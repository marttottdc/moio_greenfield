import base64
import io
import json
from io import BytesIO
from typing import Dict, Iterable, List, Tuple

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from portal.context_utils import current_tenant
from fam.models import FamLabel, LabelLayout, LabelPrintFormat

from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4, LETTER, landscape

from fam.core.render import render_label_with_stored_qr, mm_to_pt, mm_to_px, _qr_from_text

# ====== LAYOUT PICKER (modal) ==================================================


@login_required
@require_GET
def layout_picker(request):
    tenant = current_tenant.get()
    db_layouts = LabelLayout.objects.filter(tenant=tenant).only("key").order_by("key")

    ctx = {
        "layouts": [(obj.key, None) for obj in db_layouts],
        "current": request.GET.get("current") or "",
        "target_input_id": request.GET.get("target") or "layout_key",
        "sample_code": request.GET.get("sample_code") or "SAMPLE-001",
        "main_text": request.GET.get("main_text") or "Control de Activos",
        "code_text": request.GET.get("code_text") or "{{ code }}",
        "width_mm": float(request.GET.get("width_mm") or 60),
        "height_mm": float(request.GET.get("height_mm") or 60),
        "dpi": int(request.GET.get("dpi") or 300),
    }
    return render(request, "fam/modals/layout_picker.html", ctx)


@login_required
@require_GET
def layout_preview_png(request):
    """
    Returns a PNG preview for a layout key and physical size at a given DPI.
    GET params: layout, width_mm, height_mm, dpi, code, main_text, code_text, bleed_mm (optional)
    """
    layout_key = (request.GET.get("layout") or "").strip()
    width_mm = float(request.GET.get("width_mm") or 60)
    height_mm = float(request.GET.get("height_mm") or 60)
    bleed_mm = float(request.GET.get("bleed_mm") or 0)
    dpi = int(request.GET.get("dpi") or 300)

    code = request.GET.get("code") or "SAMPLE-001"
    main_text = request.GET.get("main_text") or "Control de Activos"
    code_text_tpl = request.GET.get("code_text") or "{{ code }}"
    code_text = (code_text_tpl or "{{ code }}").replace("{{ code }}", code)

    # Create a temporary QR for preview
    qr_img = _qr_from_text(code, size_px=max(100, mm_to_px(min(width_mm, height_mm) * 0.6, dpi)))

    # Let your renderer resolve the layout by key (DB-stored layout expected)
    label_im = render_label_with_stored_qr(
        layout_key=layout_key,
        width_mm=width_mm,
        height_mm=height_mm,
        dpi=dpi,
        main_text=main_text,
        code_text=code_text,
        qr_img=qr_img,
        bleed_mm=bleed_mm,
    )

    buf = BytesIO()
    label_im.save(buf, format="PNG")
    return HttpResponse(buf.getvalue(), content_type="image/png")


# ====== PRINT FORMAT CONFIG (modal) ============================================

def get_label_fields():
    # all concrete fields except relations/images if you want
    return [
        f.name for f in FamLabel._meta.get_fields()
        if f.concrete and not f.is_relation and f.name not in ("qr_code", "tenant", "created", "id", )
    ]


def get_text_elements(layout_json: str):
    try:
        layout = json.loads(layout_json)
        return [item for item in layout.get("items", []) if item.get("type") == "text"]
    except Exception as e:
        print(e)
        return []


@login_required
@require_GET
def print_format_configuration(request):
    """
    Render the 'Print Formats' modal with the list and a selected item (if any).
    GET:
      - id (optional): selected format id
    """
    tenant = current_tenant.get()
    available_fields = get_label_fields()
    formats = LabelPrintFormat.objects.filter(tenant=tenant).order_by("name")
    selected = None
    label_layout = None
    sel_id = (request.GET.get("id") or "").strip()

    if sel_id:
        if sel_id == "new":
            print("New")
        else:
            try:
                selected = formats.get(pk=sel_id)
                label_layout = request.GET.get("layout_key", selected.layout_key)
            except LabelPrintFormat.DoesNotExist:
                selected = None

    layout_items = []
    if selected and label_layout:
        try:
            layout_obj = LabelLayout.objects.get(tenant=tenant, key=label_layout)
        except LabelLayout.DoesNotExist:
            layout_obj = None

        if layout_obj:
            layout_items = layout_obj.elements["items"]

    db_layout_keys = list(
        LabelLayout.objects.filter(tenant=tenant).values_list("key", flat=True).order_by("key")
    )
    layout_keys = db_layout_keys  # no builtin merge anymore

    ctx = {
        "formats": formats,
        "available_fields": available_fields,
        "layout_items": layout_items,
        "selected": selected,
        "layouts": layout_keys,
        "code": (selected.sample_code if selected else "SAMPLE-001"),
        "mappings": selected.mappings if selected else {},
    }

    return render(request, "fam/modals/print_format_modal.html", ctx)


