import base64
import logging
import os
import uuid
from django.utils import timezone
import pandas as pd
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponse
from django.http.multipartparser import MultiPartParserError
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from crm.models import ContactType
from chatbot.charts.dahboard_stats import conversations_over_time
from chatbot.models.chatbot_session import ChatbotSession
from crm.core.data_import import import_addresses, import_customers, import_products, import_leads, import_contacts, \
    import_tags
from crm.core.integrators import get_all_orders
from crm.core.tools import track_dac_delivery
from crm.forms import TicketAddForm
from crm.models import Shipment, Branch, Ticket, EcommerceOrder, Contact, Customer, Product, \
    Face
from crm.tasks import woocommerce_webhook_processor, create_smart_order, import_frontend_skus
from moio_platform.lib.json_schema_tools import _load_schema, _infer_schema, merge_schemas, _save_schema
from moio_platform.lib.openai_gpt_api import analyze_file
from central_hub.context_utils import current_tenant
from central_hub.models import Tenant
from central_hub.tenant_config import get_tenant_config, get_tenant_config_by_id

logger = logging.getLogger(__name__)

# views.py
import json

from django.http import JsonResponse
from django.conf import settings
from jsonschema import validate as jsonschema_validate, ValidationError as JSONSchemaError

from .models import WebhookConfig
from .tasks import generic_webhook_handler   # Celery task
from chatbot.agents.moio_agents_loader import get_available_tools

# Create your views here.


@login_required()
def deliveries(request):

    shipment_list = Shipment.objects.all().order_by('-creation_date')
    if request.method == "POST":
        return render(request, template_name="shipment/shipment_table.html", context={"shipments": shipment_list})

    return render(request, template_name="shipment/shipments.html", context={"shipments": shipment_list})


def deliveries_tracking(request, tracking_code):
    User = get_user_model()
    tenant = User.objects.get(username=request.user.username).tenant
    delivery_details = None
    tracking_steps = None

    tracking_history = track_dac_delivery(tracking_code, tenant.id)
    if tracking_history:

        print(tracking_history)

        delivery_details = tracking_history[0]
        tracking_steps = tracking_history[1]

    return render(request, 'shipment/delivery_tracking.html', {'delivery_details': delivery_details, 'tracking_steps': tracking_steps })


@csrf_exempt
def woocommerce_webhook_receiver(request, tenant_code):
    # Calculate HMAC using the Secret Key.
    secret = 'chipotle'  # Replace with your webhook secret.

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method.'}, status=405)

    body = request.body.decode('utf-8')
    try:
        tenant = Tenant.objects.get(tenant_code__exact=tenant_code)

    except Tenant.DoesNotExist:
        return JsonResponse({'error': 'Bad Request.'}, status=400)

    print(tenant)

    headers = {
        "topic": request.headers.get('X-WC-Webhook-Topic'),
        "webhook_resource": request.headers.get('X-WC-Webhook-Resource'),
        "webhook_id": request.headers.get('X-WC-Webhook-ID'),
        "woo_delivery_id": request.headers.get('X-WC-Delivery-ID'),
        "webhook_signature": request.headers.get('X-Wc-Webhook-Signature')

    }

    print(f'Queuing {headers["webhook_resource"]} to be processed ')

    headers = json.dumps(headers)
    job = woocommerce_webhook_processor.apply_async(args=[headers, body, tenant.tenant_code], queue=settings.MEDIUM_PRIORITY_Q)

    return JsonResponse({'status': 'success'}, status=200)


