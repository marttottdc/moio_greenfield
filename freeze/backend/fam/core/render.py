# fam/core/render.py
import base64
import io
import re
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont
from django.core.files.storage import default_storage

from fam.models import LabelLayout
from portal.context_utils import current_tenant  # thread-local .get()



# -------------------- units ----------------------------------------------------
def mm_to_px(mm_val: float, dpi: int) -> int:
    return int(round(mm_val * dpi / 25.4))


def mm_to_pt(mm_val: float) -> float:
    return (mm_val / 25.4) * 72.0


# -------------------- PIL helpers ---------------------------------------------
def _resample():
    try:
        return Image.Resampling.LANCZOS
    except Exception:  # Pillow < 9
        return Image.LANCZOS


def _open_label_qr_pil(label) -> Optional[Image.Image]:
    """
    Utility kept for convenience elsewhere; not used directly here since
    render_label_with_stored_qr receives qr_img already.
    """
    if not getattr(label, "qr_code", None):
        return None
    with default_storage.open(label.qr_code.name, "rb") as f:
        im = Image.open(f)
        return im.convert("RGB")


def _fit_contain(src_w: int, src_h: int, box_w: int, box_h: int, force_square: bool = False) -> Tuple[int, int, int, int]:
    if force_square:
        side = min(box_w, box_h)
        ratio = min(side / max(1, src_w), side / max(1, src_h))
    else:
        ratio = min(box_w / max(1, src_w), box_h / max(1, src_h))
    nw = max(1, int(src_w * ratio))
    nh = max(1, int(src_h * ratio))
    ox = (box_w - nw) // 2
    oy = (box_h - nh) // 2
    return nw, nh, ox, oy


def _cell_px_frac(elem: Dict[str, Any], base_w: int, base_h: int, pad_base: int) -> Tuple[int, int, int, int]:
    """
    Convert fractional x,y,w,h (0..1) plus optional 'pad' fraction into integer px
    within a base (trim) box. Returns (x,y,w,h) inside the *trim* area.
    """
    x = int(float(elem.get("x", 0)) * base_w)
    y = int(float(elem.get("y", 0)) * base_h)
    w = max(1, int(float(elem.get("w", 0)) * base_w))
    h = max(1, int(float(elem.get("h", 0)) * base_h))
    pad_frac = float(elem.get("pad", 0) or 0.0)
    pad = int(pad_frac * pad_base)
    return x + pad, y + pad, max(1, w - 2 * pad), max(1, h - 2 * pad)


def _load_font(px: int, bold: bool = False):
    # Try a few common fonts; fall back to default
    candidates = [
        ("DejaVuSans-Bold.ttf", True),
        ("Arial-Bold.ttf", True),
        ("Arial Bold.ttf", True),
        ("DejaVuSans.ttf", False),
        ("Arial.ttf", False),
    ]
    if bold:
        order = [c for c in candidates if c[1]] + [c for c in candidates if not c[1]]
    else:
        order = [c for c in candidates if not c[1]] + [c for c in candidates if c[1]]

    for name, _is_bold in order:
        try:
            return ImageFont.truetype(name, max(6, int(px)))
        except Exception:
            continue
    return ImageFont.load_default()


def _measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    try:
        # Pillow ≥ 8.0
        bbox = draw.multiline_textbbox((0, 0), text, font=font, align="left")
        return (bbox[2] - bbox[0], bbox[3] - bbox[1])
    except Exception:
        # Fallback
        try:
            w = draw.textlength(text, font=font)
        except Exception:
            w = int(len(text) * (font.size or 10) * 0.6)
        h = int((font.size or 10) * 1.25)
        return int(w), int(h)


# -------------------- images from data URLs -----------------------------------
_DATAURL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<b64>.+)$", re.IGNORECASE)


