"""Tags catalog pieces from their product photo with FashionCLIP (an open-source fashion image model,
MIT licence): shape, look, pattern and colour. Runs on GitHub, never in visitors' browsers.

Daily:  python tag_photos.py [--minutes 20]
  tags pieces whose photo hasn't been seen before (remembered in data/photo_tags.json) and writes
  the confident tags into data/catalog.json. Checked by eye on 80 photos (Nov 2026): colour 94% right,
  pattern 96%, confident oversized/slim calls 93%. The "look" tag was only ~56% right, so it isn't used.
Test:   python tag_photos.py --test 300
  tags a spread-out sample and writes contact sheets to test_out/ to check by eye."""
import io, json, os, random, re, sys, time, urllib.request

from PIL import Image, ImageDraw, ImageFont

MODEL = "patrickjohncyh/fashion-clip"
HEADERS = {"User-Agent": "personal-outfit-project/0.1 (personal use, runs once a day)"}

# the garment word used in the descriptions, read from the piece's name (first match wins)
NOUNS = [("hood", "hoodie"), ("sweatshirt", "sweatshirt"), ("cardigan", "cardigan"), ("sweater", "sweater"),
         ("knit", "sweater"), ("polo", "polo shirt"), ("henley", "henley"), ("t-shirt", "t-shirt"), ("tee", "t-shirt"),
         ("overshirt", "overshirt"), ("shirt", "shirt"), ("blazer", "blazer"), ("puffer", "puffer jacket"),
         ("parka", "parka"), ("coat", "coat"), ("vest", "vest"), ("jacket", "jacket"), ("jean", "jeans"),
         ("denim", "jeans"), ("cargo", "cargo pants"), ("chino", "chinos"), ("trouser", "trousers"), ("pant", "pants"),
         ("boot", "boots"), ("loafer", "loafers"), ("sneaker", "sneakers"), ("trainer", "sneakers")]
KIND_NOUN = {"top": "top", "bottom": "pants", "outerwear": "jacket", "shoes": "shoes"}

SHAPE_UP = [("wide", "an oversized boxy {n}"), ("regular", "a regular fit {n}"), ("slim", "a slim fitted {n}")]
SHAPE_LO = [("wide", "baggy wide-leg {n}"), ("regular", "straight-leg {n}"), ("slim", "slim tapered {n}")]
LOOK = [("street", "streetwear {n}"), ("classic", "preppy classic menswear {n}"), ("rugged", "rugged workwear {n}"),
        ("minimal", "minimalist plain {n}"), ("casual", "sporty athleisure {n}")]
PATTERN = [("solid", "a plain solid colour {n}"), ("stripe", "a striped {n}"), ("plaid", "a plaid check {n}"),
           ("graphic", "a {n} with a graphic print or logo"), ("camo", "a camouflage {n}")]
# colour descriptions -> the site's colour families
COLOUR = [("black", "a black {n}"), ("white", "a white {n}"), ("white", "a cream off-white {n}"), ("grey", "a grey {n}"),
          ("navy", "a navy blue {n}"), ("blue", "a light blue {n}"), ("blue", "a mid blue denim {n}"),
          ("brown", "a brown {n}"), ("tan", "a tan beige {n}"), ("green", "an olive green {n}"), ("green", "a green {n}"),
          ("red", "a red {n}"), ("red", "a burgundy {n}"), ("bright", "a yellow {n}"), ("bright", "a pink {n}"),
          ("bright", "an orange {n}"), ("bright", "a purple {n}")]


def noun_of(item):
    t = item["title"].lower()
    for w, n in NOUNS:
        if w in t:
            return n
    return KIND_NOUN[item["kind"]]


def load(u):
    if "cdn.shopify.com" in u or "/cdn/shop/" in u:
        u += ("&" if "?" in u else "?") + "width=320"
    with urllib.request.urlopen(urllib.request.Request(u, headers=HEADERS), timeout=15) as r:
        return Image.open(io.BytesIO(r.read(2_000_000))).convert("RGB")