@csrf_exempt
def generic_webhook_receiver(request, webhook_id):
    """
    Generic webhook endpoint that enforces every rule stored in WebhookConfig:
      • HTTP method must be POST
      • Auth (_check) must pass
      • Origin must match (if set)
      • Content-Type must match (or, if unlocked, is learned and stored)
      • JSON payload must satisfy expected_schema (if provided)
    On success, the raw data are pushed to Celery.
    """
    # ──────────────────────────────── 1. basic guards ───────────────────────────
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        cfg: WebhookConfig = WebhookConfig.objects.get(id=webhook_id)
    except WebhookConfig.DoesNotExist:
        return JsonResponse({"error": "Unknown webhook"}, status=404)

    # DRF request has .query_params; mimic for plain Django request
    if not hasattr(request, "query_params"):
        request.query_params = request.GET

    # ──────────────────────────────── 2. auth  ─────────────────────────────────
    ok, reason = cfg._check(request)
    if not ok:
        return JsonResponse({"error": reason}, status=401)

    # ──────────────────────────────── 3. origin  ───────────────────────────────
    if cfg.expected_origin:
        origin = (
            request.headers.get("Origin")
            or request.headers.get("Referer")
            or request.META.get("REMOTE_ADDR", "")
        )
        if cfg.expected_origin not in origin:
            return JsonResponse({"error": "Origin not allowed"}, status=400)

    # ──────────────────────────────── 4. content type  ─────────────────────────
    content_type_header = request.headers.get("Content-Type", "")
    # take only the part before any “;” (e.g. drop “; boundary=…”)
    media_type = content_type_header.split(";", 1)[0].strip().lower()

    # what we’ve stored previously (should be just the media type)
    expected_ct = (cfg.expected_content_type or "").lower()

    if expected_ct:
        # enforcement mode: we have a stored type, so must match
        if media_type != expected_ct:
            return JsonResponse({"error": "Content-Type mismatch"}, status=400)

    elif cfg.locked:
        # locked *and* no media type configured yet → reject
        return JsonResponse({"error": "Content-Type not configured"}, status=400)

    else:
        # unlocked & first time: learn the media type
        cfg.expected_content_type = media_type
        cfg.save(update_fields=["expected_content_type"])

    # ──────────────────────────────── 5. payload extraction ────────────────────
    if "application/json" in content_type_header:
        try:
            payload = json.loads(request.body.decode("utf-8"))

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        # ─── NEW: normalise any inline base-64 files ───
        files_block = payload.get("files", {})
        for field, info in list(files_block.items()):
            b64 = info.pop("content_base64", None)  # remove; returns None if absent
            if not b64:
                continue  # nothing to normalise

            # 1. decode base-64 → bytes  (return 400 on bad data)
            try:
                raw_bytes = base64.b64decode(b64)
            except Exception:
                return JsonResponse({"error": f"Invalid base64 in '{field}'"}, status=400)

            # 2. store in your default storage
            unique_name = f"{uuid.uuid4().hex}_{info.get('filename', 'file')}"
            path = f"{cfg.tenant.nombre}/attachments/{webhook_id}/{unique_name}"
            default_storage.save(path, ContentFile(raw_bytes))

            # 3. replace inline blob with a public URL
            info["url"] = default_storage.url(path)

    elif "multipart/form-data" in content_type_header:
        # wrap POST parsing to catch missing-boundary errors
        try:
            form_data = request.POST.dict()
        except MultiPartParserError:
            logger.error(
                "Bad request (Unable to parse request body): %s",
                request.path
            )
            return JsonResponse(
                {"error": "Invalid multipart/form-data"},
                status=400
            )

        files_data = {}
        for field_name, uploaded in request.FILES.items():
            # save to your default_storage as before
            path = f"{cfg.tenant.nombre}/attachments/{webhook_id}/{uploaded.name}"
            saved = default_storage.save(path, uploaded)
            url = default_storage.url(saved)

            files_data[field_name] = {
                "filename": uploaded.name,
                "content_type": uploaded.content_type,
                "size": uploaded.size,
                "url": url,
            }

        payload = {"form": form_data, "files": files_data}

    else:
        payload = request.body.decode("utf-8", errors="replace")

    # ──────────────────────────────── 6. JSON-schema check ─────────────────────
    # ─────────── 6. JSON-schema enforcement / “learn-on-first-hit” ───────────
    #
    # Behaviour is now symmetrical to the Content-Type logic:
    #   • If cfg.locked is False *and* no schema recorded yet → derive a schema
    #     from the first valid JSON payload and persist it in cfg.expected_schema.
    #   • Once cfg.locked is True we only validate; any mismatch → 400.
    #   • If cfg.locked is True but expected_schema is still empty → reject
    #     (someone forgot to warm-up the endpoint before locking it).

    is_json_payload = isinstance(payload, (dict, list))
    stored_schema = _load_schema(cfg.expected_schema)

    if not cfg.locked and is_json_payload:
        new_schema = _infer_schema(payload)
        stored_schema = _load_schema(cfg.expected_schema)

        merged = merge_schemas(stored_schema, new_schema)
        _save_schema(cfg, merged)

    else:  # cfg.locked == True  (enforcement mode)
        if stored_schema is None:
            return JsonResponse(
                {"error": "Webhook locked but schema missing or invalid"}, status=400
            )

    # If a schema is configured (valid JSON schema in cfg.expected_schema), validate payload.
    # This keeps flow/webhook contracts honest: missing required fields should be rejected here,
    # not deferred into flow runtime evaluation.
    if is_json_payload and stored_schema is not None:
        try:
            jsonschema_validate(payload, stored_schema)
        except JSONSchemaError:
            return JsonResponse({"error": "Schema validation failed"}, status=400)

    # ──────────────────────────────── 7. ship to Celery ────────────────────────

    headers = dict(request.headers)
    logger.info(f"Shipping {cfg.name} to {cfg.handler_path} ")
    if settings.DEBUG:
        print(payload)

    job = generic_webhook_handler.apply_async(
        args=[payload, headers, content_type_header, str(webhook_id)],
        queue=settings.MEDIUM_PRIORITY_Q,
    )
    return JsonResponse({"status": "received", "job_id": job.id, "handler": cfg.handler_path }, status=200)


@login_required
def branch_list(request):

    User = get_user_model()
    tenant = User.objects.get(username=request.user.username).tenant

    branch_records = Branch.objects.filter(tenant=tenant)
    #  messages.success(request, "Hola, que tal?")

    # return render(request, 'recruiter/dashboard.html', {})
    context = {
        "branches": branch_records,
        'markers': get_branch_markers(tenant=tenant),
        'GOOGLE_MAPS_API_KEY': get_tenant_config(tenant).google_api_key,
        # 'candidate_clusters': get_candidate_clusters(tenant=tenant)
    }

    return render(request, 'company/branches.html', context=context)


@login_required
def get_branch_markers(tenant):

    branch_list = Branch.objects.filter(tenant=tenant)
    markers = []
    for branch in branch_list:
        m = {
            'lat': str(branch.latitude),
            'lng': str(branch.longitude),
            'title': branch.name
        }
        # print(m)
        markers.append(m)

    return json.dumps(markers)


