"""Bounded live route checks, not product/stock verification."""
import threading
import time
from dataclasses import dataclass
from urllib.parse import urljoin
import requests
from url_policy import safe_product_url, is_hacoo_url

@dataclass(frozen=True)
class Health:
    status: str # reachable route / dead / unknown
    url: str
    reason: str

class LinkHealth:
    def __init__(self, ttl=120, timeout=3, max_hops=4, max_entries=1000):
        self.ttl, self.timeout, self.max_hops = ttl, timeout, max_hops
        self.max_entries = max_entries
        self.cache = {}
        self.lock = threading.Lock()

    def check(self, session, url, deadline=None):
        if not safe_product_url(url):
            return Health('dead', '', 'enlace no seguro')
        now = time.monotonic()
        with self.lock:
            cached = self.cache.get(url)
            if cached and now-cached[0] < self.ttl:
                return cached[1]
        current = url
        result = Health('unknown', url, 'demasiadas redirecciones')
        for _ in range(self.max_hops):
            remaining = self.timeout if deadline is None else deadline-time.monotonic()
            if remaining <= 0:
                return Health('unknown', url, 'presupuesto de comprobación agotado')
            if not safe_product_url(current):
                result = Health('dead', '', 'destino no seguro'); break
            try:
                r = session.get(current, allow_redirects=False, timeout=min(self.timeout,remaining), stream=True)
                try: status, location = r.status_code, r.headers.get('Location')
                finally: r.close()
            except requests.RequestException:
                result = Health('unknown', url, 'no pude comprobarlo'); break
            if status in {404,410}:
                result = Health('dead', '', '404/410 confirmado'); break
            if status in {301,302,303,307,308} and location:
                current = urljoin(current, location); continue
            if status == 200 and is_hacoo_url(current):
                # SPA 200 proves only reachable route, never product existence.
                result = Health('reachable', current, 'ruta responde; producto no verificado'); break
            result = Health('unknown', url, 'destino de producto no confirmado'); break
        with self.lock:
            if len(self.cache) >= self.max_entries:
                self.cache.pop(next(iter(self.cache)))
            self.cache[url] = (time.monotonic(),result)
        return result

def choose_link(session, db, row, checker, output_url=None, budget=None, deadline=None):
    """Try original first, then at most two indexed alternatives for same ID.

    No synthetic recovery from an ID. Optional approved mapping is checked too.
    budget is a shared mutable check counter for the whole query.
    """
    budget = [3] if budget is None else budget
    candidates = [row]
    if row.get('product_id'):
        candidates += [dict(r) for r in db.search_product_id(row['product_id'], 3)
                       if r['id'] != row['id']][:2]
    unknown = None
    seen = set()
    exhausted = False
    for candidate in candidates:
        url = candidate['orig_url']
        if budget[0] <= 0:
            exhausted = True
            continue
        if url in seen:
            continue
        seen.add(url); budget[0] -= 1
        health = checker.check(session,url,deadline)
        if health.status == 'dead':
            db.mark_checked(candidate['id'],True)
            continue
        if health.status == 'unknown':
            unknown = unknown or (candidate,health)
            continue
        db.mark_checked(candidate['id'],False)
        chosen = dict(row)
        for field in ('id','orig_url','channel','message_id','posted_at','checked_at'):
            if field in candidate: chosen[field] = candidate[field]
        target = output_url if candidate['id'] == row['id'] and output_url else candidate['link']
        # Never emit an unchecked mapped/stored destination after original passes.
        if target not in {url,health.url}:
            if budget[0] <= 0:
                target = health.url
            else:
                budget[0] -= 1
                destination = checker.check(session,target,deadline)
                if destination.status == 'reachable':
                    target = target # retain verified mapping and attribution parameters
                else:
                    target = health.url
        chosen['link'] = target
        chosen['health'] = 'ruta responde; no verifica producto/stock'
        return chosen
    # Unknowns are explicitly named, not clickable dead ends.
    if unknown or exhausted:
        chosen = dict(row)
        chosen['link'] = ''
        chosen['health'] = 'Puede estar caído: no pude confirmar el destino. No doy enlace sin comprobar.'
        return chosen
    return None
