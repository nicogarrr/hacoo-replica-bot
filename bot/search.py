"""Busqueda: FTS5 con fallback LIKE y relajacion progresiva.

La frase (sobre todo si viene de vision) lleva marca + modelo + colorway.
Exigir TODOS los tokens deja fuera coincidencias buenas cuando el canal
titulo corto ("Ralph Lauren"). Estrategia: probar con los k primeros
tokens (la marca y el modelo van delante), bajando de k en k hasta 2,
y acumular sin duplicar por producto.
"""
import unicodedata

MIN_TOKENS = 2


def normalize(query: str) -> str:
    q = unicodedata.normalize("NFKD", query)
    q = "".join(c for c in q if not unicodedata.combining(c))
    return " ".join(q.split())


def _add(rows, results, seen, counted_rows, limit):
    for r in rows:
        if r["id"] in counted_rows:
            continue  # misma fila ya contada en un nivel menos relajado
        counted_rows.add(r["id"])
        key = r["product_id"] or r["link"]
        if key in seen:
            seen[key]["sources"] += 1
            continue
        entry = {
            "title": (r["title"] or "").strip() or "(sin titulo)",
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


def search(db, query: str, limit: int = 5) -> list:
    q = normalize(query)
    tokens = [t for t in q.split() if len(t) >= 2]
    if not tokens:
        return []
    results = []
    seen = {}
    counted_rows = set()
    floor = MIN_TOKENS if len(tokens) >= MIN_TOKENS else len(tokens)
    for k in range(len(tokens), floor - 1, -1):
        sub = " ".join(tokens[:k])
        rows = db.search_fts(sub, limit) or db.search_like(sub, limit)
        full = _add(rows, results, seen, counted_rows, limit)
        if full:
            return results
    # Ultimo recurso: OR de todos los tokens, bm25 arriba lo mas parecido.
    # Cubre marcas con prefijo ("Polo Ralph Lauren" -> "Ralph Lauren").
    if len(tokens) > 1 and len(results) < limit:
        rows = db.search_fts(" ".join(tokens), limit, mode="or") \
            or db.search_like(" ".join(tokens), limit, mode="or")
        _add(rows, results, seen, counted_rows, limit)
    return results