@login_required()
def crm_dashboard_kpis(request):

    context = {
        "contacts": Contact.objects.filter(tenant=current_tenant.get()).count(),
        "pending_orders": EcommerceOrder.objects.filter(status__exact="processing").count(),
        "risk_orders": EcommerceOrder.objects.filter(status__in=("on_hold", "failed")).count(),
        "active_sessions": ChatbotSession.objects.filter(active__exact=True, tenant=current_tenant.get()).count(),
        "customers": Customer.objects.filter(tenant=current_tenant.get()).count()

    }
    print(context)

    return render(request, 'crm/partials/dashboard_kpis.html', context=context)


# ====================== PRODUCTS =====================================================

@login_required()
def product_list(request):
    tenant = current_tenant.get()
    if request.method == "POST":
        search_word = request.POST.get("search")
        try:
            products = Product.objects.search(search_word, tenant=tenant)

        except Exception as e:
            print(f'Ocurrio un problema: {e}')
            products = None
        return render(request, template_name='products/product_list.html', context={'products': products})

    else:
        products = Product.objects.filter(tenant=tenant)
        print("lista de productos")
        for p in products:
            print(p)


        return render(request, template_name='products/products.html', context={'products': products})


@login_required()
def product_add(request):

    if request.method == "POST":

        return render(request, template_name='products/product_list.html')

    else:

        return render(request, template_name='products/product_add_form.html', context={'form': None})

# ===================== CUSTOMERS ====================================================


@login_required
def add_customer(request):

    return render(request, "customers/add.html", {})


@login_required
def update_customer(request, pk):

    return render(request, "customers/update.html", {})


@login_required
def customers_list(request):

    if request.method == "POST":
        search_word = request.POST.get("search")
        customers = Customer.objects.search(search_word)
        return render(request, template_name='customers/customer_list.html', context={'customers': customers})

    else:
        customers = Customer.objects.all()
        return render(request, template_name='customers/customers.html', context={'customers': customers})

# ============================== ORDERS =================================================


@login_required
def add_order(request):
    tenant_configuration = get_tenant_config(current_tenant.get())

    if request.method == "POST":

        if request.POST.get("source-form") == "smart-order" and tenant_configuration.openai_integration_enabled :
            print("smart enabled")
            data = request.POST.get("smart-order-content")

            print(f'Encolando en {os.environ.get("APP_NAME", "default")}')
            result = create_smart_order.apply_async(args=[data, tenant_configuration.tenant.id], queue=settings.MEDIUM_PRIORITY_Q)
            print("Done")
            print(result)
            order_details = result.get()
            print(order_details)
        else:
            print("manual")

    return render(request, "orders/add.html", {"order_details": order_details})


@login_required
def update_order(request):

    return render(request, "orders/update.html", {})


@login_required
def orders_list(request):

    if request.method == "POST":
        search_word = request.POST.get("search")
        orders = EcommerceOrder.objects.search(search_word).order_by("-created")
        return render(request, template_name='orders/order_list.html', context={'orders': orders})

    else:

        orders = EcommerceOrder.objects.filter(tenant=current_tenant.get()).order_by('-created')
        return render(request, template_name='orders/orders.html', context={'orders': orders})


@login_required
def import_ecommerce_orders(request):
    User = get_user_model()
    tenant = User.objects.get(username=request.user.username).tenant
    get_all_orders(tenant=tenant)

    return HttpResponse(
        status=204,
        headers={
            'HX-Trigger': json.dumps({
                "showMessage": "Ordenes Importadas"
            })
        })


# ============================== CONTACTS ================================================


@login_required
def contact_paged_list(request):
    print("page list")
    tenant = current_tenant.get()
    action = request.GET.get('action')
    print(f"get requested {request.GET}")

    all_contacts = Contact.objects.filter(tenant=tenant).order_by("-created")
    if request.method == "GET" and request.GET.get("action") == "filter":
        ctype_filter = request.GET.get("ctype_filter", "")
        if ctype_filter != "":
            all_contacts = all_contacts.filter(ctype__name__icontains=ctype_filter, tenant=tenant)
        search_term = request.GET.get("search_term", "").strip()
        if search_term != "":
            all_contacts = all_contacts.search(search_term, tenant=tenant)

        print(ctype_filter)
        print(search_term)

    paginator = Paginator(all_contacts, 30)
    page_number = request.GET.get('page_number', 1)
    contact_page = paginator.page(page_number)

    current_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    contact_metrics = {
        'total_contacts': Contact.objects.filter(tenant=tenant).count(),
        'new_this_month': Contact.objects.filter(tenant=tenant, created__gte=current_month).count(),
        'active_contacts': Contact.objects.filter(
            tenant=tenant,
            chatbot_session__active=True
        ).distinct().count(),
        'customer_contacts': Contact.objects.filter(
            tenant=tenant,
            ctype__name='customer'
        ).count(),
    }

    context = {
        'contacts': contact_page,
        'ctype_choices': ContactType.objects.filter(tenant=tenant),
        'contact_metrics': contact_metrics
    }

    if action == "load_more" or action == "filter":
        print("loading more..")
        return render(request, template_name='crm/contacts/partials/contact_list.html', context=context)

    partial_template = 'crm/contacts/contacts.html'
    if request.headers.get("HX-Request") == "true":
        return render(request, template_name=partial_template , context=context)
    else:
        # context["load_page"] = request.path
        context["partial_template"] = partial_template
        return render(request, 'layout.html', context=context)


