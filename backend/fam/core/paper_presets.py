# fam/paper_presets.py
from decimal import Decimal

INCH = Decimal("25.4")


def mm(inches: float) -> Decimal:
    return (Decimal(str(inches)) * INCH).quantize(Decimal("0.001"))

# Each preset stays compatible with your existing LabelPrintFormat fields.
# Uniform margin is an approximation for US sheets (Avery often uses asymmetric margins).
# If you need exact top/left margins later, we can extend, but not changing models now.

PRESETS = {
    # --------- A4 (ISO) ----------
    "a4_3x8_70x37": {
        "name": "A4 — 3×8 (70×37 mm)",
        "page": "A4", "orient": "portrait",
        "cols": 3, "rows": 8,
        "cell_w_mm": 70.0, "cell_h_mm": 37.0,
        "gap_x_mm": 2.0, "gap_y_mm": 2.0,
        "margin_mm": 5.0,
        "width_mm": 70.0, "height_mm": 37.0, "bleed_mm": 0.0,
    },
    "a4_2x7_99x38_1": {
        "name": "A4 — 2×7 (99.1×38.1 mm)",
        "page": "A4", "orient": "portrait",
        "cols": 2, "rows": 7,
        "cell_w_mm": 99.1, "cell_h_mm": 38.1,
        "gap_x_mm": 2.5, "gap_y_mm": 2.5,
        "margin_mm": 5.0,
        "width_mm": 99.1, "height_mm": 38.1, "bleed_mm": 0.0,
    },
    "a4_3x7_63_5x38_1": {
        "name": "A4 — 3×7 (63.5×38.1 mm)",
        "page": "A4", "orient": "portrait",
        "cols": 3, "rows": 7,
        "cell_w_mm": 63.5, "cell_h_mm": 38.1,
        "gap_x_mm": 2.0, "gap_y_mm": 2.0,
        "margin_mm": 7.0,
        "width_mm": 63.5, "height_mm": 38.1, "bleed_mm": 0.0,
    },
    "a4_2x4_99_1x67_7": {
        "name": "A4 — 2×4 (99.1×67.7 mm)",
        "page": "A4", "orient": "portrait",
        "cols": 2, "rows": 4,
        "cell_w_mm": 99.1, "cell_h_mm": 67.7,
        "gap_x_mm": 2.5, "gap_y_mm": 3.0,
        "margin_mm": 5.0,
        "width_mm": 99.1, "height_mm": 67.7, "bleed_mm": 0.0,
    },
    "a4_4x16_45_7x21_2": {
        "name": "A4 — 4×16 (45.7×21.2 mm)",
        "page": "A4", "orient": "portrait",
        "cols": 4, "rows": 16,
        "cell_w_mm": 45.7, "cell_h_mm": 21.2,
        "gap_x_mm": 2.0, "gap_y_mm": 2.0,
        "margin_mm": 5.0,
        "width_mm": 45.7, "height_mm": 21.2, "bleed_mm": 0.0,
    },

    # --------- US Letter (Avery-like) ----------
    # 5160: 3×10, 2.625"×1", pitch 2.75"×1.0" → gaps: 0.125" horiz, 0 vert
    "letter_avery_5160": {
        "name": "Letter — Avery 5160 (3×10, 2.625×1 in)",
        "page": "Letter", "orient": "portrait",
        "cols": 3, "rows": 10,
        "cell_w_mm": float(mm(2.625)), "cell_h_mm": float(mm(1.0)),
        "gap_x_mm":  float(mm(0.125)), "gap_y_mm": 0.0,
        "margin_mm": 4.0,  # uniform approximation
        "width_mm":  float(mm(2.625)), "height_mm": float(mm(1.0)), "bleed_mm": 0.0,
    },
    # 5163: 2×5, 4"×2", pitch ≈ 4.125"×2" → gaps ~0.125" horiz, 0 vert
    "letter_avery_5163": {
        "name": "Letter — Avery 5163 (2×5, 4×2 in)",
        "page": "Letter", "orient": "portrait",
        "cols": 2, "rows": 5,
        "cell_w_mm": float(mm(4.0)), "cell_h_mm": float(mm(2.0)),
        "gap_x_mm":  float(mm(0.125)), "gap_y_mm": 0.0,
        "margin_mm": 6.0,
        "width_mm":  float(mm(4.0)), "height_mm": float(mm(2.0)), "bleed_mm": 0.0,
    },
    # 5164: 2×3, 4"×3.333", pitch ≈ 4.125"×3.333" → gap ~0.125" horiz, ~0 vert
    "letter_avery_5164": {
        "name": "Letter — Avery 5164 (2×3, 4×3.333 in)",
        "page": "Letter", "orient": "portrait",
        "cols": 2, "rows": 3,
        "cell_w_mm": float(mm(4.0)),     "cell_h_mm": float(mm(3.333)),
        "gap_x_mm":  float(mm(0.125)),   "gap_y_mm": 0.0,
        "margin_mm": 6.0,
        "width_mm":  float(mm(4.0)),     "height_mm": float(mm(3.333)), "bleed_mm": 0.0,
    },
    # 5167: 4×20, 1.75"×0.5", pitch ≈ 2"×0.5" → gaps 0.25" horiz, 0 vert
    "letter_avery_5167": {
        "name": "Letter — Avery 5167 (4×20, 1.75×0.5 in)",
        "page": "Letter", "orient": "portrait",
        "cols": 4, "rows": 20,
        "cell_w_mm": float(mm(1.75)), "cell_h_mm": float(mm(0.5)),
        "gap_x_mm":  float(mm(0.25)), "gap_y_mm": 0.0,
        "margin_mm": 6.0,
        "width_mm":  float(mm(1.75)), "height_mm": float(mm(0.5)), "bleed_mm": 0.0,
    },
    # 5162: 2×7, 4"×1.333", pitch ≈ 4.125"×1.333" → gaps 0.125" horiz, 0 vert
    "letter_avery_5162": {
        "name": "Letter — Avery 5162 (2×7, 4×1.333 in)",
        "page": "Letter", "orient": "portrait",
        "cols": 2, "rows": 7,
        "cell_w_mm": float(mm(4.0)),     "cell_h_mm": float(mm(1.333)),
        "gap_x_mm":  float(mm(0.125)),   "gap_y_mm": 0.0,
        "margin_mm": 6.0,
        "width_mm":  float(mm(4.0)),     "height_mm": float(mm(1.333)), "bleed_mm": 0.0,
    },
}