@login_required
@require_POST
def print_format_save(request):
    """
    Create or update a LabelPrintFormat.
    POST body = fields from the modal form.
    Returns the modal HTML again, with the saved/selected format.
    """
    tenant = current_tenant.get()
    data = request.POST

    fields = {
        "name": data.get("name", "").strip(),
        "layout_key": data.get("layout_key", "").strip(),
        "width_mm": float(data.get("width_mm") or 60),
        "height_mm": float(data.get("height_mm") or 60),
        "dpi": int(data.get("dpi") or 300),
        "bleed_mm": float(data.get("bleed_mm") or 0),
        "page": data.get("page") or "A4",
        "orient": data.get("orient") or "portrait",
        "cols": int(data.get("cols") or 3),
        "rows": int(data.get("rows") or 8),
        "cell_w_mm": float(data.get("cell_w_mm") or 70),
        "cell_h_mm": float(data.get("cell_h_mm") or 37),
        "gap_x_mm": float(data.get("gap_x_mm") or 2),
        "gap_y_mm": float(data.get("gap_y_mm") or 2),
        "margin_mm": float(data.get("margin_mm") or 5),

        "main_text": data.get("main_text") or "Control de Activos",
        "code_text": data.get("code_text") or "{{ code }}",
        "sample_code": data.get("sample_code") or "SAMPLE-001",
    }

    pf_id = (data.get("id") or "").strip()
    try:
        if pf_id:
            obj = get_object_or_404(LabelPrintFormat, pk=pf_id, tenant=tenant)
            for k, v in fields.items():
                setattr(obj, k, v)
            obj.save()
        else:
            obj = LabelPrintFormat.objects.create(tenant=tenant, **fields)

        # Re-render modal with this one selected
        request.GET = request.GET.copy()
        request.GET["id"] = str(obj.pk)
        return print_format_configuration(request)

    except IntegrityError as e:
        return JsonResponse({"error": f"Integrity error: {e}"}, status=409)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_POST
def print_format_delete(request):
    tenant = current_tenant.get()
    pf_id = (request.POST.get("id") or "").strip()
    if not pf_id:
        return JsonResponse({"error": "id is required"}, status=400)

    obj = get_object_or_404(LabelPrintFormat, pk=pf_id, tenant=tenant)
    obj.delete()

    # Re-render list with no selected item
    return print_format_configuration(request)


@login_required
@require_GET
def print_format_preview_png(request):
    """
    PNG preview used inside the Print Format modal (<img id="pf_preview">).
    It obeys the same query params as the form fields.
    """
    layout_key = (request.GET.get("layout_key") or "").strip()
    width_mm = float(request.GET.get("width_mm") or 60)
    height_mm = float(request.GET.get("height_mm") or 60)
    bleed_mm = float(request.GET.get("bleed_mm") or 0)
    dpi = int(request.GET.get("dpi") or 300)
    code = request.GET.get("sample_code") or "SAMPLE-001"
    main_text = request.GET.get("main_text") or "Control de Activos"
    code_text_tpl = request.GET.get("code_text") or "{{ code }}"
    code_text = code_text_tpl.replace("{{ code }}", code)

    qr_img = _qr_from_text(code, size_px=max(100, mm_to_px(min(width_mm, height_mm) * 0.6, dpi)))

    label_im = render_label_with_stored_qr(
        layout_key=layout_key,
        width_mm=width_mm,
        height_mm=height_mm,
        dpi=dpi,
        main_text=main_text,
        code_text=code_text,
        qr_img=qr_img,
        bleed_mm=bleed_mm,
    )
    buf = BytesIO()
    label_im.save(buf, format="PNG")

    # If called by HTMX, return an HTML snippet (nice div + <img> with data URI)
    if request.headers.get("HX-Request") == "true":

        png_bytes = buf.getvalue()
        b64 = base64.b64encode(png_bytes).decode("ascii")

        html = f"""
            <div id="pf_preview"
              <img  class="img-fluid border shadow-sm" alt="preview" src="data:image/png;base64,{b64}">
              <div class="small text-muted mt-1">
                {width_mm:g}×{height_mm:g} mm @ {dpi} DPI • {layout_key}
              </div>
            </div>
            """

        resp = HttpResponse(html, content_type="text/html; charset=utf-8")
        resp["Cache-Control"] = "no-store"
        return resp

    else:

        return HttpResponse(buf.getvalue(), content_type="image/png")