@login_required
def contact_add(request):
    """Add a new contact"""
    if request.method == "POST":
        from crm.services.contact_service import ContactService
        
        contact, message = ContactService.create_contact(
            tenant=current_tenant.get(),
            fullname=request.POST.get('fullname', '').strip(),
            email=request.POST.get('email', '').strip(),
            phone=request.POST.get('phone', '').strip(),
            whatsapp_name=request.POST.get('whatsapp_name', '').strip(),
            source=request.POST.get('source', '').strip(),
            ctype_name=request.POST.get('ctype', '').strip()
        )

        print(contact, message)

        if contact:
            messages.success(request, message)
        else:
            messages.error(request, message)
            
        return render(request, template_name='crm/partials/contact_table_item.html', context={'contact': contact})
    
    return redirect('crm:contacts')


@login_required
def contact_update(request):
    if request.method == "POST":
        pk = request.POST.get("pk")
        print(pk)
        try:
            contact = Contact.objects.get(pk=pk)
            # contact.fullname = request.POST.get('fullname')
            contact.email = request.POST.get('email')
            contact.phone = request.POST.get('phone')
            contact.whatsapp_name = request.POST.get('whatsapp_name')
            # contact.source = request.POST.get('source')
            contact.ctype = request.POST.get('ctype')
            contact.company = request.POST.get('company')
            contact.save()

        except Contact.DoesNotExist:
            print("Contact not found")

        return HttpResponse(
            status=204,
            headers={
                'HX-Trigger': json.dumps({
                    "showMessage": "actualizado"
                })
            })


# ============================== TICKETS =================================================

@login_required
def tickets(request):
    tenant = current_tenant.get()
    try:
        all_tickets = Ticket.objects.filter(tenant=tenant).order_by("-created")

        open_count = all_tickets.filter(status="O").count()
        in_progress_count = all_tickets.filter(status="I").count()

        not_closed = all_tickets.exclude(status__exact="C")

        context = {
            "tickets": not_closed,
            "metrics": {
                "open": open_count,
                "in_progress": in_progress_count,
                "resolved": "n/a",
                "avg_response": "n/a"
            }
        }

        partial_template = 'crm/tickets/tickets.html'
        if request.headers.get("HX-Request") == "true":
            return render(request, template_name=partial_template, context=context)
        else:
            # context["load_page"] = request.path
            context["partial_template"] = partial_template
            return render(request, 'layout.html', context=context)

    except Exception as e:
        print(e)

        return HttpResponse("Server error", status=500)


@login_required
def ticket_list(request):
    tenant = current_tenant.get()
    tkts = Ticket.objects.filter(tenant_id=tenant.id).exclude(status__exact='C').order_by('created')

    if request.GET.get("my_tickets", None):
        try:
            asignee = Contact.objects.get(tenant=tenant, email=request.user.email)
        except Contact.DoesNotExist:
            asignee = None
        print(f"Tickets asignados a {asignee}")
        tkts = tkts.filter(tenant_id=tenant.id, assigned=asignee)

    return render(request, 'crm/tickets/partials/tickets_list.html', {"tickets": tkts})


@login_required
def ticket_add(request):
    if request.method == "POST":
        form = TicketAddForm(request.POST, request.FILES)

        if form.is_valid():

            ticket = form.save()

            return HttpResponse(
                status=204,
                headers={
                    'HX-Trigger': json.dumps({
                        "ticketAdded": None,
                        "showMessage": f"Ticket creado."
                    })
                })

        else:
            print(f"no valido {form.errors}")
            messages.error(request, form.errors)
    else:
        return render(request, "crm/tickets/add.html", context={'add_ticket_form': TicketAddForm(initial={'tenant': current_tenant.get().id})})


@login_required
def ticket_update(request, id):

    return None


@login_required
def ticket_details(request, id):
    ticket = Ticket.objects.get(id__exact=id)
    return render(request=request, template_name="crm/tickets/partials/ticket_details.html", context={"ticket": ticket})


def ticket_details_public(request, id):
    ticket = Ticket.objects.get(id__exact=id)
    return render(request=request, template_name="crm/tickets/ticket_details.html", context={"ticket": ticket})


@login_required
def ticket_comment_add(request, id):

    ticket = Ticket.objects.get(id__exact=id)
    try:
        comment_creator = Contact.objects.get(email=request.user.email)
    except Contact.DoesNotExist:
        comment_creator = None
        logger.error(f"Contact for {request.user.email} not found")

    if request.method == "POST":

        item = ticket.comments.create(comment=request.POST.get("new-comment"), creator=comment_creator)
        item.save()

        return render(request, template_name='crm/tickets/partials/ticket_comment_bubble.html', context={'item': item} )


@login_required
def ticket_kpis_dashboard(request):

    context = {
        "open_tickets": Ticket.objects.filter(status__exact="O").count(),
        "incidents_count": Ticket.objects.filter(type__exact="I").count(),
        "changes_count": Ticket.objects.filter(type__exact="C").count(),
        "planned_count": Ticket.objects.filter(type__exact="P").count(),
        "delayed": "n/a",
        "sla": "n/a",
        "GOOGLE_MAPS_API_KEY ": "",

    }

    return render(request, 'crm/tickets/partials/dashboard_ticket_kpis.html', context=context)


