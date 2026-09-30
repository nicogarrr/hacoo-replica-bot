"""Offline cn-links-style identity parsing, not Hacoo/affiliate conversion.

Own Python implementation. Reference concept: https://github.com/cachho/cn-links
No HTTP requests, marketplace ID namespace never enters Hacoo product_id.
Unknown formats fail closed. Canonical URLs are NOT affiliate URLs.
"""
import re
from urllib.parse import urlsplit, parse_qs, unquote

ROOTS = {'taobao.com': 'taobao', 'tmall.com': 'tmall',
         'weidian.com': 'weidian', '1688.com': '1688'}
AGENTS = {'cssbuy.com', 'cnfans.com'}
PLATFORMS = {'taobao': 'taobao', 'weidian': 'weidian', '1688': '1688',
             'ali_1688': '1688'}

def normalize_marketplace_link(url, _depth=0):
    """Return {marketplace, product_id, canonical_url} or None. Bounded unwrap."""
    if not isinstance(url, str) or len(url) > 4096 or _depth > 2:
        return None
    try:
        p = urlsplit(url.strip())
        host = (p.hostname or '').lower()
        if p.scheme not in {'https', 'http'} or p.username or p.password or p.port:
            return None
        q = {k.lower(): v for k, v in parse_qs(p.query).items()}
        def one(key):
            vals = q.get(key, [])
            return vals[0] if len(vals) == 1 else ''
        platform = next((v for root, v in ROOTS.items()
                         if host == root or host.endswith('.' + root)), '')
        pid = ''
        if platform in {'taobao', 'tmall', 'weidian'}:
            pid = one('id' if platform in {'taobao', 'tmall'} else 'itemid')
        elif platform == '1688':
            m = re.fullmatch(r'/offer/(\d+)\.html', p.path)
            pid = m.group(1) if m else ''
        elif host in AGENTS or host in {'www.' + x for x in AGENTS}:
            nested = one('url')
            if nested:
                return normalize_marketplace_link(unquote(nested), _depth + 1)
            if host.endswith('cssbuy.com'):
                m = re.fullmatch(r'/item-(?:(taobao|weidian|1688)-)?(\d+)\.html', p.path)
                if m:
                    platform, pid = m.group(1) or 'taobao', m.group(2)
            elif p.path.rstrip('/') == '/product':
                selector = one('platform') or one('shop_type')
                platform = PLATFORMS.get(selector.lower(), '')
                pid = one('id')
        if not platform or not re.fullmatch(r'[0-9]+', pid):
            return None
        canonical = {'tmall': f'https://detail.tmall.com/item.htm?id={pid}',
                     'taobao': f'https://item.taobao.com/item.htm?id={pid}',
                     'weidian': f'https://weidian.com/item.html?itemID={pid}',
                     '1688': f'https://detail.1688.com/offer/{pid}.html'}[platform]
        return {'marketplace': platform, 'product_id': pid, 'canonical_url': canonical}
    except (ValueError, TypeError):
        return None
