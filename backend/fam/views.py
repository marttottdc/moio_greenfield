import ast

import base64
import json
import os
from io import BytesIO

import pandas as pd
from django.contrib.admin.views.decorators import staff_member_required
from django.template.defaultfilters import slugify
from django.template.response import TemplateResponse
from django.views.decorators.http import require_http_methods
from reportlab.lib.utils import ImageReader
from user_agents import parse

from django.contrib.auth.decorators import login_required

from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from django.conf import settings
from fam.core.assets_data import get_asset_markers, create_labels

from fam.core.render import render_label_with_stored_qr
from fam.forms import AssetRecordForm, ExcelUploadForm, FamAssetTypeForm, AssetPolicyForm
from fam.models import AssetRecord, AssetScanDetails, AssetPolicy, FamLabel, FamAssetType, FamAssetBrand, FamAssetModel, \
    LabelLayout
from fam.tasks import process_received_scan
from portal.context_utils import current_tenant
from portal.core.tools import generate_cookie_value

from fam.models import LabelPrintFormat

import logging

logger = logging.getLogger(__name__)


@login_required()
def fam(request):
    assets = AssetRecord.objects.all()
    labels = FamLabel.objects.all()
    context = {
        'assets': assets,
        'labels': labels
    }
    partial_template = 'fam/fam.html'
    if request.headers.get("HX-Request") == "true":
        return render(request, partial_template, context=context)
    else:
        context['partial_template'] = partial_template
        return render(request, 'layout.html', context=context)


@login_required
def create_asset(request):
    if request.method == 'POST':
        pass

    elif request.method == 'GET':
        form = AssetRecordForm()

        return render(request, 'fam/partials/asset_form.html', {"form": form})


@login_required
def dashboard(request):

    context = {
        "scan_details_count": AssetScanDetails.objects.filter().count(),
        "asset_records": AssetRecord.objects.all(),
        "asset_count": AssetRecord.objects.count(),
        "markers": get_asset_markers(),
        "GOOGLE_MAPS_API_KEY": None,
        }

    return render(request, "fam/dashboard.html", context=context)


@login_required
def asset_admin(request):

    fam_assets = AssetRecord.objects.all()
    if request.htmx:
        return render(request, template_name='fam/partials/asset_record_table.html',
                      context={"fam_assets": fam_assets})
    else:
        return render(request, template_name='fam/asset_admin.html', context={"fam_assets": fam_assets})


@login_required()
def tag_admin(request):

    fam_labels = FamLabel.objects.all()
    context = {
        "fam_labels": fam_labels
    }

    return render(request, template_name='fam/partials/fam_label_table.html', context=context )


def asset_details(request, fam_label_id):

    user_agent = parse(request.META.get('HTTP_USER_AGENT', ''))
    browser_family = user_agent.browser.family
    browser_version = user_agent.browser.version_string
    device_family = user_agent.device.family
    is_mobile = user_agent.is_mobile
    ip_address = request.META.get('REMOTE_ADDR')

    my_cookie = request.COOKIES.get('fam_cookie')
    if not my_cookie:
        my_cookie = generate_cookie_value()

    if request.method == "POST":
        latitude = request.POST.get("latitude")
        longitude = request.POST.get("longitude")
        error_message = request.POST.get("error_message")
        if latitude:
            latitude = float(latitude)
        if longitude:
            longitude = float(longitude)

        scan_event = AssetScanDetails.objects.create(
            scanned_by=request.user.username,
            latitude=latitude,
            longitude=longitude,
            received_date=timezone.now(),
            label_id=fam_label_id,
            remote_ip=ip_address,
            info=f'cookie:{my_cookie}, browser:{browser_family}, version:{browser_version}, mobile:{is_mobile}, device_family:{device_family}'
        )
        scan_event.save()

        return render(request, template_name="fam/partials/scan_detected.html", context={"latitude": latitude, "longitude": longitude, "error_message": error_message})

    else:
        label = FamLabel.objects.get(id__exact=fam_label_id)
        response = render(request, 'fam/asset_details.html', context={'label': label})
        response.set_cookie('fam_cookie', my_cookie)

        return response