def get_label_preset(slug: str):
    return PRESETS.get(slug)

def list_label_presets():
    # Return as simple serializable dicts
    return [
        {"slug": k, **v}
        for k, v in sorted(PRESETS.items(), key=lambda kv: kv[1]["name"])
    ]


# Width × Height in millimeters (portrait baseline)
PAGE_SPECS = {
    # ISO 216 A-series
    "A0": (Decimal("841.0"),  Decimal("1189.0")),
    "A1": (Decimal("594.0"),  Decimal("841.0")),
    "A2": (Decimal("420.0"),  Decimal("594.0")),
    "A3": (Decimal("297.0"),  Decimal("420.0")),
    "A4": (Decimal("210.0"),  Decimal("297.0")),
    "A5": (Decimal("148.0"),  Decimal("210.0")),
    "A6": (Decimal("105.0"),  Decimal("148.0")),

    # ISO 216 B-series (common)
    "B4": (Decimal("250.0"),  Decimal("353.0")),
    "B5": (Decimal("176.0"),  Decimal("250.0")),

    # North American
    "Letter":    (Decimal("215.9"), Decimal("279.4")),  # 8.5" × 11"
    "Legal":     (Decimal("215.9"), Decimal("355.6")),  # 8.5" × 14"
    "Tabloid":   (Decimal("279.4"), Decimal("431.8")),  # 11" × 17"
    "Executive": (Decimal("184.15"),Decimal("266.7")),  # 7.25" × 10.5"
    "Half Letter": (Decimal("139.7"), Decimal("215.9")),# 5.5" × 8.5"
}


def get_page_mm(name: str):
    """Return (w_mm, h_mm). Defaults to A4 if unknown."""
    return PAGE_SPECS.get(name, PAGE_SPECS["A4"])