# ====== PRINT (PDF) ============================================================


def _page_size(page: str, orient: str):
    base = {"A4": A4, "Letter": LETTER}.get(page, A4)
    return landscape(base) if orient == "landscape" else base


@login_required
@require_POST
def print_labels_with_format_pdf(request):
    """
    Builds a PDF with one or many labels using a selected LabelPrintFormat.
    POST form (see templates/fam/modals/label_print_format_selector.html):
      - format_id: LabelPrintFormat pk
      - label_id: repeated (one or many) — FamLabel pks
      - auto_sheet: "1" if auto-detect sheet usage
      - sheet: "1" to force grid usage (when auto_sheet unchecked)
    """
    tenant = current_tenant.get()
    fmt = get_object_or_404(LabelPrintFormat, pk=request.POST.get("format_id"), tenant=tenant)

    label_ids = request.POST.getlist("label_id")
    labels = list(FamLabel.objects.filter(pk__in=label_ids, tenant=tenant))

    # Decide whether to place on a sheet grid
    auto_sheet = request.POST.get("auto_sheet") == "1"
    force_sheet = request.POST.get("sheet") == "1"
    use_sheet = force_sheet or (auto_sheet and (len(labels) > 1 or (fmt.cols * fmt.rows) > 1))

    # Prepare PDF
    pagesize = _page_size(fmt.page, fmt.orient)
    resp = HttpResponse(content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="labels.pdf"'
    c = rl_canvas.Canvas(resp, pagesize=pagesize)

    # Compute grid/cell in points
    margin_pt = mm_to_pt(float(fmt.margin_mm))
    gap_x_pt = mm_to_pt(float(fmt.gap_x_mm))
    gap_y_pt = mm_to_pt(float(fmt.gap_y_mm))
    cell_w_pt = mm_to_pt(float(fmt.cell_w_mm))
    cell_h_pt = mm_to_pt(float(fmt.cell_h_mm))

    page_w, page_h = pagesize

    def draw_label_at(x_pt: float, y_pt: float, pil_img: Image.Image):
        buf = BytesIO()
        pil_img.save(buf, format="PNG")
        buf.seek(0)
        c.drawImage(Image.open(buf), x_pt, y_pt, width=cell_w_pt, height=cell_h_pt, preserveAspectRatio=True, mask='auto')

    # Iterate labels and place either single per page or on the grid
    col = row = 0
    for lbl in labels:
        code = lbl.company_tag or str(lbl.id)
        code_text = (fmt.code_text or "{{ code }}").replace("{{ code }}", code)

        # open stored QR (fallback to generated if missing)
        try:
            qr_field = lbl.qr_code
            qr_img = Image.open(qr_field).convert("RGB") if qr_field and getattr(qr_field, "path", None) else _qr_from_text(code)
        except Exception:
            qr_img = _qr_from_text(code)

        # Render single label image with current format sizing
        label_im = render_label_with_stored_qr(
            layout_key=fmt.layout_key,
            width_mm=float(fmt.width_mm),
            height_mm=float(fmt.height_mm),
            dpi=int(fmt.dpi),
            main_text=fmt.main_text or "Control de Activos",
            code_text=code_text,
            qr_img=qr_img,
            bleed_mm=float(fmt.bleed_mm or 0),
        )

        if use_sheet:
            # Calculate top-left origin for this cell
            x = margin_pt + col * (cell_w_pt + gap_x_pt)
            # ReportLab origin is bottom-left
            y = page_h - margin_pt - (row + 1) * cell_h_pt - row * gap_y_pt
            draw_label_at(x, y, label_im)

            # advance grid pos
            col += 1
            if col >= int(fmt.cols):
                col = 0
                row += 1
            if row >= int(fmt.rows):
                # new page if grid filled
                c.showPage()
                row = col = 0
        else:
            # single label centered on page
            x = (page_w - cell_w_pt) / 2.0
            y = (page_h - cell_h_pt) / 2.0
            draw_label_at(x, y, label_im)
            c.showPage()

    c.save()
    return resp


@require_POST
def layout_logo_upload(request, pk: int):

    tenant = current_tenant.get()
    layout = get_object_or_404(LabelLayout, pk=pk, tenant=tenant)
    f = request.FILES.get("file")
    if not f:
        return HttpResponseBadRequest("Missing 'file'")

    # Save directly; Django/storages writes the file and sets .url
    layout.logo.save(getattr(f, "name", "logo"), f, save=True)

    return JsonResponse({"url": layout.logo.url})
