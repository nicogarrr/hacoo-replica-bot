"""Resuelve shortlinks de afiliado a URLs canonicas de producto Hacoo."""
import logging
import re
import time
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

DETAIL_RE = re.compile(r"/(?:detail|product)/(\d+)")
HACOO_HOST_RE = re.compile(r"(^|\.)hacoo\.[a-z]{2,3}(\.[a-z]{2})?$", re.I)


def extract_product_id(url: str) -> str:
    m = DETAIL_RE.search(url or "")
    return m.group(1) if m else ""


def is_hacoo_url(url: str) -> bool:
    try:
        return bool(HACOO_HOST_RE.search(urlparse(url).netloc))
    except Exception:
        return False


def resolve_one(session: requests.Session, url: str, max_hops: int = 4):
    """Sigue redirecciones a mano hasta Hacoo o agotar hops.

    Devuelve (url_final, product_id) o (None, None) si falla.
    """
    current = url
    for _ in range(max_hops):
        if is_hacoo_url(current) and extract_product_id(current):
            return current, extract_product_id(current)
        try:
            # GET con stream: algunos acortadores devuelven 404 a HEAD.
            r = session.get(current, allow_redirects=False, timeout=15, stream=True)
            r.close()
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
                current = r.headers["Location"]
                continue
            if r.status_code == 200:
                if is_hacoo_url(current):
                    return current, extract_product_id(current)
                return current, extract_product_id(current)
            return None, None
        except Exception as e:
            log.debug("resolver %s: %s", current, e)
            return None, None
    if is_hacoo_url(current):
        return current, extract_product_id(current)
    return None, None


def resolve_pending(session: requests.Session, db, rate_per_min: int = 30,
                    max_seconds: float = 0) -> int:
    """Resuelve a ritmo fijo hasta agotar la cola o el tiempo.

    max_seconds=0 -> sin tope de tiempo (solo la cola).
    """
    started = time.time()
    done = 0
    delay = 60.0 / max(1, rate_per_min)
    while True:
        rows = db.unresolved_links(25)
        if not rows:
            break
        for row in rows:
            final_url, pid = resolve_one(session, row["url"])
            if final_url:
                db.mark_resolved(row["id"], final_url, pid or None)
            else:
                db.mark_failed(row["id"])
            done += 1
            time.sleep(delay)
            if max_seconds and time.time() - started > max_seconds:
                db.commit()
                return done
        db.commit()
    return done
