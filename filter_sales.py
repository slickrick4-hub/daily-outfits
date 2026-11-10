"""Turns data/sales.json into data/filtered.json: men's, in-season items in your sizes."""
import json, re
from datetime import datetime, timezone

S = json.load(open("config.json"))
# approximate conversion to CAD; stores in a currency not listed here are skipped, not guessed
RATES = {"CAD": 1.0, "USD": S["usd_to_cad"], "GBP": 1.80, "EUR": 1.55, "AUD": 0.90, "NZD": 0.82,
         "DKK": 0.21, "JPY": 0.0092}
RATES.update(S.get("rates", {}))

# Words that remove an item (summer pieces, accessories, lounge wear, internal notes).
SKIP_WORDS = ["short", "tank", "skirt", "swim", "linen", "seersucker", "camp shirt",
              "resort", "sweatpant", "jogger", "lounge", "check with"]
SKIP_REGEX = (r"\b(hat|cap|beanie|scarf|tote|belt|wallet|bandana|patch|sock|glove|bag|pin)s?\b"
              # underwear and sleepwear never belong in an outfit
              r"|\b(boxer|brief|underwear|undershirt|trunk|pajama|pyjama|sleepwear|robe)s?\b|\bsleep\b"
              # dresses, but not dress shirts, dress trousers or dress shoes
              r"|\bdress(es)?\b(?!\s*(shirt|pant|trouser|slack|shoe|boot|sneaker|sock))"
              # multi-packs ("Crew 6-Pack", "(3-Pack)", "Bundle"): the price and photo cover several pieces
              r"|\b\d+\s*-?\s*pack\b|\bbundle\b|\bessentials pack\b"
              # summer-only shirts
              r"|camp collar|summerweight|hawaiian|\baloha\b")
# open summer shoes; checked before the shoe words, since "sandal" would otherwise make it a shoe
SUMMER_SHOES = re.compile(r"sandal|\bslides?\b|flip.?flop|huarache|espadrille|\bclogs?\b|\bthong\b")
SHOES = ["loafer", "derby", "derbies", "oxfords", "wingtip", "boot", "sneaker", "trainer", "shoe",
         "chelsea", "monk", "brogue", "sandal", "driver", "slipper"]
OUTER = ["jacket", "coat", "vest", "overshirt", "bomber", "shacket", "anorak", "blazer", "sportcoat", "parka"]
BOTTOM = ["pant", "trouser", "jean", "chino", "cargo", "slack"]
# fabric words that usually mean trousers, but only when the title doesn't name a top ("Denim Shirt" is a shirt)
BOTTOM_FABRIC = ["denim", "selvedge", "selvage", "corduroy"]
TOP = ["shirt", "sweater", "polo", "crew", "henley", "hood", "sweatshirt", "pullover", "cardigan",
       "knit", "zip", "rugby", "longsleeve", "long sleeve", "popover", "oxford", "chambray",
       "flannel", "jack in", "mock", "fleece", "terry", "thermal", "jersey", "knitwear", "tops"]


def tag_list(item):
    tags = item.get("tags") or []
    if isinstance(tags, str):
        tags = tags.split(",")
    return [str(t).strip().lower() for t in tags]


try:   # stores marked "mens_only" in stores.json sell (almost) only menswear and rarely label gender
    MENS_ONLY = {st["name"] for st in json.load(open("stores.json")) if st.get("mens_only")}
except Exception:
    MENS_ONLY = set()
WOMEN_RX = re.compile(r"\b(wom[ae]n|wom[ae]ns|wom[ae]n's|wom[ae]n\u2019s|female|ladies|girls?)\b")
# kids' sizes ("Boys' chino", "Youth dress shirt"); "Cow Boy" is a shirt name, not a size range
KIDS_RX = re.compile(r"\b(kids?|(?<!cow )boys?|youth|toddlers?|baby|infants?|junior)\b")
MEN_RX = re.compile(r"\b(men|mens|men's|men\u2019s|male|menswear|unisex)\b")


def is_mens(item):
    title = (item.get("title") or "").lower()
    labels = " | ".join(tag_list(item) + [(item.get("type") or "").lower()])
    if "women" in title or WOMEN_RX.search(labels) or KIDS_RX.search(title):
        return False
    if MEN_RX.search(title) or MEN_RX.search(labels):
        return True
    return item.get("store") in MENS_ONLY


def kind_of(item):
    text = ((item.get("title") or "") + " " + (item.get("type") or "")).lower()
    if SUMMER_SHOES.search((item.get("title") or "").lower()):   # title only: some stores file sneakers under "Sneakers & Sandals"
        return None
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
    if any(w in text for w in BOTTOM_FABRIC):
        return "bottom"
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
        rate = RATES.get(it.get("currency"))
        if rate is None:
            continue
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
