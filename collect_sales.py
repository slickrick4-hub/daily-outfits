"""Reads each store's public product list and saves what is on sale to data/sales.json."""
import json, os, time, urllib.request
from datetime import datetime, timezone

HEADERS = {"User-Agent": "personal-outfit-project/0.1 (personal use, runs once a day)"}
MAX_PAGES = 8  # 250 products per page


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def size_names(product):
    names = [o.get("name", "").lower() for o in product.get("options", [])]
    found = set()
    for v in product.get("variants", []):
        if not v.get("available"):
            continue
        for i, n in enumerate(names):
            if n in ("size", "waist", "waist size", "jean size") and v.get(f"option{i + 1}"):
                found.add(v[f"option{i + 1}"])
    return sorted(found)


def best_sale(product):
    best = None
    for v in product.get("variants", []):
        if not v.get("available"):
            continue
        price = float(v.get("price") or 0)
        was = float(v.get("compare_at_price") or 0)
        if was > price > 0:
            off = (was - price) / was
            if best is None or off > best[2]:
                best = (price, was, off)
    return best


def shop_currency(base, fallback):
    """Shopify stores publish their currency at /meta.json; use it when available."""
    try:
        return fetch(base + "/meta.json").get("currency") or fallback
    except Exception:
        return fallback


def collect(store):
    items = []
    base = "https://" + store["domain"]
    currency = shop_currency(base, store.get("currency"))
    for page in range(1, MAX_PAGES + 1):
        sep = "&" if "?" in store["path"] else "?"
        data = fetch(f"{base}{store['path']}{sep}limit=250&page={page}")
        products = data.get("products", [])
        if not products:
            break
        for p in products:
            sale = best_sale(p)
            if not sale:
                continue
            images = p.get("images") or []
            items.append({
                "store": store["name"],
                "title": p.get("title"),
                "type": p.get("product_type"),
                "tags": p.get("tags"),
                "url": f"{base}/products/{p.get('handle')}",
                "image": images[0]["src"] if images else None,
                "price": sale[0],
                "was": sale[1],
                "off_pct": round(sale[2] * 100),
                "currency": currency,
                "sizes": size_names(p),
            })
        time.sleep(1.5)
    return items


def main():
    stores = json.load(open("stores.json"))
    all_items = []
    for s in stores:
        try:
            got = collect(s)
            print(f"{s['name']}: {len(got)} items on sale" + (f" ({got[0]['currency']})" if got else ""))
            all_items += got
        except Exception as e:
            print(f"{s['name']}: skipped ({e})")
    os.makedirs("data", exist_ok=True)
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "items": all_items}
    with open("data/sales.json", "w") as f:
        json.dump(out, f)
    print(f"Saved {len(all_items)} items")


if __name__ == "__main__":
    main()
