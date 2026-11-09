"""Reads each store's public product list and saves what is on sale to data/sales.json."""
import json, os, time, urllib.error, urllib.request
import html
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

HEADERS = {"User-Agent": "personal-outfit-project/0.1 (personal use, runs once a day)"}
MAX_PAGES = 8  # 250 products per page


def fetch(url, tries=3):
    """Fetch JSON, retrying politely when a store says 'slow down' or drops the connection."""
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and n < tries - 1:
                time.sleep(10 * (n + 1))
                continue
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if n < tries - 1:
                time.sleep(5 * (n + 1))
                continue
            raise


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
                "images": [i["src"] for i in images[:4]],
                "price": sale[0],
                "was": sale[1],
                "off_pct": round(sale[2] * 100),
                "currency": currency,
                "sizes": size_names(p),
            })
        time.sleep(1.5)
    return items


def woo_money(v, minor):
    try:
        return int(v) / (10 ** int(minor))
    except Exception:
        return 0.0


def collect_woo(store):
    """WooCommerce stores publish a public Store API. Prices come in minor units (cents)."""
    items = []
    base = "https://" + store["domain"]
    for page in range(1, 16):
        products = fetch(f"{base}/wp-json/wc/store/v1/products?per_page=100&page={page}")
        if not isinstance(products, list) or not products:
            break
        for p in products:
            pr = p.get("prices") or {}
            minor = pr.get("currency_minor_unit", 2)
            price, was = woo_money(pr.get("price"), minor), woo_money(pr.get("regular_price"), minor)
            if not (p.get("on_sale") and was > price > 0 and p.get("is_in_stock", True)):
                continue
            sizes = []
            for a in p.get("attributes") or []:
                if str(a.get("name", "")).lower() in ("size", "sizes", "waist", "shoe size", "taille"):
                    sizes += [str(t.get("name")) for t in a.get("terms") or [] if t.get("name")]
            cats = [html.unescape(c.get("name", "")) for c in p.get("categories") or []]
            tags = cats + [html.unescape(t.get("name", "")) for t in p.get("tags") or []]
            images = [i.get("src") for i in p.get("images") or [] if i.get("src")]
            items.append({
                "store": store["name"], "title": html.unescape(p.get("name") or ""), "type": cats[0] if cats else "",
                "tags": tags, "url": p.get("permalink"), "image": images[0] if images else None, "images": images[:4],
                "price": round(price, 2), "was": round(was, 2), "off_pct": round((was - price) / was * 100),
                "currency": pr.get("currency_code") or store.get("currency"), "sizes": sizes,
                "sizes_verified": False,   # the Store API doesn't say which sizes are in stock
            })
        if len(products) < 100:
            break
        time.sleep(1.5)
    return items


def run_store(s):
    try:
        return s, (collect_woo(s) if s.get("platform") == "woocommerce" else collect(s)), None
    except Exception as e:
        return s, None, e


def main():
    stores = json.load(open("stores.json"))
    all_items = []
    with ThreadPoolExecutor(max_workers=6) as ex:      # six stores at a time, one request at a time per store
        for s, got, err in ex.map(run_store, stores):
            if err:
                print(f"{s['name']}: skipped ({err})")
                continue
            print(f"{s['name']}: {len(got)} items on sale" + (f" ({got[0]['currency']})" if got else ""))
            all_items += got
    os.makedirs("data", exist_ok=True)
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "items": all_items}
    with open("data/sales.json", "w") as f:
        json.dump(out, f)
    print(f"Saved {len(all_items)} items")


if __name__ == "__main__":
    main()