def ticket_status_change(request, id):

    try:
        ticket = Ticket.objects.get(id__exact=id)

        if request.method == "POST":

            ticket.status = request.POST.get("new_status")
            ticket.last_updated = timezone.now()
            try:
                asignee = Contact.objects.get(email=request.user.email)
                ticket.assigned = asignee
            except Contact.DoesNotExist:
                logger.error("Could not assign the ticket, the User has no Contact Info")
            ticket.save()

            if ticket.status == "C":
                badge_color = "bg-success"
            elif ticket.status == "I":
                badge_color = "bg-info"
            elif ticket.status == "O":
                badge_color = "bg-primary"
            else:
                badge_color = "bg-warning"

            new_status = ticket.get_status_display()
            print(f'New status: {new_status}')

            status_details = f'<span class="badge {badge_color} small text-end" id="ticket-status-badge-{ticket.id}" hx-swap-oob="outerHTML">{new_status}</span>'
            oob_ticket_list_status = f'<span class="badge {badge_color} small" id="ticket-list-status-badge-{ticket.id}" hx-swap-oob="outerHTML">{new_status}</span>'
            return HttpResponse(status_details + oob_ticket_list_status)

    except Ticket.DoesNotExist:
        logger.error("Ticket not found")

# ==============================  END TICKETS =================================================
@login_required
def client_address_import(request):

    if request.method == "POST":

        if 'xls_file' in request.FILES:
            import_file = request.FILES['xls_file']
            file_content_type = import_file.content_type

            print(file_content_type)
            na_values = ["", "N/A", "NA", "-", "None", "#N/A"]  # Add any strings that should be considered as NaN

            df = pd.read_excel(import_file, na_values=na_values)
            column_names = df.columns.to_list

            for index, row in df.iterrows():
                client_ext_ref = str(row.get("CodigoExt", "")).split(".")[0]
                tipo_id = row.get("TipoID", "")
                customer_id = str(row.get("ID", "")).split(".")[0]
                address_ext_ref = str(row.get("Sucursal", "")).split(".")[0]
                location = row.get("Geo", "")
                address_name = row.get("Name", "")
                legal_name = row.get("Razon", "")
                address = row.get("Direccion", "")

                if customer_id != 'nan':
                    print(f'Cliente {legal_name} {tipo_id}:{customer_id} | Cliente:{client_ext_ref}')
                    print(f'Direccion: {address} | Sucursal: {address_ext_ref}')

                    # if location != 'nan':
                    if pd.notna(location):
                        print(f'Coordinates: {location}')

            print(column_names)

    else:
        return render(request, template_name='admin/upload_file.html')


@login_required
def products_import(request):
    tenant = current_tenant.get()

    job = import_frontend_skus.apply_async(args=[tenant.id,], queue=settings.MEDIUM_PRIORITY_Q)

    return HttpResponse(
        status=204,
        headers={
            'HX-Trigger': json.dumps({
                "showMessage": f"Importando productos tarea: {job.task_id} "
            })
        })


@login_required()
def product_tags(request, product_id):

    product = Product.objects.get(id=product_id)
    return render(request, 'products/product_tag_list.html', context={'product': product})


# ==============================  DEALS =================================================
@login_required
def deals(request):

    phases = ((1, "Prospecting"), (2, "Negotiation"), (3, "Proposal"),
              (4, "Closed Won"))
    deal_range = range(1, 11)

    context = {
        "phases": phases,
        "deal_range": deal_range,
    }

    partial_template = "crm/deals.html"
    if request.headers.get("HX-Request") == "true":
        return render(request, partial_template, context=context)
    else:
        # context["load_page"] = request.path
        context["partial_template"] = partial_template
        return render(request, 'layout.html', context=context)


@login_required
def dashboard(request):
    tenant = current_tenant.get()
    if not tenant:
        return HttpResponse(content="Tenant not found", status=500)
    config = get_tenant_config(tenant)

    contacts_with_session_count = Contact.objects.annotate(
        session_count=Count('chatbot_session')
    ).filter(session_count__gt=0, tenant=tenant).values('user_id', 'fullname', 'phone',
                                                        'session_count')  # Adjust fields as needed

    context = {
        "conversations_over_time": conversations_over_time(tenant, date_range=90),
        "contacts_with_session_count": contacts_with_session_count,
        "total_value": "48,000",
        "value_growth": "12",
        "active_deals": "6",
        "deals_growth": "8",
        "completed_tasks": "5",
        "completed_growth": "18",
        "open_tasks": "2",
        "open_growth": "5",

        "activities": [
            {"title": "New deal", "subtitle": "Created", "icon": "bi-currency-dollar", "icon_class": "bg-success-light",
             "time": "Just now"},
            {"title": "Call logged", "subtitle": "With Client", "icon": "bi-telephone",
             "icon_class": "bg-primary-light", "time": "2h ago"},
            {"title": "Note added", "subtitle": "Info", "icon": "bi-journal-text", "icon_class": "bg-warning-light",
             "time": "3h ago"},
            {"title": "Email sent", "subtitle": "Sent", "icon": "bi-envelope", "icon_class": "bg-info-light",
             "time": "5h ago"},
        ],

        "pipeline_data": [25000, 15000, 8000, 48000],

        "task_status": [
            {"label": "Today's Tasks", "count": 0, "percentage": 0},
            {"label": "This Week's Tasks", "count": 1, "percentage": 20},
            {"label": "Overdue Tasks", "count": 1, "percentage": 20},
            {"label": "Completed Tasks", "count": 5, "percentage": 100},
        ]
    }
    partial_template = 'crm/dashboard.html'
    if request.headers.get("HX-Request") == "true":
        return render(request, partial_template, context=context)
    else:
        # context["load_page"] = request.path
        context["partial_template"] = partial_template
        return render(request, 'layout.html', context=context)


@login_required
def tasks(request):
    status = ("All", "My Tasks", "Overdue", "Completed")

    context = {
        "status": status,
    }

    partial_template = 'crm/tasks.html'
    if request.headers.get("HX-Request") == "true":
        return render(request, partial_template, context=context)
    else:
        # context["load_page"] = request.path
        context["partial_template"] = partial_template
        return render(request, 'layout.html', context=context)


