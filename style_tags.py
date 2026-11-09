"""Style details for each catalog item (fit, materials, pattern, vibes), read from the store's own
title, product type and tags. Used by make_catalog.py; the browser matches them to the style quiz."""
import re


def _rx(words):
    return re.compile(r"\b(" + "|".join(words) + r")\b")


FIT = {
    "slim": _rx(["slim", "skinny", "tapered", "trim fit", "tailored fit", "fitted"]),
    "relaxed": _rx(["relaxed", "loose", "wide", "wide leg", "oversized", "boxy", "baggy", "easy fit", "roomy"]),
    "regular": _rx(["straight", "straight leg", "classic fit", "regular fit", "standard fit", "athletic"]),
}
MATERIALS = ["merino", "cashmere", "wool", "cotton", "linen", "denim", "flannel", "corduroy", "suede",
             "leather", "fleece", "twill", "canvas", "selvedge", "tweed", "chambray", "oxford cloth",
             "jersey", "nylon", "polyester", "silk", "alpaca", "mohair", "lambswool", "waxed"]
MAT_RX = _rx(MATERIALS)
PATTERN_RX = _rx(["stripe", "striped", "stripes", "plaid", "check", "checked", "gingham", "houndstooth",
                  "camo", "camouflage", "floral", "print", "printed", "paisley", "herringbone", "tartan",
                  "graphic", "fair isle", "jacquard", "patterned"])
# Four broad looks the quiz asks about. Matched on title and product type only (tags are too noisy).
VIBES = {
    "classic": _rx(["oxford", "oxfords", "chino", "chinos", "loafer", "loafers", "blazer", "sportcoat",
                    "trouser", "trousers", "merino", "cashmere", "tweed", "herringbone", "polo", "cardigan",
                    "derby", "derbies", "brogue", "monk", "button down", "button-down", "dress shirt",
                    "poplin", "pleated", "flannel trouser", "wool", "quarter zip", "half zip", "rugby"]),
    "rugged": _rx(["denim", "selvedge", "selvage", "jean", "jeans", "flannel", "boot", "boots", "work",
                   "workwear", "chore", "canvas", "waxed", "chambray", "corduroy", "cord", "duck", "trucker",
                   "field", "overshirt", "shirt jacket", "henley", "western", "utility", "cargo", "moc"]),
    "minimal": _rx(["crew", "crewneck", "mock", "mock neck", "turtleneck", "knit", "essential", "essentials",
                    "everyday", "basic", "pima", "supima", "clean", "minimal", "slim chino", "tech pant",
                    "performance", "sweater"]),
    "casual": _rx(["tee", "t-shirt", "hoodie", "hooded", "sweatshirt", "jogger", "sweatpant", "sneaker",
                   "sneakers", "trainer", "fleece", "graphic", "shorts", "camp", "slide", "terry",
                   "pullover", "jersey", "zip hoodie", "track"]),
}


def _tags_text(item):
    tags = item.get("tags") or []
    if isinstance(tags, str):
        tags = tags.split(",")
    return " ".join(str(t) for t in tags).lower()


def style_of(item):
    title = (item.get("title") or "").lower()
    ptype = (item.get("type") or "").lower()
    main = title + " " + ptype
    full = main + " " + _tags_text(item)
    fit = next((name for name, rx in FIT.items() if rx.search(main)), None)
    mats = sorted(set(MAT_RX.findall(full)))
    patterned = bool(PATTERN_RX.search(title)) or bool(re.search(r"pattern:\s*(?!solid)\w", full))
    vibes = sorted(v for v, rx in VIBES.items() if rx.search(main))
    out = {"vibes": vibes}
    if patterned:              # only stored when true, to keep the catalog small
        out["pattern"] = True
    if fit:
        out["fit"] = fit
    if mats:
        out["materials"] = mats
    return out
