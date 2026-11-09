"""Pulls sale items for big retailers (Uniqlo, Abercrombie, ...) from Google Shopping through SerpApi.
Needs a SERPAPI_KEY secret. Runs a few searches per day (to stay inside the free plan) and remembers
results for keep_days days, so the catalog fills up over about a week."""
import json, os, urllib.parse, urllib.request
from collections import Counter
from datetime import date, timedelta

CFG = json.load(open("shopping.json"))
CACHE = "data/shopping_cache.json"


def search(q):
    params = {"engine": "google_shopping", "q": q, "gl": CFG["country"], "hl": CFG.get("language", "en"),
              "google_domain": CFG.get("google_domain", "google.ca"), "tbs": "sales:1", "api_key": os.environ["SERPAPI_KEY"]}
    with urllib.request.urlopen("https://serpapi.com/search.json?" + urllib.parse.urlencode(params), timeout=60) as r:
        return json.load(r)


def retailer_of(source):
    s = (source or "").lower()
    for name in CFG["retailers"]:
        if name.lower() in s:
            return name
    return None


def to_item(r, retailer):
    price, old = r.get("extracted_price"), r.get("extracted_old_price")
    link = r.get("link") or r.get("product_link")
    if not (price and old and old > price and link):
        return None
    thumb = r.get("thumbnail")
    return {"store": retailer, "title": r.get("title") or "", "type": "", "tags": ["mens"], "url": link,
            "image": thumb, "images": [thumb] if thumb else [], "price": float(price), "was": float(old),
            "off_pct": round((old - price) / old * 100), "currency": CFG["currency"], "sizes": [],
            "sizes_verified": False, "sizes_unknown": True}


def main():
    if not os.environ.get("SERPAPI_KEY"):
        print("No SERPAPI_KEY set, skipping the big-retailer search")
        return
    sales = json.load(open("data/sales.json"))
    queries = [f"{r} men's {c} sale" for r in CFG["retailers"] for c in CFG["categories"]]
    n = min(CFG.get("queries_per_run", 8), len(queries))
    start = (date.today().toordinal() * n) % len(queries)
    try:
        cache = json.load(open(CACHE))
    except Exception:
        cache = {}
    today, seen_sources = str(date.today()), Counter()
    for q in [queries[(start + i) % len(queries)] for i in range(n)]:
        try:
            results = search(q).get("shopping_results") or []
        except Exception as e:
            print(f"{q}: failed ({str(e)[:80]})")
            continue
        kept = 0
        for r in results:
            seen_sources[r.get("source") or "?"] += 1
            retailer = retailer_of(r.get("source"))
            item = to_item(r, retailer) if retailer else None
            if item:
                cache[item["url"]] = dict(item, seen=today)
                kept += 1
        print(f"{q}: {len(results)} results, {kept} kept")
    cutoff = str(date.today() - timedelta(days=CFG.get("keep_days", 14)))
    cache = {u: i for u, i in cache.items() if i["seen"] >= cutoff}
    sales["items"] += [{k: v for k, v in i.items() if k != "seen"} for i in cache.values()]
    json.dump(cache, open(CACHE, "w"), separators=(",", ":"))
    json.dump(sales, open("data/sales.json", "w"))
    print("Retailers seen in results:", ", ".join(f"{s} ({c})" for s, c in seen_sources.most_common(12)))
    print(f"Added {len(cache)} big-retailer items")


if __name__ == "__main__":
    main()
