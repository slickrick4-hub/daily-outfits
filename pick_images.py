"""Chooses the cleanest product photo (plain background, no person) for each catalog item.
Results are remembered in data/image_cache.json so each photo is only analysed once."""
import io, json, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True
HEADERS = {"User-Agent": "personal-outfit-project/0.1 (personal use, runs once a day)"}
DEADLINE = time.monotonic() + 20 * 60   # stop after 20 minutes; the rest continues tomorrow


def thumb_url(u):
    if "cdn.shopify.com" in u:
        return u + ("&" if "?" in u else "?") + "width=240"
    return u


def load(u):
    req = urllib.request.Request(thumb_url(u), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=12) as r:
        data = r.read(900000)
    return Image.open(io.BytesIO(data)).convert("RGB")


def analyse(img):
    img.thumbnail((100, 130))
    w, h = img.size
    px = img.load()
    band = max(2, int(min(w, h) * 0.06))
    border = [px[x, y] for y in range(h) for x in range(w) if x < band or x >= w - band or y < band or y >= h - band]
    n = len(border)
    mean = [sum(p[i] for p in border) / n for i in range(3)]
    std = (sum(sum((p[i] - mean[i]) ** 2 for i in range(3)) / 3 for p in border) / n) ** 0.5
    inner = [px[x, y] for y in range(band, h - band) for x in range(band, w - band)]
    diff = sum(1 for p in inner if sum(abs(p[i] - mean[i]) for i in range(3)) / 3 > 28) / len(inner)
    skin = sum(1 for r, g, b in inner if r > 95 and g > 40 and b > 20 and r > g > b and r - g > 15 and r - b > 30) / len(inner)
    plain = std < 14 and sum(mean) / 3 > 185      # even, light background
    return plain, diff, skin


def quality(a):
    plain, diff, skin = a
    q = (2 if plain else 0) + min(diff, 0.6)
    if skin > 0.08:
        q -= 1.2                                  # probably a person in the shot
    if diff < 0.08:
        q -= 1                                    # nearly empty picture
    return q


def main():
    cat = json.load(open("data/catalog.json"))
    try:
        cache = json.load(open("data/image_cache.json"))
    except Exception:
        cache = {}
    todo = []
    for it in cat["items"]:
        imgs = it.get("images") or ([it["image"]] if it.get("image") else [])
        key = "|".join(imgs)
        c = cache.get(it["url"])
        if c and c["key"] == key:
            it["image"] = c["image"]
        elif len(imgs) > 1:
            todo.append((it, imgs, key))
        elif imgs:
            cache[it["url"]] = {"key": key, "image": imgs[0]}

    def work(t):
        it, imgs, key = t
        if time.monotonic() > DEADLINE:
            return None
        scores = []
        for u in imgs:
            try:
                scores.append(quality(analyse(load(u))))
            except Exception:
                scores.append(-9)
        best = max(range(len(imgs)), key=lambda i: (scores[i], -i)) if max(scores) > -9 else 0
        return it, key, imgs[best]

    done = changed = 0
    with ThreadPoolExecutor(8) as ex:
        for res in ex.map(work, todo):
            if res:
                it, key, img = res
                done += 1
                changed += img != it["image"]
                it["image"] = img
                cache[it["url"]] = {"key": key, "image": img}
    for it in cat["items"]:
        it.pop("images", None)
    live = {i["url"] for i in cat["items"]}
    cache = {u: v for u, v in cache.items() if u in live}
    with open("data/catalog.json", "w") as f:
        json.dump(cat, f, separators=(",", ":"))
    with open("data/image_cache.json", "w") as f:
        json.dump(cache, f, separators=(",", ":"))
    print(f"Photos: analysed {done} of {len(todo)} new items, switched {changed} to a cleaner shot")


if __name__ == "__main__":
    main()
