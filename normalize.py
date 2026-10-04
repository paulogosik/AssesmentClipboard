import re
from difflib import SequenceMatcher

STREET_TOKENS = {
    "street": "st", "avenue": "ave", "av": "ave", "road": "rd", "drive": "dr", "boulevard": "blvd",
    "lane": "ln", "pk": "pike", "pke": "pike", "parkway": "pkwy", "court": "ct", "place": "pl",
    "highway": "hwy", "square": "sq", "circle": "cir", "terrace": "ter", "way": "way",
    "north": "n", "south": "s", "east": "e", "west": "w",
    "northwest": "nw", "northeast": "ne", "southwest": "sw", "southeast": "se",
}

CARE_TYPE_MAP = {
    "short-term rehabilitation & nursing": "Skilled Nursing",
    "skilled nursing": "Skilled Nursing",
    "assisted living": "Assisted Living",
    "memory support": "Memory Care",
    "memory care": "Memory Care",
    "independent living": "Independent Living",
}


def _tokens(text):
    return re.sub(r"[^a-z0-9& ]", " ", (text or "").lower().replace("&", " & ")).split()


def street_key(street):
    return " ".join(STREET_TOKENS.get(token, token) for token in _tokens(street))


def is_po_box(street):
    return bool(re.match(r"^\s*p\.?\s*o\.?\s*box", (street or "").lower()))


def address_key(street, city, state):
    return f"{street_key(street)}|{' '.join(_tokens(city))}|{(state or '').upper()}"


def name_key(name):
    return " ".join("and" if token == "&" else token for token in _tokens(name))


def name_similarity(a, b):
    return round(SequenceMatcher(None, name_key(a), name_key(b)).ratio(), 2)


def crm_care_types(offerings):
    mapped = [CARE_TYPE_MAP.get(o.strip().lower()) for o in offerings]
    return [m for m in mapped if m]
