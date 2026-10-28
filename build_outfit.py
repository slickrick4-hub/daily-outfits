"""Picks today's outfit from data/filtered.json: one top + one bottom (+ optional layer) within budget."""
import json, re
from datetime import date

STYLE = json.load(open("config.json"))
BUDGET = STYLE["outfit_budget_cad"]
# only real dress-shoe styles are allowed (no slippers, sandals, etc.)
SHOE_KEEP = STYLE.get("shoe_keep_words", ["loafer", "derby", "derbies", "oxfords", "brogue", "monk",
                                          "wingtip", "driver", "moc"])
REPEAT_PENALTY = 8   # clothes worn in the last few days score much lower (shoes are allowed to repeat)
RECENT = set()


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
