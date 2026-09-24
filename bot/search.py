"""Busqueda: FTS5 con relajacion progresiva, guarda de categoria y honestidad.

Reglas:
- La frase (sobre todo si viene de vision) lleva marca + modelo + tipo + colorway.
- Se prueba con los k primeros tokens, bajando de k en k hasta 2; ultimo
  recurso: OR de todos los tokens con bm25.
- Guarda de categoria: si la consulta es de calzado (sneaker/zapatilla/...),
  un resultado cuyo titulo es claramente ropa o accesorio NO entra nunca.
- Si el modelo exacto no aparece en ningun titulo, se informa con
  exact=False para que el bot diga "no esta, lo mas parecido" en vez de
  soltar basura generica de la marca.
"""
import re
import unicodedata

MIN_TOKENS = 2

FOOTWEAR = {
    "sneaker", "sneakers", "zapatilla", "zapatillas", "zapas", "deportiva",
    "deportivas", "shoe", "shoes", "trainer", "trainers", "tenis", "bamba",
    "bambas", "boot", "boots", "bota", "botas", "sandalia", "sandalias",
    "slide", "slides", "chancla", "chanclas", "runner", "running", "court",
    "dunk", "jordan", "yeezy", "samba", "gazelle", "campus", "forum",
    "superstar", "blazer", "vomero", "pegasus", "ultraboost", "spezial",
}
APPAREL = {
    "camiseta", "camisetas", "shirt", "tshirt", "tee", "hoodie", "sudadera",
    "sudaderas", "pantalon", "pantalones", "jeans", "vaqueros", "chaqueta",
    "jacket", "jersey", "sweater", "sweatshirt", "crewneck", "cardigan",
    "vestido", "dress", "falda", "skirt", "gorra", "hat", "cap", "beanie",
    "camisa", "blouse", "top", "chandal", "tracksuit", "calcetines",
    "calcetin", "socks", "bufanda", "scarf", "shorts", "short", "bermuda",
    "bermudas", "abrigo", "coat", "puffer", "chaleco", "vest", "gilet",
    "leggings", "poloshirt", "polo衫",
}
ACCESSORY = {
    "bolso", "bolsa", "bag", "mochila", "backpack", "cartera", "wallet",
    "cinturon", "belt", "gafas", "sunglasses", "reloj", "watch", "collar",
    "necklace", "pulsera", "bracelet", "pendientes", "earrings", "anillo",
    "ring", "tote", "handbag", "crossbody", "clutch",
}

BRANDS = [
    "polo ralph lauren", "ralph lauren", "the north face", "north face",
    "stone island", "cp company", "chrome hearts", "new balance",
    "a bathing ape", "fear of god", "off white", "palm angels",
    "broken planet", "denim tears", "cole buxton", "tommy hilfiger",
    "louis vuitton", "dr martens", "on running", "nike", "jordan",
    "adidas", "asics", "moncler", "corteiz", "trapstar", "zara", "goyard",
    "bape", "essentials", "ami", "amiri", "puma", "vans", "converse",
    "reebok", "lacoste", "carhartt", "stussy", "supreme", "balenciaga",
    "gucci", "dior", "prada", "burberry", "versace", "fendi", "loewe",
    "represent", "hellstar", "sp5der", "yeezy", "salomon", "hoka",
    "mizuno", "timberland", "ugg", "ecoalf", "lv",
]

COLORS = {
    "white", "black", "gum", "blanco", "blanca", "negro", "negra", "rojo",
    "roja", "azul", "verde", "gris", "grey", "gray", "pink", "rosa",
    "brown", "marron", "beige", "crema", "cream", "navy", "red", "blue",
    "green", "yellow", "amarillo", "orange", "naranja", "purple", "violeta",
    "morado", "khaki", "caqui", "multicolor",
}
GENERIC = COLORS | FOOTWEAR | APPAREL | ACCESSORY | {
    "men", "mens", "women", "womens", "hombre", "mujer", "kids", "ninos",
    "ninas", "para", "de", "del", "con", "y", "the", "and", "in", "low",
    "high", "mid", "top", "og", "retro", "vintage", "new", "nuevo", "nueva",
    "para", "hombre", "mujer", "unisex",
}

_EMOJI_RE = re.compile(
    "[" "\U0001F000-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF" "\U00002B00-\U00002BFF" "\U0000FE00-\U0000FE0F"
    "\U0000200D" "]+")
