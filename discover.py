"""Tests candidate store domains from candidates.txt and adds the ones with a readable product feed
to stores.json. Rejected domains are remembered for 30 days in rejected.json."""
import html, json, re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import collect_sales as cs

RETRY_AFTER_DAYS = 30


def clean(line):
    line = line.split("#")[0].strip().lower()
    line = re.sub(r"^https?://", "", line).split("/")[0]
    return line[4:] if line.startswith("www.") else line


def classify(products, name_of, tags_of, sale_of):
    mens = womens = sales = 0
    for p in products:
        text = (name_of(p) + " " + tags_of(p)).lower()
        if re.search(r"\bwomen|\bwomens|\bladies", text):
            womens += 1
        elif re.search(r"\bmens?\b|men\'s|unisex", text):
            mens += 1
        sales += bool(sale_of(p))
    return mens, womens, sales


def test(domain):
    base = "https://" + domain
    errors = []
    # 1) Shopify
    try:
        products = (cs.fetch(base + "/products.json?limit=250").get("products") or [])
        if len(products) >= 5:
            mens, womens, sales = classify(
                products, lambda p: (p.get("title") or "") + " " + (p.get("product_type") or ""), lambda p: str(p.get("tags") or ""),
                lambda p: any(float(v.get("compare_at_price") or 0) > float(v.get("price") or 0) > 0 for v in p.get("variants", [])))
            if mens == 0 and womens > 0:
                return domain, None, "women's only (no men's items found)"
            name, cur = domain, "USD"
            try:
                meta = cs.fetch(base + "/meta.json")
                name, cur = meta.get("name") or domain, meta.get("currency") or cur
            except Exception:
                pass
            return domain, {"name": name, "domain": domain, "path": "/products.json", "currency": cur, "platform": "shopify"}, f"Shopify, {len(products)} products, {sales} on sale"
        errors.append("Shopify feed has fewer than 5 products")
    except Exception as e:
        errors.append(f"Shopify: {type(e).__name__}")
    # 2) WooCommerce
    try:
        products = cs.fetch(base + "/wp-json/wc/store/v1/products?per_page=100")
        if isinstance(products, list) and len(products) >= 5:
            mens, womens, sales = classify(
                products, lambda p: html.unescape(p.get("name") or ""), lambda p: " ".join(c.get("name", "") for c in (p.get("categories") or [])),
                lambda p: p.get("on_sale"))
            if mens == 0 and womens > 0:
                return domain, None, "women's only (no men's items found)"
            cur = ((products[0].get("prices") or {}).get("currency_code")) or "USD"
            return domain, {"name": domain, "domain": domain, "path": "", "currency": cur, "platform": "woocommerce"}, f"WooCommerce, {len(products)} products, {sales} on sale"
        errors.append("WooCommerce feed has fewer than 5 products")
    except Exception as e:
        errors.append(f"WooCommerce: {type(e).__name__}")
    return domain, None, " | ".join(errors)


def main():
    try:
        stores = json.load(open("stores.json"))
    except Exception:
        stores = []
    try:
        rejected = json.load(open("rejected.json"))
    except Exception:
        rejected = {}
    have = {s["domain"] for s in stores}
    today = date.today()
    todo = []
    for line in open("candidates.txt"):
        d = clean(line)
        if not d or d in have or d in todo:
            continue
        r = rejected.get(d)
        if r and date.fromisoformat(r["date"]) > today - timedelta(days=RETRY_AFTER_DAYS):
            continue
        todo.append(d)
    print(f"Testing {len(todo)} candidate stores")
    added = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        for d, store, note in ex.map(test, todo):
            if store:
                stores.append(store)
                rejected.pop(d, None)
                added += 1
                print(f"ADDED  {store['name']} ({d}) [{store['currency']}]: {note}")
            else:
                rejected[d] = {"reason": note, "date": str(today)}
                print(f"no     {d}: {note}")
    json.dump(stores, open("stores.json", "w"), indent=1)
    json.dump(rejected, open("rejected.json", "w"), indent=1)
    print(f"Added {added}. Store list now has {len(stores)} stores.")


if __name__ == "__main__":
    main()