# ============================ COMMUNICATIONS =====================================================

@login_required
def communications(request):

    typecomm = ("Whatsapp",)
    active_chats = ChatbotSession.objects.filter(tenant=current_tenant.get(), active__exact=True).count()

    context = {
        "typecomm": typecomm,
        "active_chats": active_chats,
    }
    partial_template = 'crm/communications/communications.html'
    if request.headers.get("HX-Request") == "true":
        return render(request, partial_template, context=context)
    else:
        # context["load_page"] = request.path
        context["partial_template"] = partial_template
        return render(request, 'layout.html', context=context)


@login_required
def sessions_list(request):
    sessions = ChatbotSession.objects.filter(tenant=current_tenant.get()).order_by("-start","-last_interaction")
    action = request.GET.get('action')

    paginator = Paginator(sessions, 3)
    page_number = request.GET.get('page_number', 1)
    sessions_page = paginator.page(page_number)

    context = {
        "sessions": sessions_page,
    }

    if action == "load_more" or action == "filter":
        print("loading more..")
        return render(request, template_name='crm/communications/partials/session_list.html', context=context)

    return render(request, 'crm/communications/partials/session_list.html', context=context)

# ===============================================================

@login_required
def products(request):
    products_data = [
        {
            "name": "Advanced Leadership Program",
            "sku": "TR-ADV-002",
            "category": "Training",
            "price": "$1,499.99",
            "inventory": 15,
            "status": "active"
        },
        {
            "name": "Business Laptop Pro",
            "sku": "HW-LAP-001",
            "category": "Hardware",
            "price": "$1,299.99",
            "inventory": 25,
            "status": "active"
        },
        {
            "name": "CRM Pro License",
            "sku": "SW-CRM-001",
            "category": "Software",
            "price": "$1,499.99",
            "inventory": 50,
            "status": "active"
        }
    ]

    context = {
        "products": products_data,
        "total_products": len(products_data)
    }

    partial_template = 'crm/products.html'
    if request.headers.get("HX-Request") == "true":
        return render(request, partial_template, context=context)
    else:
        # context["load_page"] = request.path
        context["partial_template"] = partial_template
        return render(request, 'layout.html', context=context)


# ============================== WEBHOOK CONFIGURATION =================================================
from central_hub.webhooks.utils import available_handlers


@login_required
def webhook_config_list(request):
    """List all webhook configurations for the current tenant"""
    tenant = current_tenant.get()
    webhook_configs = WebhookConfig.objects.filter(tenant=tenant)

    context = {
        "webhook_configs": webhook_configs,
    }

    return render(request, 'crm/partials/webhook_config_list.html', context=context)


@login_required
def webhook_config_add(request):
    """Add a new webhook configuration"""
    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("description", "")
        expected_content_type = request.POST.get("expected_content_type", "")
        locked = request.POST.get("locked") == "on"
        auth_type = request.POST.get("auth_type", "none")
        webhook_handler = request.POST.get("webhook_handler", "")

        # Build auth_config based on auth_type
        auth_config = {}
        if auth_type == "bearer":
            auth_config = {"token": request.POST.get("bearer_token", "")}
        elif auth_type == "basic":
            auth_config = {
                "username": request.POST.get("basic_username", ""),
                "password": request.POST.get("basic_password", "")
            }
        elif auth_type == "hmac":
            auth_config = {
                "secret": request.POST.get("hmac_secret", ""),
                "signature_header": request.POST.get("hmac_signature_header", "X-Signature")
            }
        elif auth_type == "header":
            auth_config = {
                "header": request.POST.get("header_name", ""),
                "value": request.POST.get("header_value", "")
            }
        elif auth_type == "query":
            auth_config = {
                "param": request.POST.get("query_param", ""),
                "value": request.POST.get("query_value", "")
            }
        elif auth_type == "jwt":
            auth_config = {"secret": request.POST.get("jwt_secret", "")}

        webhook_config = WebhookConfig.objects.create(
            tenant=current_tenant.get(),
            name=name,
            description=description,
            expected_content_type=expected_content_type,
            locked=locked,
            auth_type=auth_type,
            auth_config=auth_config,
            handler_path=webhook_handler,
        )
        webhook_config.save()

        return HttpResponse(
            status=204,
            headers={
                'HX-Trigger': json.dumps({
                    "showMessage": f"Webhook configuration '{name}' created successfully",
                    "webhookConfigAdded": None
                })
            })

    # Get flow_id from query parameters to set default handler
    flow_id = request.GET.get('flow_id')
    default_handler = ""
    default_description = ""
    if flow_id:
        default_handler = "flows.handlers.execute_flow_webhook"
        default_description = f"flow:{flow_id}"
    
    context = {
        "available_handlers": available_handlers(),
        "default_handler": default_handler,
        "default_description": default_description,
        "flow_id": flow_id
               }
    return render(request, "crm/partials/webhook_config_form.html", context=context)