class Tagger:
    def __init__(self):
        import torch
        from transformers import CLIPModel, CLIPProcessor
        self.torch = torch
        self.model = CLIPModel.from_pretrained(MODEL).eval()
        self.proc = CLIPProcessor.from_pretrained(MODEL)
        self._text = {}

    def text(self, prompts):
        key = tuple(prompts)
        if key not in self._text:
            with self.torch.no_grad():
                t = self.proc(text=list(prompts), return_tensors="pt", padding=True)
                e = self.model.get_text_features(**t)
            self._text[key] = e / e.norm(dim=-1, keepdim=True)
        return self._text[key]

    def image(self, img):
        with self.torch.no_grad():
            e = self.model.get_image_features(**self.proc(images=img, return_tensors="pt"))
        return e / e.norm(dim=-1, keepdim=True)

    def pick(self, emb, options, noun):
        """Best option and its probability (summed over descriptions that map to the same tag)."""
        prompts = [p.format(n=noun) for _, p in options]
        logits = (self.model.logit_scale.exp() * emb @ self.text(prompts).T)[0]
        probs = logits.softmax(-1).tolist()
        tot = {}
        for (tag, _), p in zip(options, probs):
            tot[tag] = tot.get(tag, 0) + p
        best = max(tot, key=tot.get)
        return best, round(tot[best], 2)

    def tags(self, item, img, look=True):
        emb, n = self.image(img), noun_of(item)
        out = {"colour": self.pick(emb, COLOUR, n)}
        if look:
            out["look"] = self.pick(emb, LOOK, n)
        if item["kind"] != "shoes":
            out["shape"] = self.pick(emb, SHAPE_LO if item["kind"] == "bottom" else SHAPE_UP, n)
            out["pattern"] = self.pick(emb, PATTERN, n)
        return out


