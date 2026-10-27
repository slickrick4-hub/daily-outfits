"""Picks today's outfit from data/filtered.json: one top + one bottom (+ optional layer) within budget."""
import json, re
from datetime import date

STYLE = json.load(open("style.json"))
BUDGET = STYLE["outfit_budget_cad"]


COLORS = {
    "black": ["black", "coal", "onyx", "jet"],
    "white": ["white", "natural", "marshmallow", "cream", "oat", "ecru", "ivory", "alabaster", "bone", "lino"],
    "grey": ["grey", "gray", "charcoal", "slate", "ash", "smoke", "fog", "asphalt", "dove", "nimbus"],
    "navy": ["navy", "indigo", "midnight", "nocturne", "ink"],
    "blue": ["blue", "azure", "chambray", "sky", "columbia", "aura"],
    "brown": ["brown", "otter", "truffle", "espresso", "coffee", "camel", "walnut", "sable", "chocolate",
              "bark", "teak", "cocoa", "cappuccino"],
    "tan": ["khaki", "tan", "taupe", "sand", "sandstone", "stone", "beige", "desert", "safari", "mushroom"],
    "green": ["olive", "green", "sage", "forest", "pine", "army", "moss", "spruce", "cilantro", "cypress"],
    "red": ["burgundy", "red", "cabernet", "rust", "brick", "canyon", "wine", "maroon", "plum"],
    "bright": ["yellow", "orange", "pink", "purple", "salsa", "sorbet", "lemon", "goldfinch", "mauve"],
}
DARK = {"black", "navy", "grey"}


def families(text):
    return {f for f, ws in COLORS.items() if any(re.search(r"\b" + w + r"s?\b", text) for w in ws)}


def colors_of(item):
    found = families((item.get("title") or "").lower())
    if not found:  # many titles have no color, so fall back to short color-like tags
        for t in item.get("tags") or []:
            t = str(t).lower()
            if t.startswith(("color:", "primary color:")) or len(t.split()) <= 2:
                found |= families(t)
    return found


def color_bonus(parts):
    fam = set()
    for p in parts:
        fam |= colors_of(p)
    if not fam:
        return 0, fam
    b = 0
    if fam <= DARK:
        b -= 2.5          # all dark neutrals looks flat
    if fam - DARK:
        b += 1.5          # at least one color that lifts the outfit
    if len(fam) >= 4:
        b -= 3            # too many colors
    if "bright" in fam:
        b -= 2
    return b, fam


def hits(title, words):
    return sum(1 for w in words if re.search(r"\b" + re.escape(w), title))


def score(item):
    title = (item.get("title") or "").lower()
    s = item["off_pct"] / 10
    s += 2 * hits(title, STYLE["like_words"])
    s -= 3 * hits(title, STYLE["avoid_words"])
    if item.get("final_sale"):
        s -= STYLE.get("final_sale_penalty", 1)
    return s


def slim(i):
    keys = ["store", "title", "url", "image", "price_cad", "was_cad", "off_pct", "sizes", "final_sale", "kind"]
    return {k: i.get(k) for k in keys}


def main():
    items = json.load(open("data/filtered.json"))["items"]
    # drop anything that matches a word you said you avoid
    items = [i for i in items if hits((i.get("title") or "").lower(), STYLE["avoid_words"]) == 0]
    tops = [i for i in items if i["kind"] == "top"]
    bottoms = [i for i in items if i["kind"] == "bottom"]
    layers = [i for i in items if i["kind"] == "outerwear"]
    combos = []
    for t in tops:
        for b in bottoms:
            base = t["price_cad"] + b["price_cad"]
            if base > BUDGET:
                continue
            combos.append((score(t) + score(b) + color_bonus([t, b])[0], [t, b]))
            for o in layers:
                if base + o["price_cad"] <= BUDGET:
                    combos.append((score(t) + score(b) + 0.5 * score(o) + color_bonus([t, b, o])[0], [t, b, o]))
    combos.sort(key=lambda c: -c[0])
    picks, seen = [], set()
    for sc, parts in combos:  # keep the best outfit for each different top, up to 10
        if parts[0]["url"] in seen:
            continue
        seen.add(parts[0]["url"])
        picks.append(parts)
        if len(picks) == 10:
            break
    out = {"date": str(date.today()), "budget_cad": BUDGET, "items": [], "alternatives": []}
    if picks:
        today = picks[date.today().toordinal() % len(picks)]
        total = round(sum(i["price_cad"] for i in today), 2)
        was = round(sum(i["was_cad"] for i in today), 2)
        out.update(items=[slim(i) for i in today], total_cad=total, was_total_cad=was,
                   saved_cad=round(was - total, 2),
                   note="Colors: " + " + ".join(sorted(color_bonus(today)[1])) +
                        ". No shoes in the sale data yet, so wear your own.")
        out["alternatives"] = [[i["title"] for i in p] for p in picks if p is not today][:3]
        print(f"Today's outfit: {', '.join(i['title'] for i in today)} = CAD {total}")
    else:
        out["message"] = "No outfit fits the budget today."
        print("No outfit fits the budget today.")
    print(f"{len(combos)} possible outfits, {len(picks)} shortlisted")
    with open("data/outfit.json", "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