def _image_from_data_url(src: str) -> Optional[Image.Image]:
    m = _DATAURL_RE.match(src or "")
    if not m:
        return None
    raw = base64.b64decode(m.group("b64"))
    mime = (m.group("mime") or "").lower()
    if "svg" in mime:
        try:
            import cairosvg  # optional
            png_bytes = cairosvg.svg2png(bytestring=raw)
            return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        except Exception:
            return None
    try:
        return Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:
        return None


# -------------------- layout extraction ---------------------------------------
def _extract_elements(layout: Any) -> List[Dict[str, Any]]:
    """
    Accepts various common shapes:
      - layout.elements is a dict with key 'elements'
      - layout.elements is already a list
      - layout.items is a list (legacy)
      - layout.json / layout.spec (dict with 'elements' or 'items')
    """
    # direct attribute "elements"
    if hasattr(layout, "elements"):
        data = getattr(layout, "elements")
        if isinstance(data, list):
            return list(data)
        if isinstance(data, dict):
            if isinstance(data.get("elements"), list):
                return list(data["elements"])
            if isinstance(data.get("items"), list):
                return list(data["items"])

    # other likely attributes
    for attr in ("json", "spec", "definition", "data", "content", "payload"):
        if hasattr(layout, attr):
            obj = getattr(layout, attr)
            if isinstance(obj, dict):
                if isinstance(obj.get("elements"), list):
                    return list(obj["elements"])
                if isinstance(obj.get("items"), list):
                    return list(obj["items"])

    # legacy "items" directly on model
    if hasattr(layout, "items") and isinstance(layout.items, list):
        return list(layout.items)

    raise ValueError("Unable to extract elements list from LabelLayout")


def _resolve_layout(layout_key: str) -> Any:
    key = (layout_key or "").strip()
    if not key:
        raise ValueError("layout_key is required")

    tenant = current_tenant.get()
    try:
        qs = LabelLayout.objects
        if tenant is not None and hasattr(LabelLayout, "tenant"):
            layout = qs.get(key=key, tenant=tenant)
        else:
            layout = qs.get(key=key)
        return layout
    except LabelLayout.DoesNotExist:
        # Let the caller raise if desired; keeping it explicit
        raise