@csrf_exempt
def asset_scan_log(request):
    if request.method == "GET":
        return HttpResponseBadRequest()
    elif request.method == "POST":
        try:
            content_type = request.content_type
            if content_type == 'application/json':
                print(content_type)
                try:
                    body_data = json.loads(request.body)
                    print("Payload received")

                    job = process_received_scan.apply_async(args=(body_data,), queue=settings.LOW_PRIORITY_Q)
                    print(f"Sent to worker in job: {job.id}")

                    # Process JSON data
                except json.JSONDecodeError:
                    # Handle JSON decoding error
                    print("Error Decoding Json")

            elif content_type == 'application/x-www-form-urlencoded':
                # Process form data
                body_data = request.POST
                print('application/x-www-form-urlencoded')
                # Access form data using body_data dictionary

            elif content_type.startswith('multipart/form-data'):
                # Process multipart/form-data
                # Access uploaded files and form data using request.FILES and request.POST
                print('multipart/form-data')
            else:
                print(f'Dont know how to handle {content_type}')

            # Enqueue the task to Celery
            # mr is a function in message_worker module that handles the body
            return HttpResponse("EVENT_RECEIVED", status=200)
        except Exception as e:
            print(e)
            return HttpResponseBadRequest()


@login_required
def asset_import(request):

    if request.method == 'POST':
        form = ExcelUploadForm(request.POST, request.FILES)

        if form.is_valid():
            file = request.FILES['file']
            df = pd.read_excel(file)
            preload_table = df.to_dict(orient='records')
            column_names = df.columns.to_list

            for index, row in df.iterrows():

                try:
                    asset_type = FamAssetType.objects.get(name=row['type'])
                except FamAssetType.DoesNotExist:
                    asset_type = None

                if row.get('active', '0') == '1':
                    active = True
                else:
                    active = False

                if row.get('compliant', '') == '1':
                    compliant = True
                else:
                    compliant = False

                asset_record = {
                    "serial_number": row['serial_number'],
                    "brand": row.get('brand', ''),
                    "model": row.get('model', ''),
                    "type": asset_type,
                    "name": row.get('name', ''),
                    "purchase_date": timezone.make_aware(row.get('purchase_date', '')),
                    "created_date": timezone.now(),
                    "last_seen": timezone.now().timestamp(),
                    "status": row.get('status', ''),
                    "comment": row.get('comment', ''),
                    "owner_company": row.get('owner_company', ''),
                    "asset_image": row.get('asset_image', ''),
                    "active": active,
                    "compliant": compliant,
                    "tenant": current_tenant.get(),
                    "last_location": row.get('last_location', ''),
                    "last_known_latitude": row.get('last_known_latitude', 0),
                    "last_known_longitude": row.get('last_known_longitude', 0)
                }

                try:
                    new_asset = AssetRecord.objects.get(serial_number=row['serial_number'])
                    new_asset.update(**asset_record)

                except AssetRecord.DoesNotExist:
                    new_asset = AssetRecord.objects.create(**asset_record)

                new_asset.save()
                print(new_asset)

            return render(request, 'fam/partials/import_form.html', {'table_headers': column_names, 'preload_table': preload_table})

    else:
        form = ExcelUploadForm()

        return render(request, 'fam/partials/import_form.html', {'form': form})


@login_required
def batch_create_labels(request):
    tenant = current_tenant.get()

    if request.method == 'POST':

        prefix = request.POST.get('prefix', '')
        digits = int(request.POST.get('digits', '0'))
        quantity = int(request.POST.get('quantity', '0'))

        create_labels(prefix=prefix, digits=digits, quantity=quantity, tenant=tenant)

    labels = FamLabel.objects.all().order_by('-created')

    return render(request=request, template_name="fam/modals/qr_tags_creation_form.html", context={"fam_labels": labels})


@login_required
def print_labels(request):
    if request.method == "POST":
        labels_to_print = request.POST.getlist("label_id")

        if not labels_to_print:
            return HttpResponseBadRequest("No labels selected")
        from fam.models import LabelPrintFormat
        formats = LabelPrintFormat.objects.all().order_by("name")
        return render(
            request,
            'fam/modals/label_print_format_selector.html',
            {"labels_to_print": labels_to_print, "formats": formats}
        )


@login_required
def fam_label_template_preview(request):

    if request.method == "POST":
        base64_logo = None
        if 'image' in request.FILES:
            logo = request.FILES['image']
            file_content_type = logo.content_type

            # Read the file content
            file_content = logo.read()

            # Encode the file content to base64
            encoded_logo = base64.b64encode(file_content).decode('utf-8')
            base64_logo = f'data:{file_content_type};base64,{encoded_logo}'

        template_id = request.POST.get('template_id')
        custom_message = request.POST.get('custom_message')
        sample_label_id = request.POST.get('sample_label_id')

        labels_to_print_list = ast.literal_eval( request.POST.getlist("labels_to_print")[0])

        labels_to_print = FamLabel.objects.filter(id__in=labels_to_print_list)

        context = {"template_id": template_id, "labels_to_print": labels_to_print, "preview_image": base64_logo, "custom_message": custom_message}
        return render(request, 'fam/partials/fam_label_templates.html', context=context)


