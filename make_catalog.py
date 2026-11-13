"""Turns data/sales.json into data/catalog.json: every in-season men's sale item, tagged,
with all of its sizes. Sizes and budget are applied later in each person's browser."""
import json
from datetime import datetime, timezone

import filter_sales as F
import build_outfit as B
import style_tags as ST


def cap_per_store(items, cap):
    """Keep at most `cap` items per store so a few huge stores can't flood the feed. Takes the biggest
    discounts first, one kind at a time in turn, so a store keeps its shoes and trousers, not just tops."""
    by_store = {}
    for it in items:
        by_store.setdefault(it["store"], []).append(it)
    kept = []
    for store_items in by_store.values():
        if len(store_items) <= cap:
            kept += store_items
            continue
        queues = {}
        for it in sorted(store_items, key=lambda i: -i["off_pct"]):
            queues.setdefault(it["kind"], []).append(it)
        picked = []
        while len(picked) < cap:
            for q in queues.values():
                if q and len(picked) < cap:
                    picked.append(q.pop(0))
        kept += picked
    return kept


# where each store ships from, guessed from its currency (big retailers found through Google Shopping
# are their Canadian sites). Shown on the site, with a "Canada and US only" option.
REGION = {"CAD": "CA", "USD": "US", "GBP": "UK", "EUR": "EU", "DKK": "EU", "JPY": "JP", "AUD": "AU", "NZD": "NZ"}


def store_regions():
    out = {}
    try:
        for st in json.load(open("stores.json")):
            out[st["name"]] = st.get("ships_from") or REGION.get(st.get("currency"), "")
    except Exception:
        pass
    try:
        for name in json.load(open("shopping.json"))["retailers"]:
            out.setdefault(name, "CA")
    except Exception:
        pass
    return {k: v for k, v in out.items() if v}


def main():
    data = json.load(open("data/sales.json"))
    rate = F.S["usd_to_cad"]
    items = []
    for it in data["items"]:
        if not F.is_mens(it):          # women's items can be added later
            continue
        kind = F.kind_of(it)
        if not kind or it["off_pct"] < F.S.get("catalog_min_off_pct", 10):
            continue
        r = F.RATES.get(it.get("currency"))
        if r is None:
            continue
        tags = F.tag_list(it)
        row = {
            "store": it["store"], "title": it["title"], "url": it["url"], "image": it["image"],
            "images": it.get("images") or ([it["image"]] if it.get("image") else []),
            "price_cad": round(it["price"] * r, 2), "was_cad": round(it["was"] * r, 2),
            "off_pct": it["off_pct"], "sizes": it.get("sizes") or [], "kind": kind,
            "colors": sorted(B.colors_of(it)), **ST.style_of(it),
        }
        # flags are only written when they differ from the usual, to keep the file small for phones
        if "final-sale" in tags:
            row["final_sale"] = True
        if it.get("sizes_verified", True) is False:
            row["sizes_verified"] = False
        if it.get("sizes_unknown"):
            row["sizes_unknown"] = True
        row.pop("materials", None)          # not used by the site
        for k in ("sizes", "colors", "vibes"):
            if not row.get(k):
                row.pop(k, None)
        items.append(row)
    # per-store cap, lowered on big sale days so the whole catalog stays quick to load on a phone
    cap, limit = F.S.get("max_items_per_store", 150), F.S.get("max_catalog_items", 9000)
    kept = cap_per_store(items, cap)
    while len(kept) > limit and cap > 40:
        cap -= 10
        kept = cap_per_store(items, cap)
    if cap < F.S.get("max_items_per_store", 150):
        print(f"Big sale day: capped stores at {cap} items to stay under {limit}")
    items = kept
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "stores": store_regions(), "items": items}
    with open("data/catalog.json", "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"Catalog: {len(items)} items")
    for k in ("top", "bottom", "shoes", "outerwear"):
        print(f"  {k}: {sum(1 for i in items if i['kind'] == k)}")


if __name__ == "__main__":
    main()
