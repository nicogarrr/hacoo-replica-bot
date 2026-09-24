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

_LEXICON = {"footwear": FOOTWEAR, "apparel": APPAREL, "accessory": ACCESSORY}

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


def _add(rows, results, seen, counted_rows, limit, category, lvl,
         typed_ids=frozenset()):
    for r in rows:
        if r["id"] in counted_rows:
            continue
        counted_rows.add(r["id"])
        if category:
            rcat = categorize(r["title"] or "")
            if rcat and rcat != category:
                continue  # guarda de categoria: calzado nunca trae ropa
        key = r["product_id"] or r["link"]
        posted = (r["posted_at"] or "")[:10]
        if key in seen:
            seen[key]["sources"] += 1
            # el enlace mas reciente del mismo producto es el que vale:
            # los enlaces de Hacoo mueren en ~1 mes
            if posted > seen[key]["posted_at"]:
                seen[key].update({
                    "id": r["id"], "link": r["link"],
                    "orig_url": r["orig_url"], "posted_at": posted,
                })
            continue
        entry = {
            "id": r["id"],
            "title": clean_title(r["title"]),
            "link": r["link"],
            "orig_url": r["orig_url"],
            "channel": r["channel"],
            "posted_at": posted,
            "sources": 1,
            "lvl": lvl,
            "typed": r["id"] in typed_ids,
        }
        seen[key] = entry
        results.append(entry)
        if len(results) >= limit:
            return True
    return False


def _days_ago(n: int) -> str:
    import time as _t
    return _t.strftime("%Y-%m-%d", _t.gmtime(_t.time() - n * 86400))


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
        # los canales abrevian la marca ("Ralph Lauren", no "Polo Ralph
        # Lauren"): si la marca tiene 3+ palabras, se prueba tambien sin
        # la primera para no tirar el modelo a la basura con ella
        subs = [" ".join(tokens[:k])]
        if brand and len(brand) >= 3 and k > 2:
            subs.append(" ".join(tokens[1:k]))
        rows = []
        for sub in subs:
            seen_sub = {r["id"] for r in rows}
            chunk = db.search_fts(sub, limit) or db.search_like(sub, limit)
            rows += [r for r in chunk if r["id"] not in seen_sub]
        if category and k <= max(len(brand), MIN_TOKENS):
            # consulta tipada SOLO en niveles marca-only: marca + lexico de
            # la categoria, para sacar "Zapatillas RL Heritage" aunque el
            # top bm25 sea morralla generica de la marca. En niveles
            # estrictos el AND manda y la tipada no entra (si no, una
            # busqueda de Heritage sacaria sandalias).
            base = brand if brand else tokens[:k]
            typed = db.search_fts_with_any(
                base, sorted(_LEXICON[category]), limit * 6)
            if len(base) >= 3:
                # siempre tambien sin la primera palabra: "Zapatillas
                # Ralph Lauren Heritage" no lleva "Polo" y si no se
                # escapa cuando la marca completa ya da resultados
                tids0 = {t["id"] for t in typed}
                typed += [t for t in db.search_fts_with_any(
                    base[1:], sorted(_LEXICON[category]), limit * 6)
                    if t["id"] not in tids0]
            tids = {t["id"] for t in typed}
            rows = list(typed) + [r for r in rows if r["id"] not in tids]
        else:
            typed = []
            tids = set()
        if _add(rows, results, seen, counted_rows, limit, category, k,
                typed_ids=tids):
            break
    if len(results) < limit and len(tokens) > 1:
        rows = db.search_fts(" ".join(tokens), limit, mode="or") \
            or db.search_like(" ".join(tokens), limit, mode="or")
        # titulos con tipo de producto claro primero: menos morralla
        rows = sorted(rows, key=lambda r: 0 if categorize(r["title"] or "") else 1)
        _add(rows, results, seen, counted_rows, limit, category, 1)
    # frescura: dentro de cada nivel, los enlaces mas nuevos primero;
    # y se ocultan los de >45 dias salvo que no quede nada mas
    by_lvl = sorted(results, key=lambda e: -e["lvl"])
    ordered = []
    for lvl in dict.fromkeys(e["lvl"] for e in by_lvl):
        group = [e for e in by_lvl if e["lvl"] == lvl]
        # tipadas (misma categoria) primero y, dentro, las mas nuevas
        group.sort(key=lambda e: e["posted_at"], reverse=True)
        group.sort(key=lambda e: not e.get("typed"))
        ordered.extend(group)
    cutoff_drop = _days_ago(45)
    fresh = [e for e in ordered if e["posted_at"] >= cutoff_drop]
    results = fresh if fresh else ordered
    cutoff_stale = _days_ago(25)
    for e in results:
        e["stale"] = e["posted_at"] < cutoff_stale

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