def sample(items, n):
    """A spread-out sample: every kind, and extra streetwear pieces since that's where words fall short."""
    rnd = random.Random(7)
    by = {}
    for it in items:
        if it.get("image"):
            by.setdefault(it["kind"], []).append(it)
    want = {"top": .4, "bottom": .3, "outerwear": .15, "shoes": .15}
    out = []
    for k, share in want.items():
        pool = by.get(k, [])
        street = [i for i in pool if "street" in (i.get("vibes") or [])]
        rest = [i for i in pool if i not in street]
        m = int(n * share)
        pick = rnd.sample(street, min(len(street), m // 3))
        out += pick + rnd.sample(rest, min(len(rest), m - len(pick)))
    rnd.shuffle(out)
    return out[:n]


def sheet(rows, path):
    """Contact sheet: 4 x 5 photos with what the name says and what the photo says."""
    W, H, cols = 300, 470, 4
    img = Image.new("RGB", (W * cols, H * ((len(rows) + cols - 1) // cols)), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=13)
    except TypeError:
        font = ImageFont.load_default()
    for k, (n, it, ph, tags) in enumerate(rows):
        x, y = (k % cols) * W, (k // cols) * H
        th = ph.copy()
        th.thumbnail((W - 10, 300))
        img.paste(th, (x + 5, y + 5))
        words = f"words: {','.join(it.get('colors') or ['-'])} | {it.get('fit') or '-'} | {','.join(it.get('vibes') or ['-'])}"
        lines = [f"#{n} {it['kind']} - {it['store'][:22]}", it["title"][:40], words[:46]]
        lines += [f"{k2}: {v[0]} ({v[1]})" for k2, v in tags.items()]
        for j, line in enumerate(lines):
            d.text((x + 6, y + 312 + j * 17), line, fill="black", font=font)
    img.save(path)


def test(n):
    cat = json.load(open("data/catalog.json"))
    pieces = sample(cat["items"], n)
    t0 = time.monotonic()
    tg = Tagger()
    print(f"Model loaded in {time.monotonic() - t0:.0f}s")
    os.makedirs("test_out", exist_ok=True)
    rows, report, t1 = [], [], time.monotonic()
    for i, it in enumerate(pieces):
        try:
            ph = load(it["image"])
        except Exception as e:
            print(f"skip {it['title'][:40]}: {str(e)[:60]}")
            continue
        tags = tg.tags(it, ph)
        rows.append((len(rows) + 1, it, ph, tags))
        report.append({"n": len(rows), "store": it["store"], "title": it["title"], "kind": it["kind"],
                       "image": it["image"], "words": {"colors": it.get("colors"), "fit": it.get("fit"),
                       "vibes": it.get("vibes")}, "photo": tags})
    secs = time.monotonic() - t1
    print(f"Tagged {len(rows)} photos in {secs:.0f}s ({secs / max(1, len(rows)):.2f}s each, including download)")
    for k in range(0, len(rows), 20):
        sheet(rows[k:k + 20], f"test_out/sheet_{k // 20 + 1:02d}.png")
    json.dump(report, open("test_out/report.json", "w"), indent=1)
    # quick summary: how sure the model is, per tag
    for tag in ("shape", "look", "pattern", "colour"):
        ps = [r["photo"][tag][1] for r in report if tag in r["photo"]]
        if ps:
            print(f"{tag:8} median confidence {sorted(ps)[len(ps) // 2]:.2f}, sure (>=0.6) on {sum(p >= .6 for p in ps)} of {len(ps)}")


CACHE = "data/photo_tags.json"


def apply(it, t):
    """Write the confident tags into a catalog item. Words from the store always win."""
    c, cp = t.get("c"), t.get("cp", 0)
    if c and cp >= 0.6 and not it.get("colors"):
        it["photo_colors"] = [c]                     # replaces the rougher pixel-based guess
    p, pp = t.get("p"), t.get("pp", 0)
    if p and p != "solid" and pp >= 0.8 and not (p == "graphic" and it["kind"] == "bottom"):
        it["pattern"] = True                         # plain jeans sometimes read as "graphic"
        if p == "graphic":
            it["ptype"] = "graphic"
    s, sp = t.get("s"), t.get("sp", 0)
    if s in ("wide", "slim") and sp >= 0.85 and not it.get("fit"):
        it["pshape"] = s                             # only confident oversized/slim calls


def daily(minutes):
    cat = json.load(open("data/catalog.json"))
    try:
        cache = json.load(open(CACHE))
    except Exception:
        cache = {}
    todo = [it for it in cat["items"] if it.get("image") and it["image"] not in cache]
    print(f"Photo tags: {len(todo)} new photos to tag")
    deadline = time.monotonic() + minutes * 60
    done = 0
    if todo:
        tg = Tagger()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(6) as ex:           # download photos in parallel, tag one at a time
            for k in range(0, len(todo), 60):          # in small batches, so the time limit is respected
                if time.monotonic() > deadline:
                    break
                for it, ph in ex.map(lambda i: (i, _safe_load(i["image"])), todo[k:k + 60]):
                    if ph is None:
                        cache[it["image"]] = {}
                        continue
                    t = tg.tags(it, ph, look=False)
                    row = {"c": t["colour"][0], "cp": t["colour"][1]}
                    if "pattern" in t:
                        row.update(p=t["pattern"][0], pp=t["pattern"][1], s=t["shape"][0], sp=t["shape"][1])
                    cache[it["image"]] = row
                    done += 1
    live = {it["image"] for it in cat["items"] if it.get("image")}
    cache = {u: v for u, v in cache.items() if u in live}
    for it in cat["items"]:
        if it.get("image") in cache:
            apply(it, cache[it["image"]])
    for path, data in (("data/catalog.json", cat), (CACHE, cache)):   # write-then-rename, never half a file
        with open(path + ".tmp", "w") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(path + ".tmp", path)
    left = sum(1 for it in cat["items"] if it.get("image") and it["image"] not in cache)
    n = lambda k: sum(1 for it in cat["items"] if it.get(k))
    print(f"Photo tags: tagged {done} today, {left} left for the next run; "
          f"{n('pshape')} pieces have a photo shape, {n('ptype')} a graphic print")


def _safe_load(u):
    try:
        return load(u)
    except Exception:
        return None


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--test":
        test(int(sys.argv[2]))
    else:
        mins = float(sys.argv[sys.argv.index("--minutes") + 1]) if "--minutes" in sys.argv else 20
        daily(mins)
