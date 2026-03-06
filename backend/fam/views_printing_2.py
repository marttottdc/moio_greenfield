# views_printing.py

import math
from io import BytesIO
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST
from PIL import Image, ImageDraw

from portal.context_utils import current_tenant

from fam.models import FamLabel, LabelLayout, LabelPrintFormat
# quick QR (placeholder-friendly)
from PIL import Image, ImageDraw
from fam.core.render import render_label_with_stored_qr


# --- ADD this import block near your other ReportLab imports ---
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4, LETTER, landscape
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import Color


# ---------- Units & helpers ----------
def mm_to_px(mm_val: float, dpi: int) -> int:
    return int(round(mm_val * dpi / 25.4))


def mm_to_pt(mm_val: float) -> float:
    return (mm_val / 25.4) * 72.0


def _resample():
    try:    return Image.Resampling.LANCZOS
    except: return Image.LANCZOS


def _qr_from_text(data: str, size_px: int = 300) -> Image.Image:
    try:
        import qrcode
        qr = qrcode.QRCode(border=1, box_size=max(2, size_px // 60))
        qr.add_data(data or "")
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        return img
    except Exception:
        img = Image.new("RGB", (size_px, size_px), "white")
        d = ImageDraw.Draw(img)
        pad = size_px // 12
        d.rectangle([pad, pad, size_px - pad, size_px - pad], outline="black", width=3)
        d.rectangle([pad * 2, pad * 2, size_px - pad * 2, size_px - pad * 2], fill="black")
        return img


# physical page sizes in millimeters
PAGE_MM = {
    "A4": (210.0, 297.0),
    "Letter": (215.9, 279.4),  # 8.5 × 11 in
}


def _page_size(page: str, orient: str):
    base = {"A4": A4, "Letter": LETTER}.get(page, A4)
    return landscape(base) if orient == "landscape" else base



# use the centralized renderer (you added it in fam/core/render.py)


@login_required
@require_GET
def layout_picker(request):
    tenant = current_tenant.get()
    db_layouts = LabelLayout.objects.filter(tenant=tenant).only("key").order_by("key")
    layouts = {obj.key: None for obj in db_layouts}
    for k in BUILTIN_LAYOUTS.keys():
        layouts.setdefault(k, None)

    ctx = {
        "layouts": sorted(layouts.items(), key=lambda kv: kv[0]),
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
    # still available if you need single-label preview
    layout_key = (request.GET.get("layout") or "").strip()
    width_mm = float(request.GET.get("width_mm") or 60)
    height_mm = float(request.GET.get("height_mm") or 60)
    bleed_mm = float(request.GET.get("bleed_mm") or 0)
    dpi = int(request.GET.get("dpi") or 300)

    code = request.GET.get("code") or "SAMPLE-001"
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
    return HttpResponse(buf.getvalue(), content_type="image/png")


@login_required
@require_GET
def print_format_configuration(request):
    tenant = current_tenant.get()
    formats = LabelPrintFormat.objects.filter(tenant=tenant).order_by("name")
    selected = None
    sel_id = (request.GET.get("id") or "").strip()
    if sel_id:
        try:
            selected = formats.get(pk=sel_id)
        except LabelPrintFormat.DoesNotExist:
            selected = None

    db_layout_keys = list(
        LabelLayout.objects.filter(tenant=tenant).values_list("key", flat=True).order_by("key")
    )
    layout_keys = sorted(set(db_layout_keys + list(BUILTIN_LAYOUTS.keys())))

    ctx = {
        "formats": formats,
        "selected": selected,
        "layouts": layout_keys,
        "code": (selected.sample_code if selected else "SAMPLE-001"),
    }
    return render(request, "fam/modals/print_format_modal.html", ctx)


@login_required
@require_POST
def print_format_save(request):
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
    if pf_id:
        obj = get_object_or_404(LabelPrintFormat, pk=pf_id, tenant=tenant)
        for k, v in fields.items():
            setattr(obj, k, v)
        obj.save()
    else:
        obj = LabelPrintFormat.objects.create(tenant=tenant, **fields)

    # re-render, selecting this one
    request.GET = request.GET.copy()
    request.GET["id"] = str(obj.pk)
    return print_format_configuration(request)


@login_required
@require_POST
def print_format_delete(request):
    tenant = current_tenant.get()
    pf_id = (request.POST.get("id") or "").strip()
    obj = get_object_or_404(LabelPrintFormat, pk=pf_id, tenant=tenant)
    obj.delete()
    return print_format_configuration(request)

# ==============================================================================
# NEW: WHOLE-PAGE PREVIEW (HTML wrapper + PNG)
# ==============================================================================

@login_required
@require_GET
def print_format_page_preview(request):
    """
    Returns a tiny HTML fragment containing an <img> pointing to the PNG preview.
    We do this so HTMX can swap the container without dealing with binary data.
    """
    # forward all GET params to the png endpoint
    qs = urlencode(dict(request.GET.items()))
    # cache-bust on each refresh (HTMX adds _ for us sometimes, but keep explicit)
    if qs:
        qs += "&_cb=1"
    else:
        qs = "_cb=1"

    src = f"{request.build_absolute_uri('/').rstrip('/')}/fam/formats/page_preview.png?{qs}"
    html = f"""
      <div class="ratio ratio-3x2 border rounded bg-white">
        <img src="{src}" alt="Page preview" class="img-fluid w-100 h-100 object-fit-contain"/>
      </div>
      <div class="small text-muted mt-1">Live preview — reflects page, margins, grid, and layout repeated in all cells.</div>
    """
    return HttpResponse(html, content_type="text/html; charset=utf-8")


@login_required
@require_GET
def print_format_page_preview_png(request):
    """
    Builds a PNG that shows the FULL PAGE (sheet) with grid and the selected layout
    repeated in each cell, scaled to fit. It honors page, orientation, margins,
    gaps, cell sizes, and bleed (applied to each label, not to the page).
    """
    # --- gather params ---
    layout_key = (request.GET.get("layout_key") or "").strip()
    page = (request.GET.get("page") or "A4")
    orient = (request.GET.get("orient") or "portrait")
    cols = int(request.GET.get("cols") or 3)
    rows = int(request.GET.get("rows") or 8)
    cell_w_mm = float(request.GET.get("cell_w_mm") or 70)
    cell_h_mm = float(request.GET.get("cell_h_mm") or 37)
    gap_x_mm = float(request.GET.get("gap_x_mm") or 2)
    gap_y_mm = float(request.GET.get("gap_y_mm") or 2)
    margin_mm = float(request.GET.get("margin_mm") or 5)

    # label content sizing (can differ from cell size)
    width_mm = float(request.GET.get("width_mm") or cell_w_mm)
    height_mm = float(request.GET.get("height_mm") or cell_h_mm)
    bleed_mm = float(request.GET.get("bleed_mm") or 0)

    # texts
    main_text = request.GET.get("main_text") or "Control de Activos"
    code_tpl = request.GET.get("code_text") or "{{ code }}"
    sample_code = request.GET.get("sample_code") or "SAMPLE-001"
    code_text = code_tpl.replace("{{ code }}", sample_code)

    # --- compute page mm ---
    base_w_mm, base_h_mm = PAGE_MM.get(page, PAGE_MM["A4"])
    if orient == "landscape":
        base_w_mm, base_h_mm = base_h_mm, base_w_mm

    # --- choose preview resolution (screen-friendly) ---
    LONG_PX = 1100  # target long edge in pixels
    long_mm = max(base_w_mm, base_h_mm)
    px_per_mm = LONG_PX / max(1.0, long_mm)
    page_w_px = int(round(base_w_mm * px_per_mm))
    page_h_px = int(round(base_h_mm * px_per_mm))

    # virtual DPI used to render each label so it fits the cell nicely
    vdpi = max(72, min(200, int(round(px_per_mm * 25.4))))

    # --- build base page image ---
    page_img = Image.new("RGB", (page_w_px, page_h_px), "white")
    d = ImageDraw.Draw(page_img)

    # draw page border
    d.rectangle([0, 0, page_w_px - 1, page_h_px - 1], outline="#CCCCCC", width=1)

    # content (printable) origin
    margin_px = int(round(margin_mm * px_per_mm))
    origin_x = margin_px
    origin_y = margin_px

    # draw margin rect
    d.rectangle(
        [origin_x, origin_y, page_w_px - margin_px - 1, page_h_px - margin_px - 1],
        outline="#B0B0B0", width=1
    )

    # precalc cell sizes in px
    cell_w_px = int(round(cell_w_mm * px_per_mm))
    cell_h_px = int(round(cell_h_mm * px_per_mm))
    gap_x_px = int(round(gap_x_mm * px_per_mm))
    gap_y_px = int(round(gap_y_mm * px_per_mm))

    # QR for sample code
    qr_img = _qr_from_text(sample_code, size_px=max(64, int(min(cell_w_px, cell_h_px) * 0.7)))

    # render one label at virtual DPI and reuse it
    try:
        label_im = render_label_with_stored_qr(
            layout_key=layout_key,
            width_mm=width_mm,
            height_mm=height_mm,
            dpi=vdpi,
            main_text=main_text,
            code_text=code_text,
            qr_img=qr_img,
            bleed_mm=bleed_mm,
        )
    except Exception:
        # fallback: plain white tile with border
        label_im = Image.new("RGB", (max(1, int(width_mm * px_per_mm)), max(1, int(height_mm * px_per_mm))), "white")
        d2 = ImageDraw.Draw(label_im)
        d2.rectangle([0, 0, label_im.width - 1, label_im.height - 1], outline="black", width=1)

    # paste labels across the grid, drawing light grid rectangles
    y = origin_y
    for r in range(max(1, rows)):
        x = origin_x
        for c in range(max(1, cols)):
            # cell rect
            cell_rect = [x, y, x + cell_w_px - 1, y + cell_h_px - 1]
            d.rectangle(cell_rect, outline="#E0E0E0", width=1)

            # fit label image inside the cell (preserve aspect)
            iw, ih = label_im.size
            ratio = min(cell_w_px / max(1, iw), cell_h_px / max(1, ih))
            nw = max(1, int(iw * ratio))
            nh = max(1, int(ih * ratio))
            ox = x + (cell_w_px - nw) // 2
            oy = y + (cell_h_px - nh) // 2

            tile = label_im.resize((nw, nh), _resample())
            page_img.paste(tile, (ox, oy))

            x += cell_w_px + gap_x_px
        y += cell_h_px + gap_y_px

    # tiny metadata footer (optional)
    footer = f"{page} {orient} — {cols}×{rows} | cell {cell_w_mm}×{cell_h_mm}mm, gap {gap_x_mm}/{gap_y_mm}mm | margin {margin_mm}mm"
    try:
        d.text((8, page_h_px - 16), footer, fill="#999")
    except Exception:
        pass

    # stream PNG
    buf = BytesIO()
    page_img.save(buf, format="PNG")
    return HttpResponse(buf.getvalue(), content_type="image/png")

# ==============================================================================
# PRINT (PDF) — unchanged from your previous integration (omitted for brevity)
# ==============================================================================

@login_required
@require_POST
def print_labels_with_format_pdf(request):
    tenant = current_tenant.get()
    fmt = get_object_or_404(LabelPrintFormat, pk=request.POST.get("format_id"), tenant=tenant)

    label_ids = request.POST.getlist("label_id")
    labels = list(FamLabel.objects.filter(pk__in=label_ids, tenant=tenant))

    auto_sheet = request.POST.get("auto_sheet") == "1"
    force_sheet = request.POST.get("sheet") == "1"
    use_sheet = force_sheet or (auto_sheet and (len(labels) > 1 or (fmt.cols * fmt.rows) > 1))

    pagesize = _page_size(fmt.page, fmt.orient)
    resp = HttpResponse(content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="labels.pdf"'
    c = rl_canvas.Canvas(resp, pagesize=pagesize)

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
        c.drawImage(ImageReader(buf), x_pt, y_pt,
                    width=cell_w_pt, height=cell_h_pt,
                    preserveAspectRatio=True, mask='auto')

    col = row = 0
    for lbl in labels:
        code = lbl.company_tag or str(lbl.id)
        code_text = (fmt.code_text or "{{ code }}").replace("{{ code }}", code)

        try:
            qr_field = lbl.qr_code
            if qr_field and getattr(qr_field, "path", None):
                from django.core.files.storage import default_storage
                with default_storage.open(qr_field.name, "rb") as f:
                    qr_img = Image.open(f).convert("RGB")
            else:
                qr_img = _qr_from_text(code)
        except Exception:
            qr_img = _qr_from_text(code)

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
            x = margin_pt + col * (cell_w_pt + gap_x_pt)
            y = page_h - margin_pt - (row + 1) * cell_h_pt - row * gap_y_pt
            draw_label_at(x, y, label_im)
            col += 1
            if col >= int(fmt.cols):
                col = 0
                row += 1
            if row >= int(fmt.rows):
                c.showPage()
                row = col = 0
        else:
            x = (page_w - cell_w_pt) / 2.0
            y = (page_h - cell_h_pt) / 2.0
            draw_label_at(x, y, label_im)
            c.showPage()

    c.save()
    return resp


@xframe_options_sameorigin
@login_required
@require_GET
def print_format_page_preview_pdf(request):
    """
    Preview PDF of the full page with grid & repeated label.
    Respects exactly the user-defined label size, rows, cols, gaps, and margins.
    If the layout exceeds the page, it flows onto multiple pages.

    Optional GET params:
      ?show_footer=0   → hide footer (default on)
      ?show_grid=0     → hide grid lines (default on)
    """
    # ---- params ----
    layout_key = (request.GET.get("layout_key") or "").strip()
    page = (request.GET.get("page") or "A4")
    orient = (request.GET.get("orient") or "portrait")
    cols = int(request.GET.get("cols") or 3)
    rows = int(request.GET.get("rows") or 8)
    gap_x_mm = float(request.GET.get("gap_x_mm") or 2)
    gap_y_mm = float(request.GET.get("gap_y_mm") or 2)
    top_margin_mm = float(request.GET.get("top_margin_mm") or 5)
    left_margin_mm = float(request.GET.get("left_margin_mm") or 5)

    width_mm = float(request.GET.get("width_mm") or 70)
    height_mm = float(request.GET.get("height_mm") or 37)
    bleed_mm = float(request.GET.get("bleed_mm") or 0)

    main_text = request.GET.get("main_text") or "Control de Activos"
    code_tpl = request.GET.get("code_text") or "{{ code }}"
    sample_code = request.GET.get("sample_code") or "SAMPLE-001"
    code_text = code_tpl.replace("{{ code }}", sample_code)

    show_footer = request.GET.get("show_footer", "0") == "1"
    show_grid = request.GET.get("show_grid", "0") == "1"

    # ---- standard no-cache PDF headers ----
    resp = HttpResponse(content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="sheet_preview.pdf"'
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp["Pragma"] = "no-cache"
    resp["Expires"] = "0"

    # ---- page setup ----
    pagesize = _page_size(page, orient)
    c = rl_canvas.Canvas(resp, pagesize=pagesize)
    pw, ph = pagesize

    # ---- convert units ----
    gap_x_pt = mm_to_pt(gap_x_mm)
    gap_y_pt = mm_to_pt(gap_y_mm)
    label_w_pt = mm_to_pt(width_mm)
    label_h_pt = mm_to_pt(height_mm)
    origin_x = mm_to_pt(left_margin_mm)
    origin_y = mm_to_pt(top_margin_mm)

    # ---- render one label and reuse ----
    vdpi = 150
    qr_img = _qr_from_text(sample_code, size_px=max(64, int(min(label_w_pt, label_h_pt) / 72 * vdpi)))
    try:
        label_im = render_label_with_stored_qr(
            layout_key=layout_key,
            width_mm=width_mm,
            height_mm=height_mm,
            dpi=vdpi,
            main_text=main_text,
            code_text=code_text,
            qr_img=qr_img,
            bleed_mm=bleed_mm,
        )
    except Exception:
        tile_w_px = max(1, int(width_mm / 25.4 * vdpi))
        tile_h_px = max(1, int(height_mm / 25.4 * vdpi))
        label_im = Image.new("RGB", (tile_w_px, tile_h_px), "white")
        d2 = ImageDraw.Draw(label_im)
        d2.rectangle([0, 0, tile_w_px - 1, tile_h_px - 1], outline="black", width=1)

    # ---- draw page + inner border (dotted grid) ----
    if show_grid:
        c.setStrokeColorRGB(0.4, 0.4, 0.4)
        c.setDash(2, 3)  # dotted
        c.rect(0.5, 0.5, pw - 1, ph - 1, stroke=1, fill=0)  # outer page border

        c.setStrokeColorRGB(0.6, 0.6, 0.6)
        content_w = pw - origin_x - mm_to_pt(left_margin_mm)
        content_h = ph - origin_y - mm_to_pt(top_margin_mm)
        c.rect(origin_x, origin_y, content_w, content_h, stroke=1, fill=0)  # usable area
        c.setDash()

    # ---- pagination loop ----
    total_labels = cols * rows
    current_label = 0
    while current_label < total_labels:
        for r in range(rows):
            for cidx in range(cols):
                if current_label >= total_labels:
                    break

                x = origin_x + cidx * (label_w_pt + gap_x_pt)
                y = ph - origin_y - (r + 1) * label_h_pt - r * gap_y_pt

                if y < origin_y:
                    break

                # draw cell if grid enabled
                if show_grid:
                    c.setStrokeColorRGB(0.5, 0.5, 0.5)
                    c.setDash(2, 3)
                    c.rect(x, y, label_w_pt, label_h_pt, stroke=1, fill=0)
                    c.setDash()

                # draw label
                buf = BytesIO()
                label_im.save(buf, format="PNG")
                buf.seek(0)
                c.drawImage(
                    ImageReader(buf), x, y,
                    width=label_w_pt, height=label_h_pt,
                    preserveAspectRatio=True, mask='auto'
                )
                current_label += 1

        if current_label < total_labels:
            c.showPage()

    # ---- footer ----
    if show_footer:
        c.setFillColorRGB(0.45, 0.45, 0.45)
        c.setFont("Helvetica", 8)
        footer = (f"{page} {orient} — {cols}×{rows} | "
                  f"label {width_mm}×{height_mm}mm | "
                  f"gaps {gap_x_mm}/{gap_y_mm}mm | "
                  f"margins T{top_margin_mm} L{left_margin_mm}mm")
        c.drawString(mm_to_pt(8), mm_to_pt(8), footer)

    c.save()
    return resp


@login_required
@require_GET
def print_format_page_preview_fragment(request):
    """
    Returns an HTML snippet with a constrained <object> that embeds the preview PDF.
    """
    params = request.GET.copy()
    # Always send lock_cell=1 to keep cell = label (client can override by sending 0)
    if "lock_cell" not in params:
        params["lock_cell"] = "1"
    params["_cb"] = str(int(timezone.now().timestamp() * 1000))
    pdf_url = reverse("fam:print_format_page_preview_pdf") + "?" + urlencode(params)
    pdf_view = f"{pdf_url}#view=Fit"  # initial zoom = full page

    html = f"""
      <object
        data="{pdf_view}"
        type="application/pdf"
        class="pf-preview-obj">
        <div class="small text-muted p-2">
          PDF preview couldn’t be embedded.
          <a href="{pdf_url}" target="_blank" rel="noopener">Open in a new tab</a>.
        </div>
      </object>
      <div class="d-flex justify-content-end mt-1">
        <a class="btn btn-sm btn-outline-secondary" href="{pdf_url}" target="_blank" rel="noopener">Open in new tab ↗</a>
      </div>
    """
    resp = HttpResponse(html)
    resp["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp["Pragma"] = "no-cache"
    resp["Expires"] = "0"
    return resp