_LINKJUNK_RE = re.compile(r"(?i)\b(?:links?|enlaces?)\b:?")


def normalize(query: str) -> str:
    q = unicodedata.normalize("NFKD", query)
    q = "".join(c for c in q if not unicodedata.combining(c))
    return " ".join(q.split())


def clean_title(title: str) -> str:
    """Titulo legible: sin emojis ni la morralla 'Link: Link:' de canal."""
    t = _EMOJI_RE.sub(" ", title or "")
    t = _LINKJUNK_RE.sub(" ", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"\s*[-–|]\s*$", "", t.strip())
    t = re.sub(r"\s{2,}", " ", t).strip(" -–|")
    return t or "(sin titulo)"


def _tokens(text: str) -> list:
    return [t for t in re.split(r"[^\w]+", normalize(text).lower()) if t]


def categorize(text: str) -> str:
    toks = set(_tokens(text))
    if toks & FOOTWEAR:
        return "footwear"
    if toks & APPAREL:
        return "apparel"
    if toks & ACCESSORY:
        return "accessory"
    return ""


def _split_query(tokens: list) -> tuple:
    """Devuelve (marca, terminos de modelo) sobre la consulta normalizada."""
    low = [t.lower() for t in tokens]
    brand = []
    for b in BRANDS:  # la lista va de frase larga a corta
        bt = b.split()
        if low[:len(bt)] == bt:
            brand = tokens[:len(bt)]
            break
    rest = tokens[len(brand):]
    model = [t for t in rest if t.lower() not in GENERIC]
    return brand, model


def _add(rows, results, seen, counted_rows, limit, category):
    for r in rows:
        if r["id"] in counted_rows:
            continue
        counted_rows.add(r["id"])
        if category:
            rcat = categorize(r["title"] or "")
            if rcat and rcat != category:
                continue  # guarda de categoria: calzado nunca trae ropa
        key = r["product_id"] or r["link"]
        if key in seen:
            seen[key]["sources"] += 1
            continue
        entry = {
            "title": clean_title(r["title"]),
            "link": r["link"],
            "channel": r["channel"],
            "posted_at": (r["posted_at"] or "")[:10],
            "sources": 1,
        }
        seen[key] = entry
        results.append(entry)
        if len(results) >= limit:
            return True
    return False


def search(db, query: str, limit: int = 5) -> dict:
    """Devuelve {results, exact, model, category}.

    exact=False significa: el modelo pedido no aparece en ningun titulo;
    los resultados son solo lo mas parecido de la marca.
    """
    q = normalize(query)
    tokens = [t for t in q.split() if len(t) >= 2]
    if not tokens:
        return {"results": [], "exact": False, "model": "", "category": ""}
    category = categorize(q)
    brand, model_terms = _split_query(tokens)
    model_label = " ".join(model_terms)
    results = []
    seen = {}
    counted_rows = set()
    floor = MIN_TOKENS if len(tokens) >= MIN_TOKENS else len(tokens)
    for k in range(len(tokens), floor - 1, -1):
        sub = " ".join(tokens[:k])
        rows = db.search_fts(sub, limit) or db.search_like(sub, limit)
        if category:
            # titulos de la misma categoria (zapatillas) antes que morralla
            # sin tipo ("Polo Ralph Lauren 👶👶"); bm25 manda dentro del grupo
            rows = sorted(
                rows,
                key=lambda r: 0 if categorize(r["title"] or "") == category else 1)
        if _add(rows, results, seen, counted_rows, limit, category):
            break
    if len(results) < limit and len(tokens) > 1:
        rows = db.search_fts(" ".join(tokens), limit, mode="or") \
            or db.search_like(" ".join(tokens), limit, mode="or")
        # titulos con tipo de producto claro primero: menos morralla
        rows = sorted(rows, key=lambda r: 0 if categorize(r["title"] or "") else 1)
        _add(rows, results, seen, counted_rows, limit, category)
    exact = True
    if model_terms:
        ml = [m.lower() for m in model_terms]
        exact = any(
            all(m in (r["title"] or "").lower() for m in ml) for r in results)
        if not results:
            exact = False
    return {
        "results": results[:limit],
        "exact": exact,
        "model": model_label,
        "category": category,
    }
