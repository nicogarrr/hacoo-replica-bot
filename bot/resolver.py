"""Resuelve shortlinks de afiliado a URLs canonicas de producto Hacoo."""
import logging
import re
import time
from urllib.parse import urlparse, urljoin
from url_policy import safe_product_url, is_hacoo_url
from marketplace_links import normalize_marketplace_link
from product_identity import hacoo_product_id

import requests

log = logging.getLogger(__name__)

def extract_product_id(url: str) -> str:
    return hacoo_product_id(url)


class RetryableResolution(Exception):
    """Transient network/server failure, not a confirmed dead product."""


def _resolve_one(session, url, max_hops=4):
    current = url
    for _ in range(max_hops):
        if not safe_product_url(current):
            return None, None
        if is_hacoo_url(current) and extract_product_id(current):
            return current, extract_product_id(current)
        try:
            r = session.get(current, allow_redirects=False, timeout=15, stream=True)
            try:
                status, location = r.status_code, r.headers.get("Location")
            finally:
                r.close()
        except requests.RequestException as exc:
            raise RetryableResolution() from exc
        if status == 429 or status == 408 or status >= 500:
            raise RetryableResolution()
        if status in (301, 302, 303, 307, 308) and location:
            current = urljoin(current, location)
            continue
        if status == 200:
            return current, extract_product_id(current) if is_hacoo_url(current) else ""
        return None, None
    if is_hacoo_url(current):
        return current, extract_product_id(current)
    return None, None


def resolve_one(session, url, max_hops=4):
    """Public compatibility wrapper; pending worker handles transient backoff."""
    try:
        return _resolve_one(session, url, max_hops)
    except RetryableResolution:
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
        rows = db.unresolved_links(25, started)
        if not rows:
            break
        for row in rows:
            try:
                final_url, pid = _resolve_one(session, row["url"])
            except RetryableResolution:
                db.mark_retry(row["id"])
            else:
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


def resolve_identity(session, url):
    """Typed resolver entry point; marketplace identities require no network.

    Never write marketplace IDs to the Hacoo product_id column or return them
    from the Hacoo search UI. No affiliate conversion is inferred.
    """
    market = normalize_marketplace_link(url)
    if market:
        return dict(market, kind="marketplace")
    final, pid = resolve_one(session, url)
    if final:
        return {"kind": "hacoo", "canonical_url": final, "product_id": pid or ""}
    return None
