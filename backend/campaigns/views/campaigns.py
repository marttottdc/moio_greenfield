import json
import uuid
from datetime import datetime, time

import pandas as pd
from celery.result import AsyncResult
from django.conf import settings
from django.urls import reverse

from campaigns.core.campaign_flow import CampaignFlow
from campaigns.core.campaigns_engine import set_base_config
from chatbot.models.wa_message_log import WaMessageLog
from crm.models import Contact, ContactType
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.utils.translation import gettext as _
from campaigns.tasks import validate_campaign, send_outgoing_messages, execute_campaign

from moio_platform.celery_app import app
from moio_platform.core.core_views import handler500
from moio_platform.lib.tools import remove_keys
from portal.context_utils import current_tenant
from portal.models import Tenant, TenantConfiguration
from chatbot.lib.whatsapp_client_api import WhatsappBusinessClient, template_requirements, replace_template_placeholders, compose_template_based_message
from campaigns.models import Audience, AudienceKind, Campaign, CampaignDataStaging, Status, CampaignData
from campaigns.forms import CampaignBasicForm
from django.db.models import Avg, Count, Max, Case, When, DateTimeField, Q
from django.db.models.functions import TruncDate
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.dateparse import parse_date
from urllib.parse import urlencode
import logging

logger = logging.getLogger(__name__)


@login_required
def campaigns_view(request):
    """Main campaigns dashboard with filtering"""
    tenant = current_tenant.get()

    # Calculate metrics
    all_campaigns = Campaign.objects.filter(tenant=tenant)
    all_audiences = Audience.objects.filter(tenant=tenant)
    total_sent = sum(c.sent for c in all_campaigns)
    total_opened = sum(c.opened for c in all_campaigns)

    # Add open rates and launch status to campaigns
    campaigns_with_rates = []

    context = {
        "campaigns": campaigns_with_rates,
        "audiences": all_audiences,
        "channels": ["email", "whatsapp", "telegram", "sms"],
        "statuses": ["draft", "scheduled", "active", "ended", "archived"],
        "dashboard_metrics": {
            "total_campaigns": all_campaigns.count(),
            "active_campaigns": all_campaigns.filter(status='active').count(),
            "total_sent": total_sent,
            "total_opened": total_opened,
            "open_rate": (total_opened / total_sent * 100) if total_sent > 0 else 0,
        }
    }

    if request.headers.get("HX-Request"):
        return render(request, 'campaigns/campaigns.html', context)

    # Full page
    context["partial_template"] = 'campaigns/campaigns.html'
    return render(request, 'layout.html', context)


