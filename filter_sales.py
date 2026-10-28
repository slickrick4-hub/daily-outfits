"""Turns data/sales.json into data/filtered.json: men's, in-season items in your sizes."""
import json, re
from datetime import datetime, timezone

S = json.load(open("config.json"))

# Words that remove an item (summer pieces, accessories, lounge wear, internal notes).
SKIP_WORDS = ["short", "tank", "dress", "skirt", "swim", "linen", "seersucker", "camp shirt",
              "resort", "sweatpant", "jogger", "lounge", "check with"]
SKIP_REGEX = r"\b(hat|cap|beanie|scarf|tote|belt|wallet|bandana|patch|sock|glove|bag|pin)s?\b"
SHOES = ["loafer", "derby", "derbies", "oxfords", "wingtip", "boot", "sneaker", "trainer", "shoe",
         "chelsea", "monk", "brogue", "sandal", "driver", "slipper"]
OUTER = ["jacket", "coat", "vest", "overshirt", "bomber", "shacket", "anorak", "blazer", "sportcoat", "parka"]
BOTTOM = ["pant", "trouser", "jean", "chino", "denim", "cargo", "selvedge", "selvage"]
TOP = ["shirt", "sweater", "polo", "crew", "henley", "hood", "sweatshirt", "pullover", "cardigan",
       "knit", "zip", "rugby", "longsleeve", "long sleeve", "popover", "oxford", "chambray",
       "flannel", "jack in", "mock"]


def tag_list(item):
    tags = item.get("tags") or []
    if isinstance(tags, str):
        tags = tags.split(",")
    return [str(t).strip().lower() for t in tags]


def is_mens(item):
    title = (item.get("title") or "").lower()
    if "women" in title:
        return False
    if "unisex" in title or "men's" in title or "men\u2019s" in title:
        return True
    return any(t in ("men", "mens", "mens-sale", "unisex") for t in tag_list(item))


def kind_of(item):
    text = ((item.get("title") or "") + " " + (item.get("type") or "")).lower()
    if any(w in text for w in SHOES):
        return "shoes"
    if any(w in text for w in SKIP_WORDS) or re.search(SKIP_REGEX, text):
        return None
    if any(w in text for w in OUTER):
        return "outerwear"
    if any(w in text for w in BOTTOM):
        return "bottom"
    if re.search(r"\btee\b", text) or any(w in text for w in TOP):
        return "top"
    return None


def size_ok(item, kind):
    if kind == "shoes" and not S["shoe_sizes"]:
        return bool(item.get("sizes"))  # no shoe size set yet, so accept anything in stock
    for raw in item.get("sizes") or []:
        s = str(raw).strip().upper()
        if kind == "shoes":
            m = re.match(r"^(?:US\s*)?(\d{1,2}(?:\.\d)?)", s)
            if m and float(m.group(1)) in S["shoe_sizes"]:
                return True
        elif kind == "bottom":
            m = re.match(r"^(\d{2})(?:\s*[/X-]\s*(\d{2}))?$", s)
            if m and S["waist_min"] <= int(m.group(1)) <= S["waist_max"]:
                if not m.group(2) or int(m.group(2)) in S["lengths"]:
                    return True
        elif s.split(" - ")[0].strip() in S["top_sizes"]:
            return True
    return False


def main():
    data = json.load(open("data/sales.json"))
    kept = []
    for it in data["items"]:
        if not is_mens(it):
            continue
        kind = kind_of(it)
        if not kind or not size_ok(it, kind):
            continue
        rate = S["usd_to_cad"] if it.get("currency") == "USD" else 1
        price, was = round(it["price"] * rate, 2), round(it["was"] * rate, 2)
        cap = S["max_shoe_cad"] if kind == "shoes" else S["max_item_cad"]
        if it["off_pct"] < S["min_off_pct"] or price > cap:
            continue
        it = dict(it, kind=kind, price_cad=price, was_cad=was,
                  final_sale="final-sale" in tag_list(it))
        kept.append(it)
    kept.sort(key=lambda i: (i["kind"], -i["off_pct"]))
    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "source_generated_at": data.get("generated_at"), "items": kept}
    with open("data/filtered.json", "w") as f:
        json.dump(out, f)
    print(f"Kept {len(kept)} of {len(data['items'])} items")
    for k in ("top", "bottom", "shoes", "outerwear"):
        print(f"  {k}: {sum(1 for i in kept if i['kind'] == k)}")


if __name__ == "__main__":
    main()