@login_required
def fam_label_filter(request):
    if request.method == "POST":
        search_term = request.POST.get('search')
        filtered_labels = FamLabel.objects.filter(company_tag__icontains=search_term).order_by('-created')
        return render(request=request, template_name="fam/partials/fam_label_table.html", context={"fam_labels": filtered_labels})


@login_required
def generate_pdf(request):
    pass


@login_required
def brand_crud(request, brand_id=None):
    if request.method == "POST":

        return render(request, template_name='fam/cruds/modal_factory.html')

    else:
        asset_brands=FamAssetBrand.objects.all()
        context = {"asset_brands": asset_brands}
        return render(request, template_name='fam/cruds/modal_factory.html', context=context)


@login_required
def asset_type_crud(request, id=None):

    tenant = current_tenant.get()

    if request.method == "POST":

        if id is None:
            new_type = FamAssetTypeForm(request.POST)
            if new_type.is_valid():
                new_type.save()

        else:
            target_type = FamAssetType.objects.get(id=id)
            form = FamAssetTypeForm(request.POST, instance=target_type)
            if form.is_valid():
                form.save()
            else:
                print(form.errors)

        asset_types = FamAssetType.objects.all()
        context = {"asset_types": asset_types}
        return render(request, template_name='fam/cruds/types_table.html', context=context)

    else:
        if request.method == 'GET':

            if request.GET.get("action") =="add":
                form = FamAssetTypeForm(initial={"tenant": tenant})
                context = {
                    "form": form,
                }

                return render(request, template_name='fam/cruds/asset_type_form.html', context=context)

            if request.GET.get("action") == "edit" and id is not None:

                type_to_edit = FamAssetType.objects.get(id=id)
                form = FamAssetTypeForm(instance=type_to_edit)

                context = {
                    "form": form,
                    "id": id
                }
                return render(request, template_name='fam/cruds/asset_type_form.html', context=context)
            else:
                asset_types = FamAssetType.objects.all()
                context = {"asset_types": asset_types}

            return render(request, template_name='fam/cruds/types_table.html', context=context)


@login_required
def policy_crud(request, id=None):

    tenant = current_tenant.get()

    if request.method == "POST":

        if id is None:
            new_item = AssetPolicy(request.POST)
            if new_item.is_valid():
                new_item.save()

        else:
            target_item = AssetPolicy.objects.get(id=id)
            form = AssetPolicyForm(request.POST, instance=target_item)
            if form.is_valid():
                form.save()
            else:
                print(form.errors)

        item_list = AssetPolicy.objects.all()
        context = {"item_list": item_list}
        return render(request, template_name='fam/cruds/policies_table.html', context=context)

    else:
        if request.method == 'GET':

            if request.GET.get("action") == "add":
                form = AssetPolicyForm(initial={"tenant": tenant})
                context = {
                    "form": form,
                }

                return render(request, template_name='fam/cruds/asset_policy_form.html', context=context)

            if request.GET.get("action") == "edit" and id is not None:

                target_item = AssetPolicy.objects.get(id=id)
                form = AssetPolicyForm(instance=target_item)

                context = {
                    "form": form,
                    "id": id
                }
                return render(request, template_name='fam/cruds/policies_table.html', context=context)
            else:
                item_list = AssetPolicy.objects.all()
                context = {"item_list": item_list}

            return render(request, template_name='fam/cruds/policies_table.html', context=context)


@login_required
def refresh_kpis(request):

    return render(request, template_name='fam/partials/header_kpis.html')


@login_required
def list_assets(request):
    tenant = current_tenant.get()
    if request.user.is_superuser and settings.DEBUG:
        assets = AssetRecord.objects.all().order_by('name')
    else:
        assets = AssetRecord.objects.filter(tenant=tenant).order_by('name')

    context = {"assets": assets}

    return render(request, template_name='fam/partials/list_assets.html', context=context)