def list_page_presets():
    """List of dicts with key, width_mm, height_mm (as float for JSON)."""
    out = []
    for k, (w, h) in PAGE_SPECS.items():
        out.append({"key": k, "width_mm": float(w), "height_mm": float(h)})
    return sorted(out, key=lambda d: d["key"])


def D(x: float) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.001"))

"""
Presets are printer-agnostic but align with common Zebra/Brother/DYMO sizes.
 type: diecut (fixed H with gap) or continuous (variable H, no gap)
 """

ROLL_PRESETS = {
    # --- Die-cut (gap between labels along feed direction) ---
    "roll_25x12_gap3":   {"name": "25×12 mm (gap 3)",   "type": "diecut",    "roll_w_mm": D(25.0),  "label_h_mm": D(12.0),  "gap_y_mm": D(3.0)},
    "roll_32x19_gap3":   {"name": "32×19 mm (gap 3)",   "type": "diecut",    "roll_w_mm": D(32.0),  "label_h_mm": D(19.0),  "gap_y_mm": D(3.0)},
    "roll_38x25_gap3":   {"name": "38×25 mm (gap 3)",   "type": "diecut",    "roll_w_mm": D(38.0),  "label_h_mm": D(25.0),  "gap_y_mm": D(3.0)},
    "roll_50x25_gap3":   {"name": "50×25 mm (gap 3)",   "type": "diecut",    "roll_w_mm": D(50.0),  "label_h_mm": D(25.0),  "gap_y_mm": D(3.0)},
    "roll_50x38_gap3":   {"name": "50×38 mm (gap 3)",   "type": "diecut",    "roll_w_mm": D(50.0),  "label_h_mm": D(38.0),  "gap_y_mm": D(3.0)},
    "roll_57x32_gap3":   {"name": "57×32 mm (gap 3)",   "type": "diecut",    "roll_w_mm": D(57.0),  "label_h_mm": D(32.0),  "gap_y_mm": D(3.0)},
    "roll_62x29_gap3":   {"name": "62×29 mm (gap 3)",   "type": "diecut",    "roll_w_mm": D(62.0),  "label_h_mm": D(29.0),  "gap_y_mm": D(3.0)},
    "roll_62x100_gap3":  {"name": "62×100 mm (gap 3)",  "type": "diecut",    "roll_w_mm": D(62.0),  "label_h_mm": D(100.0), "gap_y_mm": D(3.0)},
    "roll_102x51_gap3":  {"name": "102×51 mm (gap 3)",  "type": "diecut",    "roll_w_mm": D(102.0), "label_h_mm": D(51.0),  "gap_y_mm": D(3.0)},
    "roll_102x76_gap3":  {"name": "102×76 mm (gap 3)",  "type": "diecut",    "roll_w_mm": D(102.0), "label_h_mm": D(76.0),  "gap_y_mm": D(3.0)},
    "roll_102x149_gap3": {"name": "102×149 mm (gap 3)", "type": "diecut",    "roll_w_mm": D(102.0), "label_h_mm": D(149.0), "gap_y_mm": D(3.0)},  # 4×6"

    # --- Continuous (no gap; you choose the print height) ---
    "roll_cont_62":      {"name": "Continuous 62 mm",   "type": "continuous","roll_w_mm": D(62.0),  "default_h_mm": D(50.0)},
    "roll_cont_102":     {"name": "Continuous 102 mm",  "type": "continuous","roll_w_mm": D(102.0), "default_h_mm": D(100.0)},
}


def list_roll_presets():
    out = []
    for slug, p in ROLL_PRESETS.items():
        row = {"slug": slug, "name": p["name"], "type": p["type"], "roll_w_mm": float(p["roll_w_mm"])}
        if p["type"] == "diecut":
            row.update({"label_h_mm": float(p["label_h_mm"]), "gap_y_mm": float(p["gap_y_mm"])})
        else:
            row.update({"default_h_mm": float(p["default_h_mm"])})
        out.append(row)
    return sorted(out, key=lambda d: d["name"])


def get_roll_preset(slug: str):
    return ROLL_PRESETS.get(slug)
