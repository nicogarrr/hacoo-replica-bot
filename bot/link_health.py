"""Bounded live route checks, not product/stock verification."""
import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
import requests
from url_policy import safe_product_url, is_hacoo_url
from product_state import classify_product_html

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
        self.product_cache = {}

    def probe_product(self, session, product_id, deadline=None):
        if not re.fullmatch(r'[0-9]{1,15}', str(product_id)):
            return 'unknown', 'ID no verificable'
        now = time.monotonic()
        with self.lock:
            cached = self.product_cache.get(product_id)
            if cached and now-cached[0] < self.ttl:
                return cached[1]
        # Official route observed in shop search SSR. Not an output/affiliate URL.
        url = f'https://shop.hacoo.pl/es-ES/detail/{product_id}'
        state = ('unknown', 'no pude comprobar la ficha de producto')
        for _ in range(self.max_hops):
            remaining = self.timeout if deadline is None else deadline-time.monotonic()
            if remaining <= 0 or not safe_product_url(url):
                break
            try:
                response = session.get(url, allow_redirects=False,
                    timeout=min(self.timeout,remaining), stream=True)
                try:
                    status, location = response.status_code, response.headers.get('Location')
                    if status in {301,302,303,307,308} and location:
                        url = urljoin(url,location)
                        continue
                    if status != 200:
                        break # HTTP/transport failure is not global deletion proof
                    body = bytearray()
                    for chunk in response.iter_content(chunk_size=16384):
                        if deadline is not None and time.monotonic() >= deadline:
                            return 'unknown','presupuesto de comprobación agotado'
                        body.extend(chunk)
                        if len(body) > 2_000_000:
                            return 'unknown','respuesta demasiado grande'
                    state = classify_product_html(body.decode('utf-8',errors='replace'), product_id)
                    break
                finally:
                    response.close()
            except requests.RequestException:
                break
        with self.lock:
            if len(self.product_cache) >= self.max_entries:
                self.product_cache.pop(next(iter(self.product_cache)))
            self.product_cache[product_id] = (time.monotonic(),state)
        return state

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
                match = re.fullmatch(r'/(?:[a-z]{2}-[A-Z]{2}/)?(?:detail|product|p)/([0-9]+)/?', urlsplit(current).path)
                if not match:
                    result = Health('unknown',url,'ruta sin ID de producto verificable'); break
                state, reason = self.probe_product(session,match.group(1),deadline)
                result = Health('reachable' if state == 'present' else state,current,reason)
                break
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
        if health.status in {'unknown','unavailable'}:
            unknown = unknown or (candidate,health)
            continue
        expected = str(row.get('product_id') or '')
        resolved_match = re.fullmatch(r'/(?:[a-z]{2}-[A-Z]{2}/)?(?:detail|product|p)/([0-9]+)/?', urlsplit(health.url).path)
        if expected and (not resolved_match or resolved_match.group(1) != expected):
            unknown = unknown or (candidate,Health('unknown',url,'destino distinto del producto pedido'))
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
                destination_match = re.fullmatch(
                    r'/(?:[a-z]{2}-[A-Z]{2}/)?(?:detail|product|p)/([0-9]+)/?',
                    urlsplit(destination.url).path)
                if (destination.status == 'reachable' and destination_match
                        and (not expected or destination_match.group(1) == expected)):
                    target = target # retain verified mapping and attribution parameters
                else:
                    target = health.url
        chosen['link'] = target
        chosen['health'] = 'Ficha presente en la web ES al comprobar; no verifica stock/talla.'
        return chosen
    # Unknowns are explicitly named, not clickable dead ends.
    if unknown or exhausted:
        chosen = dict(row)
        chosen['link'] = ''
        chosen['health'] = ('No disponible en la web ES. Enlace omitido; no demuestra borrado global.'
                            if unknown and unknown[1].status == 'unavailable'
                            else 'Puede estar caído: no pude confirmar que el producto exista en la web ES. Enlace omitido.')
        return chosen
    return None
