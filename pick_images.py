"""Chooses the cleanest product photo (plain background, no person) for each catalog item.
Results are remembered in data/image_cache.json so each photo is only analysed once."""
import colorsys, io, json, time, urllib.request
from collections import Counter
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


def family(r, g, b):
    """Map one pixel to the same colour families the site uses (see COLORS in build_outfit.py)."""
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    h *= 360
    if v < 0.17:
        return "navy" if 200 <= h < 250 and s > 0.35 and v > 0.08 else "black"   # very dark navy
    if s < 0.13 or (s < 0.22 and v > 0.8):
        return "white" if v > 0.82 else ("black" if v < 0.3 else "grey")
    if s > 0.55 and v > 0.65 and (40 <= h < 70 or 270 <= h < 345 or (20 <= h < 40 and s > 0.75)):
        return "bright"
    if (h < 10 or h >= 345) and s > 0.45:
        return "red"                                           # camel and espresso sit just above this
    if h < 40:
        return "brown" if v < 0.55 else ("tan" if s < 0.6 else "bright")
    if h < 70:
        return "green" if v < 0.6 else "tan"                   # olive vs khaki
    if h < 175:
        return "green"
    if h < 255:
        return "navy" if v < 0.4 else "blue"
    return "red" if h >= 300 else "navy"


def garment_colors(img):
    """Main colour(s) of the garment in a product photo: pixels that differ from the background,
    in the middle of the picture, ignoring skin. Returns [] when it can't tell."""
    img = img.copy()
    img.thumbnail((100, 130))
    w, h = img.size
    px = img.load()
    band = max(2, int(min(w, h) * 0.06))
    border = [px[x, y] for y in range(h) for x in range(w) if x < band or x >= w - band or y < band or y >= h - band]
    bg = [sum(p[i] for p in border) / len(border) for i in range(3)]
    votes, total = Counter(), 0
    for y in range(int(h * .15), int(h * .85)):
        for x in range(int(w * .15), int(w * .85)):
            r, g, b = px[x, y]
            total += 1
            if (abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2])) / 3 < 28:
                continue                                       # background
            if r > 95 and g > 40 and b > 20 and r > g > b and r - g > 15 and r - b > 30:
                continue                                       # skin
            votes[family(r, g, b)] += 1
    fg = sum(votes.values())
    if votes["black"] and votes["black"] < fg * 0.55:
        fg -= votes.pop("black")                               # dark pixels are mostly shadows and folds
    if not total or fg < total * 0.08:
        return []                                              # garment too small or same colour as background
    (top, n1), *rest = votes.most_common(2) + [(None, 0)]
    out = [top]
    if rest and rest[0][0] and rest[0][1] >= fg * 0.35:
        out.append(rest[0][0])                                 # clearly two-tone
    return sorted(out)


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
    # items whose title names no colour: read it from the chosen photo (cached per photo).
    # About 2 in 3 come out right or close, so the site uses these as hints only ("photo_colors"),
    # never to hide a piece.
    need = []
    for it in cat["items"]:
        if it.get("colors") or not it.get("image"):
            continue
        c = cache.get(it["url"]) or {}
        if c.get("cimg") == it["image"]:
            if c.get("colors"):
                it["photo_colors"] = c["colors"]
        else:
            need.append(it)

    def colour_work(it):
        if time.monotonic() > DEADLINE:
            return None
        try:
            return it, garment_colors(load(it["image"]))
        except Exception:
            return it, []

    coloured = 0
    with ThreadPoolExecutor(8) as ex:
        for res in ex.map(colour_work, need):
            if res:
                it, cols = res
                if cols:
                    it["photo_colors"] = cols
                coloured += bool(cols)
                cache.setdefault(it["url"], {"key": "", "image": it["image"]}).update(cimg=it["image"], colors=cols)
    for it in cat["items"]:
        it.pop("images", None)
    live = {i["url"] for i in cat["items"]}
    cache = {u: v for u, v in cache.items() if u in live}
    with open("data/catalog.json", "w") as f:
        json.dump(cat, f, separators=(",", ":"))
    with open("data/image_cache.json", "w") as f:
        json.dump(cache, f, separators=(",", ":"))
    print(f"Photos: analysed {done} of {len(todo)} new items, switched {changed} to a cleaner shot")
    print(f"Colours: read {coloured} of {len(need)} uncoloured items from their photos")


if __name__ == "__main__":
    main()