@login_required
def webhook_config_edit(request, webhook_id):
    """Edit an existing webhook configuration"""
    webhook_config = WebhookConfig.objects.get(id=webhook_id, tenant=current_tenant.get())

    if request.method == "POST":
        webhook_config.name = request.POST.get("name")
        webhook_config.description = request.POST.get("description", "")
        webhook_config.expected_content_type = request.POST.get("expected_content_type", "")
        webhook_config.locked = request.POST.get("locked") == "on"
        auth_type = request.POST.get("auth_type", "none")
        webhook_config.auth_type = auth_type
        webhook_handler = request.POST.get("webhook_handler", "")

        # Build auth_config based on auth_type
        auth_config = {}
        if auth_type == "bearer":
            auth_config = {"token": request.POST.get("bearer_token", "")}
        elif auth_type == "basic":
            auth_config = {
                "username": request.POST.get("basic_username", ""),
                "password": request.POST.get("basic_password", "")
            }
        elif auth_type == "hmac":
            auth_config = {
                "secret": request.POST.get("hmac_secret", ""),
                "signature_header": request.POST.get("hmac_signature_header", "X-Signature")
            }
        elif auth_type == "header":
            auth_config = {
                "header": request.POST.get("header_name", ""),
                "value": request.POST.get("header_value", "")
            }
        elif auth_type == "query":
            auth_config = {
                "param": request.POST.get("query_param", ""),
                "value": request.POST.get("query_value", "")
            }
        elif auth_type == "jwt":
            auth_config = {"secret": request.POST.get("jwt_secret", "")}

        webhook_config.auth_config = auth_config
        webhook_config.handler_path = webhook_handler
        webhook_config.save()

        return HttpResponse(
            status=204,
            headers={
                'HX-Trigger': json.dumps({
                    "showMessage": f"Webhook configuration '{webhook_config.name}' updated successfully",
                    "webhookConfigUpdated": None
                })
            })

    context = {
        "webhook_config": webhook_config,
        "available_handlers": available_handlers()
    }

    return render(request, "crm/partials/webhook_config_form.html", context=context)


@login_required
def webhook_config_delete(request, webhook_id):
    if request.method == "POST":
        try:
            webhook = WebhookConfig.objects.get(id=webhook_id, tenant=current_tenant.get())
            webhook.delete()
            messages.success(request, "Webhook configuration deleted successfully.")
        except WebhookConfig.DoesNotExist:
            messages.error(request, "Webhook configuration not found.")

    return redirect('crm:settings')

# =====================================================================================================
# AI Agent Configuration Views


@login_required
def agent_config_list(request):
    from chatbot.models.agent_configuration import AgentConfiguration
    agents = AgentConfiguration.objects.filter(tenant=current_tenant.get())
    return render(request, 'crm/partials/agent_config_list.html', {'agents': agents})


@login_required
def agent_config_add(request):
    if request.method == "POST":
        from crm.services.agent_service import AgentService
        
        agent, message = AgentService.create_agent(
            tenant=current_tenant.get(),
            name=request.POST.get('name'),
            model=request.POST.get('model', 'gpt-4o-mini'),
            instructions=request.POST.get('instructions', ''),
            channel=request.POST.get('channel', ''),
            channel_id=request.POST.get('channel_id', ''),
            tools_json=request.POST.get('tools', '[]'),
            enabled=request.POST.get('enabled') == 'on'
        )
        
        if agent:
            messages.success(request, message)
        else:
            messages.error(request, message)
        
        # Return the updated agent list for HTMX
        agents = AgentService.list_agents(current_tenant.get())
        return render(request, 'crm/partials/agent_config_list.html', {'agents': agents})
    context = {
        "agent": None,
        "available_tools": get_available_tools()
    }
    return render(request, 'crm/partials/agent_config_form.html', context=context)


@login_required
def agent_config_edit(request, agent_id):
    from crm.services.agent_service import AgentService
    
    agent = AgentService.get_agent_by_id(agent_id, current_tenant.get())
    from django.forms.models import model_to_dict

    data = model_to_dict(agent)
    for name, value in data.items():
        print(name, value)

    if not agent:
        messages.error(request, "Agent configuration not found.")
        return redirect('crm:settings')

    if request.method == "POST":
        success, message = AgentService.update_agent(
            agent=agent,
            name=request.POST.get('name'),
            model=request.POST.get('model', 'gpt-4o-mini'),
            instructions=request.POST.get('instructions', ''),
            channel=request.POST.get('channel', ''),
            channel_id=request.POST.get('channel_id', ''),
            tools_json=request.POST.get('tools', '[]'),
            enabled=request.POST.get('enabled') == 'on'
        )
        
        if success:
            return HttpResponse(
                status=204,
                headers={
                    'HX-Trigger': json.dumps({
                        "showMessage": f"Webhook configuration '{agent.name}' updated successfully",
                        "webhookConfigUpdated": None
                    })
                })
        else:
            return HttpResponse(
                status=204,
                headers={
                    'HX-Trigger': json.dumps({
                        "showMessage": f"Webhook configuration '{agent.name}' not saved",
                        "webhookConfigUpdated": None
                    })
                })
        
        # Return the updated agent list for HTMX
        # agents = AgentService.list_agents(current_tenant.get())
        # return render(request, 'crm/partials/agent_config_list.html', {'agents': agents})

    context = {
        "agent": agent,
        "available_tools": get_available_tools()
    }
    return render(request, 'crm/partials/agent_config_form.html', context=context)


def agent_config_delete(request, agent_id):
    from chatbot.models.agent_configuration import AgentConfiguration
    if request.method == "POST":
        try:
            agent = AgentConfiguration.objects.get(id=agent_id, tenant=current_tenant.get())
            agent.delete()
            messages.success(request, "Agent configuration deleted successfully.")
        except AgentConfiguration.DoesNotExist:
            messages.error(request, "Agent configuration not found.")

    return redirect('crm:settings')