@login_required
def campaign_analytics(request):

    tenant = current_tenant.get()
    tenant_id = request.GET.get("tenant")
    start_param = request.GET.get("start_date")
    end_param = request.GET.get("end_date")
    status_param = request.GET.get("status")
    origin_param = request.GET.get("origin")
    search_query = request.GET.get("q")

    # queryset = WaMessageLog.objects.select_related("tenant").all()
    queryset = WaMessageLog.objects.filter(tenant=tenant)

    selected_tenant = tenant
    if request.user.is_staff:
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)
            selected_tenant = Tenant.objects.filter(id=tenant_id).first()
        else:
            queryset = queryset.filter(tenant=tenant)
    else:
        queryset = queryset.filter(tenant=tenant)

    if start_param:
        start_date = parse_date(start_param)
        if start_date:
            start_dt = datetime.combine(start_date, time.min)
            if timezone.is_naive(start_dt):
                start_dt = timezone.make_aware(start_dt, timezone.get_current_timezone())
            queryset = queryset.filter(created__gte=start_dt)

    if end_param:
        end_date = parse_date(end_param)
        if end_date:
            end_dt = datetime.combine(end_date, time.max)
            if timezone.is_naive(end_dt):
                end_dt = timezone.make_aware(end_dt, timezone.get_current_timezone())
            queryset = queryset.filter(created__lte=end_dt)

    if status_param:
        queryset = queryset.filter(status=status_param)

    if origin_param:
        queryset = queryset.filter(origin=origin_param)

    aggregated_queryset = queryset

    logs_queryset = queryset.order_by("-created")
    if search_query:
        logs_queryset = logs_queryset.filter(
            Q(user_name__icontains=search_query)
            | Q(user_number__icontains=search_query)
            | Q(body__icontains=search_query)
            | Q(user_message__icontains=search_query)
        )

    paginator = Paginator(logs_queryset, 50)
    page_number = request.GET.get("page")
    logs_page = paginator.get_page(page_number)

    volume_data = (
        aggregated_queryset.annotate(day=TruncDate("created"))
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )
    volume_per_day = [
        {
            "day": entry["day"],
            "label": entry["day"].strftime("%Y-%m-%d") if entry["day"] else "",
            "total": entry["total"],
        }
        for entry in volume_data
    ]

    delivery_performance = list(
        aggregated_queryset.values("status")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    top_users = list(
        aggregated_queryset.values("user_name", "user_number")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )

    conversation_counts = (
        aggregated_queryset.exclude(conversation_id__isnull=True)
        .values("conversation_id")
        .annotate(total=Count("id"))
    )
    average_messages = conversation_counts.aggregate(avg=Avg("total"))["avg"] or 0
    total_conversations = conversation_counts.count()

    total_messages = aggregated_queryset.count()
    unique_users = aggregated_queryset.values("user_number").distinct().count()

    status_options = sorted(
        filter(None, aggregated_queryset.values_list("status", flat=True).distinct())
    )
    origin_options = sorted(
        filter(None, aggregated_queryset.values_list("origin", flat=True).distinct())
    )

    base_query_params = {
        key: value
        for key, value in request.GET.items()
        if key in {"tenant", "start_date", "end_date", "status", "origin", "q"} and value
    }
    base_query_params.pop("page", None)
    querystring = urlencode(base_query_params)

    context = {
        "logs": logs_page,
        "volume_per_day": volume_per_day,
        "delivery_performance": delivery_performance,
        "top_users": top_users,
        "conversation_summary": {
            "average_messages": average_messages,
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "unique_users": unique_users,
        },
        "filters": {
            "tenant": str(tenant_id) if tenant_id else (str(selected_tenant.id) if selected_tenant else None),
            "start_date": start_param,
            "end_date": end_param,
            "status": status_param,
            "origin": origin_param,
            "q": search_query or "",
            "querystring": querystring,
        },
        "tenants": Tenant.objects.order_by("nombre") if request.user.is_staff else [],
        "selected_tenant": selected_tenant,
        "is_staff": request.user.is_staff,
        "status_options": status_options,
        "origin_options": origin_options,
    }

    template = "campaigns/partials/analytics_content.html"
    return render(request, template, context)


@login_required
def refresh_kpis(request):
    """Main campaigns dashboard with filtering"""
    tenant = current_tenant.get()
    print("recalculando")
    # Calculate metrics
    all_campaigns = Campaign.objects.filter(tenant=tenant)
    all_audiences = Audience.objects.filter(tenant=tenant)
    total_sent = sum(c.sent for c in all_campaigns)
    total_opened = sum(c.opened for c in all_campaigns)

    # Add open rates and launch status to campaigns
    campaigns_with_rates = []

    context = {
        "campaigns": campaigns_with_rates,
        "audiences": all_audiences,
        "channels": ["email", "whatsapp", "telegram", "sms"],
        "statuses": ["draft", "scheduled", "active", "ended", "archived"],
        "dashboard_metrics": {
            "total_campaigns": all_campaigns.count(),
            "active_campaigns": all_campaigns.filter(status='active').count(),
            "total_sent": total_sent,
            "total_opened": total_opened,
            "open_rate": (total_opened / total_sent * 100) if total_sent > 0 else 0,
        }
    }

    return render(request, 'campaigns/partials/campaigns_kpis.html', context)


@login_required
def campaign_list(request):
    """Main campaigns dashboard with filtering"""
    tenant = current_tenant.get()
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    channel_filter = request.GET.get('channel', '')

    # Build campaign queryset
    campaigns_qs = Campaign.objects.filter(
        tenant=tenant)
    if search:
        campaigns_qs = campaigns_qs.filter(name__icontains=search)
    if status_filter:
        campaigns_qs = campaigns_qs.filter(status=status_filter)
    if channel_filter:
        campaigns_qs = campaigns_qs.filter(channel=channel_filter)

    context = {
        "campaigns": campaigns_qs.order_by("-created"),
    }

    response = render(request, 'campaigns/partials/campaign_list.html', context)
    response["HX-Trigger"] = json.dumps({
        "refresh_data": None,
    })
    return response


@login_required
def campaign_add(request):

    tenant = current_tenant.get()

    if request.method == "GET":

        context = {
            "form": CampaignBasicForm(),
            "step": "1",
            "campaign": None,
            "information": _("Create your campaign with basic information. You can configure audience and settings in the next step")
        }

    else:

        new_campaign_form = CampaignBasicForm(request.POST)
        if new_campaign_form.is_valid():

            new_campaign = new_campaign_form.save(commit=False)
            new_campaign.tenant = tenant
            new_campaign.config = set_base_config(new_campaign)
            new_campaign.save()
            # Build redirect response

            redirect_url = reverse("campaigns:campaign-configure", kwargs={"pk": new_campaign.pk})
            response = HttpResponseRedirect(redirect_url)
            response["HX-Trigger"] = "refreshCampaignList"
            return response

        else:
            context = {
                "campaign": None,
                "step": "1",
                "information": _("There were errors"),
                "form": new_campaign_form,
                "errors": new_campaign_form.errors,
            }

    # HTMX modal
    return render(request, "campaigns/modals/campaign_form_multistep.html", context)


@login_required
def campaign_edit(request, pk=None):

    tenant = current_tenant.get()

    if request.method == 'POST':

        step = request.POST.get("step", "1")

        try:
            pk = request.POST.get('campaign_pk', None)

            campaign = Campaign.objects.get(pk=pk, tenant=tenant)
            form = CampaignBasicForm(request.POST, instance=campaign)

        except Campaign.DoesNotExist:
            step = "1"

            # if campaign.kind == "express" and campaign.channel == "whatsapp":
            #    return render(request, template_name='campaigns/modals/campaign_form_import.html', context=context)

            # return render(request, template_name='campaigns/modals/campaign_form_select_whatsapp_template.html', context=context)

        if step == "2":

            aud_pk = request.POST.get("audience_pk", "None")
            if aud_pk:
                try:
                    audience = Audience.objects.get(pk=aud_pk)
                    campaign.audience = audience
                    campaign.save()

                except Audience.DoesNotExist:
                    print("Audience does not exist")

                context = {
                    "campaign": campaign,
                    "step": "3",
                    "information": "Configure the campaign behaviour",
                    "form": form,
                }

        elif step == "3":  # step 3, save and refresh

            context = {
                "campaign": campaign,
                "step": "end",
                "information": "Review and Launch the campaign or leave it for later",
                "form": form,
            }

        else:
            # process result and exit
            return redirect("campaigns:campaign-list")

    elif request.method == 'GET':
        if pk:
            try:
                campaign = Campaign.objects.get(pk=pk, tenant=tenant)
                form = CampaignBasicForm(instance=campaign)

            except Campaign.DoesNotExist:
                step = "1"


@login_required
def campaign_delete(request, pk):
    """Delete campaign"""
    tenant = current_tenant.get()
    campaign = get_object_or_404(Campaign, pk=pk, tenant=tenant)

    if request.method == "DELETE":
        campaign.delete()

        return redirect('campaigns:campaign-list')


@login_required
def campaign_duplicate(request, pk):
    """Duplicate campaign"""
    tenant = current_tenant.get()
    original = get_object_or_404(Campaign, pk=pk, tenant=tenant)

    keys_to_delete = ["data_staging", ]
    clone_config = remove_keys(original.config,keys_to_delete )

    # Create copy
    Campaign.objects.create(tenant=tenant,
                            name=f"{original.name} (copy)",
                            description=original.description,
                            channel=original.channel,
                            kind=original.kind,
                            status='draft',
                            audience=original.audience,
                            config=clone_config,)

    # HTMX response
    if request.headers.get("HX-Request"):
        return campaigns_view(request)

    messages.success(request, "Campaign duplicated.")
    return redirect('campaigns:campaigns')


@login_required
def load_whatsapp_templates(request):
    """Load WhatsApp templates for campaign creation"""
    tenant = current_tenant.get()
    templates = []

    try:
        campaign = Campaign.objects.get(pk=request.GET.get("campaign_pk", None), tenant=tenant)

    except Campaign.DoesNotExist:
        campaign = None

    try:
        config = TenantConfiguration.objects.get(tenant=tenant)
        if config.whatsapp_integration_enabled:
            wa = WhatsappBusinessClient(config)
            template_list = wa.download_message_templates()

            if template_list:
                for template in template_list:
                    templates.append(
                        {
                            "id": template["id"],
                            "name": template["name"],
                            "category": template["category"],
                            "language": template["language"],
                            "components": template.get("components", []),
                            "requirements": template_requirements(template),
                            "status": template.get("status")
                        }
                    )

    except Exception as e:
        # Handle any errors gracefully
        pass

    context = {
        "templates": templates,
        "campaign": campaign
    }

    return render(request, 'campaigns/partials/whatsapp_templates_selector.html', context)


def _get_whatsapp_requirements(tenant, template_id):

    config = TenantConfiguration.objects.get(tenant=tenant)
    if config.whatsapp_integration_enabled:
        wa = WhatsappBusinessClient(config)

        # template = WaTemplate.objects.get(template_id=template_id)
        template = wa.template_details(template_id)

        return template_requirements(template)
    else:
        return None


@login_required()
def whatsapp_template_details(request, template_id):

    tenant = current_tenant.get()
    config = TenantConfiguration.objects.get(tenant=tenant)

    campaign_pk = request.GET.get("campaign_pk", None)
    enable_preview = request.GET.get("enable_preview", "True") == "True"
    enable_test = request.GET.get("enable_test", "False") == "True"

    campaign = None
    if campaign_pk:
        try:
            campaign = Campaign.objects.get(pk=campaign_pk, tenant=tenant)
        except Campaign.DoesNotExist:
            pass

    if config.whatsapp_integration_enabled:
        wa = WhatsappBusinessClient(config)
        template = wa.template_details(template_id)
        requirements = template_requirements(template)

        if request.method == "POST":

            vars = request.POST.dict()
            # print("requerimientos -------")
            # print(requirements)
            # print("valores------------")
            # print(vars)

            template_object = replace_template_placeholders(requirements, vars)
            # print("reemplazo-------")
            # print(template_object)

            namespace = wa.retrieve_template_namespace()

            msg = compose_template_based_message(template, phone=vars["whatsapp_number"], namespace=namespace, components=template_object)

            print("mensaje para enviar:", msg)

            send_result = wa.send_message(msg, "template")
            if isinstance(send_result, dict) and send_result.get("success"):
                return HttpResponse(
                    status=204,
                    headers={
                        'HX-Trigger': json.dumps({
                            "showMessage": f"Mensaje enviado"
                        })
                    })
            else:
                error = send_result.get("error", "Error desconocido") if isinstance(send_result, dict) else "Error desconocido"
                return HttpResponse(
                    status=204,
                    headers={
                        'HX-Trigger': json.dumps({
                            "showMessage": f"Mensaje no Enviado: {error}"
                        })
                    })

        else:

            context = {
                'enable_test': enable_test,
                'enable_preview': enable_preview,
                'target_template': template,
                'requirements': requirements,
                'contacts': Contact.objects.filter(tenant=config.tenant_id).order_by("fullname", "whatsapp_name"),
                'campaign': campaign,
            }
            return render(request, 'campaigns/partials/whatsapp_template_detail.html', context)
    else:
        HttpResponse(status=500)


@login_required
def whatsapp_templates_tab(request):

    tenant = current_tenant.get()
    templates = []

    try:
        config = TenantConfiguration.objects.get(tenant=tenant)
        if config.whatsapp_integration_enabled:
            wa = WhatsappBusinessClient(config)
            template_list = wa.download_message_templates()

            if template_list:
                for template in template_list:
                    templates.append({
                        "id": template["id"],
                        "name": template["name"],
                        "category": template["category"],
                        "language": template["language"],
                        "status": template.get("status", "UNKNOWN"),
                        "components": template.get("components", [])
                    })

    except Exception as e:
        # Handle any errors gracefully
        pass

    context = {"templates": templates}
    return render(request, 'campaigns/partials/whatsapp_templates_tab.html', context)


@login_required
def campaign_configure(request, pk=None):

    tenant = current_tenant.get()
    whatsapp_template_set = False
    campaign_data_set = False
    campaign_mapping_set = False
    campaign_audience_set = False
    campaign_schedule_set = False

    if pk is None and request.method == "POST":
        pk = request.POST.get("campaign_pk")

    try:
        campaign = Campaign.objects.get(pk=pk)

        if request.method == "POST":
            action = request.POST.get("action")

            if action == "set_whatsapp_template":
                logger.info("Setting whatsapp template")
                whatsapp_template_id = request.POST.get("whatsapp_template_id")
                print(f"whatsapp_template_id: {whatsapp_template_id}")
                requirements = _get_whatsapp_requirements(tenant, whatsapp_template_id)
                print(f"requirements: {requirements}")

                campaign.config["message"]["whatsapp_template_id"] = whatsapp_template_id
                campaign.config["message"]["template_requirements"] = requirements
                campaign.save(update_fields=["config"])

                whatsapp_template_set = True

            elif action == "set_defaults":
                logger.info("Setting defaults")

                campaign.config["defaults"]["auto_correct"] = request.POST.get("auto_correct", None) == "on"
                campaign.config["defaults"]["use_first_name"] = request.POST.get("auto_set_first_name", None) == "on"
                campaign.config["defaults"]["save_contacts"] = request.POST.get("save_contacts", None) == "on"
                campaign.config["defaults"]["notify_agent"] = request.POST.get("notify_agent", None) == "on"

                campaign.config["defaults"]["contact_type"] = request.POST.get("contact_type_for_contacts", None)
                campaign.config["defaults"]["country_code"] = request.POST.get("default_country_code", None)
                logger.info("saving defaults", campaign.config["defaults"])
                campaign.save(update_fields=["config"])

                return HttpResponse(content_type="text/plain", status=204)

            elif action == "confirm_campaign_configuration":
                job = validate_campaign.apply_async(args=[str(campaign.pk),], queue=settings.MEDIUM_PRIORITY_Q)
                print(f"Sent to worker in job: {job.id}")
                context = {
                    "job_id": job.id,
                    "campaign_pk": campaign.pk
                }
                return render(request, template_name='campaigns/modals/campaign_validation.html', context=context)

        if campaign.config["message"].get("whatsapp_template_id", None):
            whatsapp_template_set = True

        if campaign.config["message"].get("map", None):
            campaign_mapping_set = True

        if campaign.config["data"].get("data_staging", None):
            campaign_data_set = True

        if campaign.config["schedule"].get("date", None):
            campaign_schedule_set = True

        from campaigns.core.campaigns_engine import describe_configuration
        prompt = f"""
        based on the following configuration describe te behaviour of the campaign using this language {request.LANGUAGE_CODE}
        campaign data refers to the headers available to map to the template and if present the data staging is where the bulk of data is loaded.
        message refers to the message configuration, template, template requirements, and the mapping of requirements to available fields in the data
        defaults refers to the behaviour of the campaign.
        schedule to when the campaign should be executed
        if all is empty, configuration needs to be done. Use at most 400 char.
        """
        description = describe_configuration(tenant, prompt=prompt, campaign=campaign)

        ctypes = ContactType.objects.filter(tenant=tenant).distinct()

        steps = [
            {"label": "Datos", "url": "/config/datos/", "weight": 2},
            {"label": "Plantilla", "url": "/config/mensaje/", "weight": 1},
            {"label": "Selección", "url": "/config/mensaje/","weight": 1},
            {"label": "Validación", "url": "/config/validacion/", "weight": 2},
            {"label": "Programación", "url": "/config/programacion/", "weight": 2},
        ]
        current_idx = 1  # 0-based

        context = {
            "campaign": campaign,
            "campaign_config_description": description,
            "campaign_defaults": campaign.config["defaults"],
            "audiences": Audience.objects.filter(tenant=tenant, is_draft=False),
            "whatsapp_template_set": whatsapp_template_set,
            "campaign_data_set": campaign_data_set,
            "campaign_mapping_set": campaign_mapping_set,
            "campaign_audience_set": campaign_audience_set,
            "campaign_schedule_set": campaign_schedule_set,
            "contact_types": ctypes,
            "steps": steps,
            "current_idx": current_idx
        }
        return render(request, template_name='campaigns/modals/campaign_behaviour_form.html', context=context)

    except Campaign.DoesNotExist:
        return HttpResponse(status="500", template="500.html")


@login_required
def import_data(request, pk=None):
    tenant = current_tenant.get()
    try:
        if pk is None:
            pk = request.POST.get("campaign_pk")

        campaign = Campaign.objects.get(pk=pk, tenant=tenant)

        if request.method == "POST":

            uploaded_file = request.FILES.get('file')
            skip_rows = int(request.POST.get("skip-rows", "0"))

            preview_rows = int(request.POST.get('preview-rows', '5'))
            phase = request.POST.get('phase', 0)
            logger.info(f"Campaign configuration phase: {phase}")

            context = {
                "campaign": campaign,
                "preview_rows": preview_rows,
                "phase": phase,
                "requirements": campaign.config["message"]["template_requirements"]
            }

            if uploaded_file:

                if uploaded_file.name.endswith(('.xls', 'xlsx')):
                    logger.info("Processing Excel file")

                    xl = pd.ExcelFile(uploaded_file, 'calamine' )

                    if len(xl.sheet_names) > 1 and not request.POST.get("sheet_name"):
                        context["sheets"] = xl.sheet_names
                        print(context["sheets"])

                        return render(request, template_name='campaigns/partials/sheet_name_selector.html', context=context)

                    df = pd.read_excel(uploaded_file, header=skip_rows, dtype=str, sheet_name=request.POST.get("sheet_name", 0)).fillna("")

                else:

                    df = pd.read_csv(filepath_or_buffer=uploaded_file, header=skip_rows, dtype=str, keep_default_na=False, delimiter=";")

                preview_data = df.head(preview_rows).to_dict(orient='records')

                context["columns"] = df.columns.to_list()
                context["data"] = preview_data
                context["total_rows"] = len(df)

                if phase == "0":

                    return render(request, template_name='campaigns/partials/data_import_preview.html', context=context)

                elif phase == "confirm_data":

                    try:
                        raw_data = df.to_dict(orient='records')
                        print(raw_data)
                    except Exception as e:
                        logger.error(e)
                        return redirect(reverse("server_error"))

                    logger.info("Confirming data import")
                    campaign_staging_pk = request.POST.get("data_import_flow", None)

                    try:
                        logger.info(f"Campaign staging pk={campaign_staging_pk}")
                        campaign_staging = CampaignDataStaging.objects.get(pk=campaign_staging_pk, campaign_id=campaign.pk, tenant=tenant)
                        campaign_staging.raw_data = raw_data
                        campaign_staging.row_count = len(df)
                        campaign_staging.save()

                    except CampaignDataStaging.DoesNotExist:
                        logger.info(f"No campaign staging found, creating one")

                        campaign_staging = CampaignDataStaging.objects.create(
                            tenant=tenant,
                            campaign_id=campaign.pk,
                            raw_data=raw_data,
                            row_count=len(df),
                            import_source=f"data_import",
                            original_filename=uploaded_file.name
                        )
                        campaign.config["data"]["headers"] = df.columns.tolist()
                        campaign.config["data"]["data_staging"] = str(campaign_staging.pk)

                        campaign.save(update_fields=["config"])

                    return redirect("campaigns:campaign-configure", pk=campaign.pk)

            logger.error("No file uploaded")

        else:

            campaign = Campaign.objects.get(tenant=tenant, pk=pk)

            context = {
                "campaign": campaign,
                "data_import_flow": str(uuid.uuid4())
            }

            return render(request, template_name='campaigns/modals/campaign_form_import.html', context=context)

    except Campaign.DoesNotExist:
        return HttpResponse("Campaign not found", status=500)


@login_required
def data_mapper(request, pk=None):
    tenant = current_tenant.get()

    if request.method == "POST":
        mapping = []
        print(request.POST)

        campaign_pk = request.POST.get("campaign_pk")
        try:
            campaign = Campaign.objects.get(pk=campaign_pk, tenant=tenant)

        except Campaign.DoesNotExist:
            return HttpResponse("Campaign not found", status=500)

        for f in request.POST:
            if f.startswith("map"):
                if request.POST.get(f) != "fixed_value":

                    print(f'Campo: {f} ----> {request.POST[f]}')
                    if len(f.split("-")) > 3:
                        req_type = f.split("-")[2]
                        req_var = f.split("-")[3]

                        map_item = {
                            "template_element": req_type,
                            "template_var": req_var,
                            "target_field": request.POST[f],
                            "type": f.split("-")[1],
                        }
                    else:
                        req_var = f.split("-")[2]
                        map_item = {
                            # "template_element": req_type,
                            "template_var": req_var,
                            "target_field": request.POST[f],
                            "type": f.split("-")[1],
                        }
                    mapping.append(map_item)

        contact_name_map = {
            "template_var": "contact_name",
            "target_field": request.POST.get("contact-name-field", ""),
            "type": "variable"
        }
        mapping.append(contact_name_map)

        campaign.config["message"]["map"] = mapping

        campaign.save(update_fields=["config"])

        context = {
            "phase": "finish",
            "config": campaign.config
        }

        # return render(request, template_name='campaigns/partials/data_import_confirmation.html', context=context)
        return redirect("campaigns:campaign-configure", pk=campaign.pk)

    else:
        tenant = current_tenant.get()
        try:
            if pk is None:
                pk = request.GET.get("pk")

            campaign = Campaign.objects.get(pk=pk, tenant=tenant)

            context = {
                "campaign": campaign,
                "requirements": campaign.config["message"]["template_requirements"],
                "columns": campaign.config["data"].get("headers", [])
            }

            return render(request, template_name='campaigns/partials/data_import_mapper.html', context=context)

        except Campaign.DoesNotExist:
            return HttpResponse("Campaign not found", status=500)


@login_required
def campaign_scheduler(request, pk=None):
    tenant = current_tenant.get()

    if pk is None:
        pk = request.POST.get("campaign_pk")

    try:
        campaign = Campaign.objects.get(pk=pk, tenant=tenant)

    except Campaign.DoesNotExist:
        return HttpResponse("Campaign not found", status=500)

    if request.method == "POST":
        date_scheduled = request.POST.get("date")
        campaign.config["schedule"]["date"] = date_scheduled
        campaign.status = Status.SCHEDULED
        campaign.save(update_fields=["config", "status"])

        job = execute_campaign.apply_async(
            args=[str(campaign.pk)],
        )

        context = {
            "jobs": [job.id],
            "campaign_pk": campaign.pk
        }

        return render(request, template_name='campaigns/modals/campaing_execution_monitor.html', context=context)

    else:

        context = {
            "campaign": campaign,
        }
        return render(request, template_name='campaigns/modals/campaign_scheduler.html', context=context)


@login_required
def whatsapp_log(request, pk=None):
    tenant = current_tenant.get()
    try:
        campaign_data = CampaignData.objects.filter(campaign__id=pk)

        # Collect ids and also map cdo extras
        msg_ids = []
        cdo_map = {}  # msg_id -> cdo extra data
        for cdo in campaign_data:
            result = cdo.result
            if result:
                msg_log = result.get("messages", None)

                if msg_log:
                    wa_id = msg_log[0].get("id", None)
                    contact_number = result.get("contacts")[0].get("input", None)

                    if wa_id:
                        msg_ids.append(wa_id)
                        cdo_map[wa_id] = {
                            "cdo_id": cdo.id,
                            "variables": cdo.variables,
                            "result": cdo.result,
                            "contact_number": contact_number
                        }

    except CampaignData.DoesNotExist:
        return HttpResponse("Campaign not found", status=500)

    qs = (
        WaMessageLog.objects.filter(tenant=tenant, msg_id__in=msg_ids)
        .values("msg_id")
        .annotate(
            sent_time=Max(
                Case(When(status="sent", then="timestamp"),
                     output_field=DateTimeField())
            ),
            delivered_time=Max(
                Case(When(status="delivered", then="timestamp"),
                     output_field=DateTimeField())
            ),
            read_time=Max(
                Case(When(status="read", then="timestamp"),
                     output_field=DateTimeField())
            ),
            failed_time=Max(
                Case(
                    When(status__in=["failed", "error"], then="timestamp"),
                    output_field=DateTimeField(),
                )
            ),
        )
    )

    # Merge with cdo extras
    message_logs = []
    for entry in qs:

        msg_id = entry["msg_id"]
        entry["contact_number"] = cdo_map.get(msg_id)["contact_number"]
        entry["cdo"] = cdo_map.get(msg_id)  # attach CampaignData info

        message_logs.append(entry)

    context = {
        "message_logs": message_logs
    }

    return render(request, template_name='campaigns/partials/message_logs.html', context=context)


@login_required
def campaign_task_monitor(request, job_id: str):

    if request.method == "GET":

        result = AsyncResult(job_id, app=app)

        print(f"resultado: {result.result}")

        context = {
            "campaign_pk": request.GET.get("campaign_pk", None),
            "job_id": job_id,
            "status": result.status,  # e.g. PENDING, STARTED, SUCCESS, FAILURE, RETRY
            "ready": result.ready(),  # True if finished
            "successful": result.successful() if result.ready() else None,
            # "result": result.result if result.ready() else None,  # return value or exception
        }

        return render(request, template_name='campaigns/partials/_job_status_panel.html', context=context)