@login_required
def assign_label(request, id):
    tenant = current_tenant.get()
    vacant_assets = AssetRecord.objects.filter(label__isnull=True, tenant=tenant).order_by('name')

    try:
        label = FamLabel.objects.get(pk=id)

        if request.method == "GET":
            context = {
                "vacant_assets": vacant_assets,
                "label": label
            }

            return render(request, template_name='fam/modals/assign_label_form.html', context=context)

    except FamAssetType.DoesNotExist:
        logger.error("Label does not exist")


@require_http_methods(["GET", "POST"])
def print_format_preview(request):
    """
    Preview a LabelPrintFormat using sample_code as QR content (no DB label needed).
    """
    fmt_id = request.POST.get("format_id") or request.GET.get("format_id")
    if not fmt_id:
        return HttpResponseBadRequest("format_id required")
    fmt = LabelPrintFormat.objects.get(pk=fmt_id)

    # Build a synthetic QR image from sample_code (re-use your FamLabel QR style if needed)
    import qrcode
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4
    )
    qr.add_data(fmt.sample_code)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Render with layout using the synthetic QR
    im = render_label_with_stored_qr(
        layout_key=fmt.layout_key,
        width_mm=float(fmt.width_mm),
        height_mm=float(fmt.height_mm),
        dpi=int(fmt.dpi),
        main_text=(fmt.main_text or "").replace("{{ code }}", fmt.sample_code),
        code_text=(fmt.code_text or "").replace("{{ code }}", fmt.sample_code),
        qr_img=qr_img,
        bleed_mm=float(fmt.bleed_mm),
    )

    # return small fragment with base64
    buf = BytesIO(); im.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return TemplateResponse(request, "fam/partials/print_format_preview.html", {"img_data": img_b64})


@login_required
def print_format_configuration(request):
    """
    List formats on the left; form (create/edit) + live preview on the right.
    """
    tenant = current_tenant.get()
    formats = LabelPrintFormat.objects.filter(tenant=tenant)
    # pick selected format or default blank
    # fmt_id = request.GET.get("id")
    selected = None
    #if fmt_id:
    #    selected = get_object_or_404(LabelPrintFormat, pk=fmt_id)

    layouts = LabelLayout.objects.filter(tenant=tenant)
    ctx = {
        "formats": formats,
        "selected": selected,
        "layouts": layouts
    }
    return render(request, "fam/modals/print_format_modal.html", context=ctx)


@login_required
def label_designer(request):
    tenant = current_tenant.get()

    if request.method == "GET":
        # JSON fetch for a specific layout
        layout_id = request.GET.get("id")
        wants_json = "application/json" in (request.headers.get("Accept", "") or "")
        if layout_id and wants_json:
            layout = get_object_or_404(LabelLayout, pk=layout_id, tenant=tenant)
            payload = layout.elements or {}
            # Ensure dict
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            # Return the fractional JSON expected by the renderer, plus name/id/description
            payload.update({
                "name": layout.key,
                "id": str(layout.pk),
                "description": layout.description or "",
            })
            return JsonResponse(payload, status=200)

        # Default: render modal with list
        layouts = LabelLayout.objects.filter(tenant=tenant).only("id", "key").order_by("key")
        return render(request, "fam/modals/label_designer_modal_mm.html", {
            "available_layouts": layouts,
        })

    # POST: create / save
    action = (request.POST.get("action") or "").strip().lower()
    if action not in {"create", "save"}:
        return JsonResponse({"error": "Invalid or missing action"}, status=400)

    # Common: parse layout_json
    raw_layout = request.POST.get("layout_json") or "{}"
    try:
        elements = json.loads(raw_layout)
    except Exception as e:
        logger.exception("Invalid layout_json")
        return JsonResponse({"error": "Invalid layout_json (must be JSON)"}, status=400)

    if action == "create":
        name = (request.POST.get("name") or "").strip()
        if not name:
            return JsonResponse({"error": "name is required"}, status=400)
        description = (request.POST.get("description") or "").strip()
        obj = LabelLayout.objects.create(
            tenant=tenant,
            key=name,
            description=description,
            elements=elements,
        )
        # Return id so the client won’t prompt again on next save
        return JsonResponse({"id": str(obj.pk), "name": obj.key}, status=201)

    # action == "save"
    obj_id = (request.POST.get("id") or "").strip()
    if not obj_id:
        return JsonResponse({"error": "id is required for save"}, status=400)
    obj = get_object_or_404(LabelLayout, pk=obj_id, tenant=tenant)
    obj.elements = elements
    # If you track updated timestamps, you can use update_fields to avoid touching other columns
    obj.save(update_fields=["elements"])
    return HttpResponse(status=204)