def _qr_from_text(data: str, size_px: int = 300) -> Image.Image:
    try:
        import qrcode  # type: ignore

        qr = qrcode.QRCode(border=1, box_size=max(2, size_px // 60))
        qr.add_data(data or "")
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        return img
    except Exception:
        # Simple placeholder if qrcode lib is missing
        img = Image.new("RGB", (size_px, size_px), "white")
        d = ImageDraw.Draw(img)
        pad = size_px // 12
        d.rectangle([pad, pad, size_px - pad, size_px - pad], outline="black", width=3)
        d.rectangle([pad * 2, pad * 2, size_px - pad * 2, size_px - pad * 2], fill="black")
        return img
# -------------------- main API -------------------------------------------------


# render.py (excerpt)

# filename: render.py

# === [PDF-FUNC:render_label_with_stored_qr] ===
def render_label_with_stored_qr(
    layout_key: str,
    width_mm: float,
    height_mm: float,
    dpi: int,
    main_text: str,
    code_text: str,
    qr_img: Image.Image,
    bleed_mm: float = 0.0,
) -> Image.Image:
    """
    Render a label using the DB-stored LabelLayout identified by `layout_key`.

    NEW (mm-based):
      - Each element uses absolute millimeters: x, y, w, h, and fontSize (mm).
      - Only 'logo' is a stored image (ImageField on LabelLayout). 'qr' is dynamic (qr_img).
      - We do NOT rely on any persisted 'src' (data URLs / blob URLs) for the editor.

    BACKWARD COMPAT:
      - If an element looks fractional (all x/y/w/h ≤ 1.05), treat as fractions of the trim box.

    Expected shape in DB (modern):
      layout.elements == {
        "width_mm": <mm>, "height_mm": <mm>,
        "items": [ { "type": "image"|"text", "role": "logo"|"qr"|"title"|"code"|..., "x":mm, "y":mm, "w":mm, "h":mm, ... }, ... ]
      }
    """
    # --- helpers (local, small) ---
    def _is_frac_elem(e: dict) -> bool:
        try:
            vals = [float(e.get(k, 0.0)) for k in ("x", "y", "w", "h")]
            return all(0.0 <= v <= 1.05 for v in vals) and max(vals) <= 1.05
        except Exception:
            return False

    def _mm_rect_to_px(e: dict) -> tuple[int, int, int, int]:
        """Convert this element's (x,y,w,h) to pixels from mm (add bleed offset)."""
        x_px = mm_to_px(float(e.get("x", 0.0)), dpi)
        y_px = mm_to_px(float(e.get("y", 0.0)), dpi)
        w_px = mm_to_px(float(e.get("w", 0.0)), dpi)
        h_px = mm_to_px(float(e.get("h", 0.0)), dpi)
        return offset_x + int(round(x_px)), offset_y + int(round(y_px)), int(round(w_px)), int(round(h_px))

    def _frac_rect_to_px(e: dict) -> tuple[int, int, int, int]:
        """Convert this element's (x,y,w,h) as fractions of trim to pixels (add bleed offset)."""
        x_px = int(round(float(e.get("x", 0.0)) * trim_w_px))
        y_px = int(round(float(e.get("y", 0.0)) * trim_h_px))
        w_px = int(round(float(e.get("w", 0.0)) * trim_w_px))
        h_px = int(round(float(e.get("h", 0.0)) * trim_h_px))
        return offset_x + x_px, offset_y + y_px, w_px, h_px

    def _font_px(e: dict) -> int:
        """
        Font size: prefer mm (fontSize). If absent, accept legacy 'fs' as fraction of the
        shorter trim edge. Always clamp to ≥6 px for legibility.
        """
        if "fontSize" in e:
            try:
                fs_mm = max(0.1, float(e["fontSize"]))
            except Exception:
                fs_mm = 4.0
            return max(6, int(round(mm_to_px(fs_mm, dpi))))
        # legacy fraction (e.g., 0.06 of min(trim_w, trim_h))
        fs_frac = float(e.get("fs", 0.0)) if e.get("fs") is not None else 0.0
        if fs_frac > 0:
            return max(6, int(round(mm_to_px(min(width_mm, height_mm) * fs_frac, dpi))))
        # default
        return max(6, int(round(mm_to_px(4.0, dpi))))

    def _open_layout_logo(layout_obj) -> Image.Image | None:
        """
        Try to open the stored logo (ImageField) on the LabelLayout, if present.
        Returns a PIL Image or None.
        """
        try:
            logo = getattr(layout_obj, "logo", None)
            if not logo:
                return None
            with logo.open("rb") as fh:
                im = Image.open(fh)
                im.load()
                return im
        except Exception:
            return None

    def _choose_image_source(elem: dict) -> Image.Image | None:
        """
        Decide the image to draw for this element:
          - role=='qr'  -> use qr_img (parameter)
          - role=='logo'-> use layout.logo (ImageField)
          - else (legacy) -> try data URL in elem.get("src")
        """
        role = (elem.get("role") or "").lower()
        if role == "qr":
            return qr_img
        if role == "logo":
            return layout_logo_img  # prepared once outside loop
        # legacy fall-back (editor could have persisted a data URL long ago)
        src = elem.get("src")
        if src:
            try:
                return _image_from_data_url(src)
            except Exception:
                return None
        return None

    def _paste_image(base: Image.Image, img: Image.Image, cx: int, cy: int, cw: int, ch: int, keep_aspect: bool, opacity: float):
        """Resize/paste image into (cx,cy,cw,ch), honoring aspect + opacity."""
        if img is None or cw <= 0 or ch <= 0:
            return
        iw, ih = img.size
        if iw <= 0 or ih <= 0:
            return

        if keep_aspect:
            scale = min(cw / iw, ch / ih) if iw and ih else 1.0
            nw = max(1, int(round(iw * scale)))
            nh = max(1, int(round(ih * scale)))
            ox = (cw - nw) // 2
            oy = (ch - nh) // 2
        else:
            nw, nh = max(1, int(cw)), max(1, int(ch))
            ox = oy = 0

        img2 = img.resize((nw, nh), _resample())

        # Apply opacity if needed
        if opacity < 1.0:
            if img2.mode != "RGBA":
                img2 = img2.convert("RGBA")
            # scale alpha channel
            bands = img2.getbands()
            if "A" in bands:
                a = img2.getchannel("A").point(lambda p: int(p * opacity))
            else:
                a = Image.new("L", img2.size, int(255 * opacity))
            img2.putalpha(a)
            base.paste(img2, (cx + ox, cy + oy), img2)
        else:
            if img2.mode in ("RGBA", "LA"):
                base.paste(img2, (cx + ox, cy + oy), img2)
            else:
                base.paste(img2, (cx + ox, cy + oy))

    # --- canvas sizes ---
    bleed_px = mm_to_px(bleed_mm, dpi)
    trim_w_px = mm_to_px(width_mm, dpi)
    trim_h_px = mm_to_px(height_mm, dpi)
    total_w_px = trim_w_px + 2 * bleed_px
    total_h_px = trim_h_px + 2 * bleed_px
    offset_x, offset_y = bleed_px, bleed_px

    # --- base image ---
    label_img = Image.new("RGB", (max(1, total_w_px), max(1, total_h_px)), "white")
    draw = ImageDraw.Draw(label_img)

    # --- fetch layout + elements (mm-native if present) ---
    layout = _resolve_layout(layout_key)  # should give you a model; tolerates dict
    layout_json = getattr(layout, "elements", layout) or {}
    items = (layout_json.get("items") or layout_json.get("elements") or [])  # tolerate old key
    # Preload logo once
    layout_logo_img = _open_layout_logo(layout)

    # --- template vars ---
    tmpl_main = main_text or ""
    tmpl_code = code_text or ""

    # --- main loop ---
    for elem in items:
        et = (elem.get("type") or "").lower()

        # position/size in px (mm-modern or frac-legacy)
        if _is_frac_elem(elem):
            cx, cy, cw, ch = _frac_rect_to_px(elem)
        else:
            cx, cy, cw, ch = _mm_rect_to_px(elem)

        if et == "image":
            keep_aspect = bool(elem.get("keepAspect", True))
            opacity = float(elem.get("opacity", 1.0))
            src_img = _choose_image_source(elem)
            _paste_image(label_img, src_img, cx, cy, cw, ch, keep_aspect, opacity)
            continue

        if et == "text":
            role = (elem.get("role") or "").lower()
            raw_text = elem.get("text", "")

            if role == "title":
                text = tmpl_main
            elif role == "code":
                text = tmpl_code
            else:
                text = raw_text.replace("{{ main }}", tmpl_main).replace("{{ code }}", tmpl_code)

            fs_px = _font_px(elem)
            bold = (int(elem.get("fontWeight", 400)) >= 600)
            font = _load_font(fs_px, bold=bold)

            align = (elem.get("align") or "left").lower()
            color = elem.get("color", "#000000")
            valign = (elem.get("valign") or "top").lower()

            # size of rendered (no explicit wrap here)
            tw, th = _measure(draw, text, font)

            # horizontal position within (cx..cx+cw)
            if align == "center":
                tx = cx + (cw - tw) // 2
            elif align == "right":
                tx = cx + (cw - tw)
            else:
                tx = cx

            # vertical alignment
            if valign == "middle":
                ty = cy + (ch - th) // 2
            elif valign == "bottom":
                ty = cy + (ch - th)
            else:
                ty = cy

            draw.multiline_text((tx, ty), text, font=font, fill=color, align=align)

        # ignore unknown

    return label_img
# === [/PDF-FUNC:render_label_with_stored_qr] ===


__all__ = [
    "mm_to_px",
    "mm_to_pt",
    "render_label_with_stored_qr",
    "_open_label_qr_pil",
]
