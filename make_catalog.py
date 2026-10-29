"""Turns data/sales.json into data/catalog.json: every in-season men's sale item, tagged,
with all of its sizes. Sizes and budget are applied later in each person's browser."""
import json
from datetime import datetime, timezone

import filter_sales as F
import build_outfit as B


def main():
    data = json.load(open("data/sales.json"))
    rate = F.S["usd_to_cad"]
    items = []
    for it in data["items"]:
        if not F.is_mens(it):          # women's items can be added later
            continue
        kind = F.kind_of(it)
        if not kind or it["off_pct"] < F.S["min_off_pct"]:
            continue
        r = rate if it.get("currency") == "USD" else 1
        tags = F.tag_list(it)
        items.append({
            "store": it["store"], "title": it["title"], "url": it["url"], "image": it["image"],
            "price_cad": round(it["price"] * r, 2), "was_cad": round(it["was"] * r, 2),
            "off_pct": it["off_pct"], "sizes": it.get("sizes") or [], "kind": kind,
            "final_sale": "final-sale" in tags, "colors": sorted(B.colors_of(it)),
            "gender": "unisex" if ("unisex" in it["title"].lower() or "unisex" in tags) else "men",
        })
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "items": items}
    with open("data/catalog.json", "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"Catalog: {len(items)} items")
    for k in ("top", "bottom", "shoes", "outerwear"):
        print(f"  {k}: {sum(1 for i in items if i['kind'] == k)}")


if __name__ == "__main__":
    main()