@login_required
def deals_move_stage(request):

    print(request.POST.get("elementId"), request.POST.get("targetId"))

    return HttpResponse(
        status=204,
        headers={
            'HX-Trigger': json.dumps({
                "showMessage": "movido"
            })
        })


#======================= PAYMENT RECEIVED
import mercadopago
from mercadopago import config


@login_required
def submit_payment_form(request):
    if request.method == "POST":
        sdk = mercadopago.SDK("ACCESS_TOKEN")

        request_options = mercadopago.config.RequestOptions()
        request_options.custom_headers = {
            'x-idempotency-key': ''
        }

        payment_data = {
            "transaction_amount": float(request.POST.get("transaction_amount")),
            "token": request.POST.get("token"),
            "description": request.POST.get("description"),
            "installments": int(request.POST.get("installments")),
            "payment_method_id": request.POST.get("payment_method_id"),
            "payer": {
                "email": request.POST.get("email"),
                "identification": {
                    "type": request.POST.get("type"),
                    "number": request.POST.get("number")
                }
            }
        }

        payment_response = sdk.payment().create(payment_data, request_options)
        payment = payment_response["response"]

        print(payment)
        """SAMPLE RESPONSE
            Al crear un pago es posible recibir 3 estados diferentes: "Pendiente", "Rechazado" y "Aprobado". 

            {
           "status": "approved",
           "status_detail": "accredited",
           "id": 3055677,
           "date_approved": "2019-02-23T00:01:10.000-04:00",
           "payer": {
               ...
           },
           "payment_method_id": "visa",
           "payment_type_id": "credit_card",
           "refunds": [],
           ...
            }
            """

    context = {
        "mp_public_key" : "YOUR_PUBLIC_KEY"
    }
    partial_template = 'crm/payment_test.html'
    if request.headers.get("HX-Request") == "true":
        return render(request, 'crm/payment_test.html', context=context)
    else:
        # context["load_page"] = request.path
        context["partial_template"] = partial_template
        return render(request, 'layout.html', context=context)


@login_required
def face_detections(request):
    from crm.models import Face
    faces = Face.objects.filter(tenant=current_tenant.get())

    context = {
        "faces": faces
    }

    partial_template = "crm/faces/faces.html"
    if request.headers.get("HX-Request") == "true":
        return render(request, 'crm/faces/faces.html', context=context)
    else:
        # context["load_page"] = request.path
        context["partial_template"] = partial_template
        return render(request, 'layout.html', context=context)


@csrf_exempt
def face_search(request):
    from pgvector.django import L2Distance

    if request.method == "GET":

        raw = request.GET.get("embedding")
        emb = [float(x) for x in raw.split(",") if x]

        cfg = get_tenant_config_by_id(int(request.GET.get("tenant_id")))
        face = Face.objects.filter(tenant=cfg.tenant).exclude(embedding__isnull=True).annotate(dist=L2Distance("embedding", emb)).order_by("dist").first()

        name = "Desconocido"
        if face.contact:
            name = face.contact.fullname

        return JsonResponse(data={"face_id": face.id, "seen": face.seen, "last_seen": face.last_seen, "name": name})


@login_required
def face_page(request):

    if request.method == "GET":
        face_id = request.GET.get("face_id")
        print(f"Searching for {face_id}")
        try:
            face = Face.objects.get(id=face_id)
            context = {
                "face": face
            }

        except Exception as e:
            logger.error(e)
            return render(request, '400.html')

        partial_template = 'crm/faces/face_page.html'
        if request.headers.get("HX-Request") == "true":
            return render(request, partial_template, context=context)
        else:
            context['partial_template'] = partial_template
            return render(request, 'layout.html', context=context)


@login_required
def import_data(request):
    tenant = current_tenant.get()
    config = get_tenant_config(tenant)

    if request.method == "POST":

        uploaded_file = request.FILES.get('file')
        skip_rows = int(request.POST.get("skip-rows", "0"))

        preview_rows = int(request.POST.get('preview-rows', '5'))
        phase = request.POST.get('phase', 0)
        print(f"Phase: {phase}")

        context = {
            "preview_rows": preview_rows,
            "phase": phase,

        }

        if uploaded_file:

            analyze_file(uploaded_file, config)

            if uploaded_file.name.endswith(('.xls', 'xlsx')):

                xl = pd.ExcelFile(uploaded_file, 'calamine')

                if len(xl.sheet_names) > 1 and not request.POST.get("sheet_name"):
                    context["sheets"] = xl.sheet_names
                    print(context["sheets"])

                    return render(request, template_name='crm/partials/sheet_name_selector.html', context=context)

                df = pd.read_excel(uploaded_file, header=skip_rows, sheet_name=request.POST.get("sheet_name", 0)).fillna("")

            elif uploaded_file.name.endswith('.csv'):

                df = pd.read_csv(filepath_or_buffer=uploaded_file, header=skip_rows, dtype=str, keep_default_na=False, delimiter=";")
            elif uploaded_file.name.endswith('.pdf'):
                df = None
            else:
                df = None

            preview_data = df.head(preview_rows).to_dict(orient='records')

            context["columns"] = df.columns.to_list()
            context["data"] = preview_data
            context["total_rows"] = len(df)

            if phase == "0":

                return render(request, template_name='crm/partials/data_import_preview.html', context=context)

        print("no file")

    else:

        context = {

            "data_import_flow": str(uuid.uuid4())
        }

        return render(request, template_name='crm/modals/data_import_form.html', context=context)


# ==========================INTEGRATIONS =================================



