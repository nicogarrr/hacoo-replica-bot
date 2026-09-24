"""Busqueda: FTS5 con fallback LIKE, agrupando por producto."""
import unicodedata


def normalize(query: str) -> str:
    q = unicodedata.normalize("NFKD", query)
    q = "".join(c for c in q if not unicodedata.combining(c))
    return " ".join(q.split())


def search(db, query: str, limit: int = 5) -> list:
    q = normalize(query)
    rows = db.search_fts(q, limit) or db.search_like(q, limit)
    seen_products = {}
    results = []
    for r in rows:
        key = r["product_id"] or r["link"]
        if key in seen_products:
            # mismo producto desde otro canal: lo contamos como fuente extra
            seen_products[key]["sources"] += 1
            continue
        entry = {
            "title": (r["title"] or "").strip() or "(sin titulo)",
            "link": r["link"],
            "channel": r["channel"],
            "posted_at": (r["posted_at"] or "")[:10],
            "sources": 1,
        }
        seen_products[key] = entry
        results.append(entry)
        if len(results) >= limit:
            break
    return results
