"""Observed community offers, separate from Hacoo search and affiliate output.

No price/catalog verification. No posting side effects. IDs are namespaced.
"""
import html
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from marketplace_links import normalize_marketplace_link
from url_policy import safe_product_url, is_hacoo_url
from product_identity import hacoo_product_id

SCHEMA = """
CREATE TABLE IF NOT EXISTS community_offers (
 namespace TEXT NOT NULL, identity TEXT NOT NULL, channel TEXT NOT NULL,
 message_id INTEGER NOT NULL, title TEXT NOT NULL, original_url TEXT NOT NULL,
 posted_ts REAL NOT NULL, price_cents INTEGER, previous_cents INTEGER,
 PRIMARY KEY(namespace,identity,channel,message_id)
);
CREATE INDEX IF NOT EXISTS community_offers_recent ON community_offers(posted_ts);
"""
# Require explicit before/now, EUR markers on BOTH values, sensible reductions.
_PRICE = re.compile(r'(?i)\b(?:antes|before)\s*[:=]?\s*(\d{1,6}(?:[.,]\d{1,2})?)\s*(?:€|EUR)\s*[,;|/\-]?\s*(?:ahora|now)\s*[:=]?\s*(\d{1,6}(?:[.,]\d{1,2})?)\s*(?:€|EUR)(?!\w)')

def init_trends(db):
    db.conn.executescript(SCHEMA)

def _timestamp(value):
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if not d.tzinfo:
            return None # source date without timezone cannot drive freshness
        return d.timestamp()
    except (ValueError, TypeError, AttributeError):
        return None

def _prices(text):
    matches = list(_PRICE.finditer(text or ''))
    if len(matches) != 1:
        return None, None
    before, now = [int(round(float(v.replace(',', '.')) * 100))
                   for v in matches[0].groups()]
    if not (0 < now < before and (before - now) / before <= .95):
        return None, None
    return now, before

def offer_identity(url):
    market = normalize_marketplace_link(url)
    if market:
        return market['marketplace'], market['product_id']
    if safe_product_url(url):
        p = urlsplit(url)
        pid = hacoo_product_id(url)
        if pid:
            return 'hacoo', pid
        # Unknown shortlinks remain separate; never strip tracking signatures.
        return 'hacoo', 'url:' + urlunsplit((p.scheme, p.netloc.lower(), p.path, p.query, ''))
    return None

def index_offer(db, message, url, now=None):
    identity = offer_identity(url)
    ts = _timestamp(message.posted_at)
    now = time.time() if now is None else now
    if not identity or ts is None or ts > now + 300:
        return False
    # Multi-product posts cannot bind a price pair reliably to one product.
    identities = {offer_identity(u) for u in message.links}
    identities.discard(None)
    price, before = _prices(message.raw_text) if len(identities) == 1 else (None, None)
    db.conn.execute("""INSERT INTO community_offers
       (namespace,identity,channel,message_id,title,original_url,posted_ts,
        price_cents,previous_cents) VALUES(?,?,?,?,?,?,?,?,?)
       ON CONFLICT(namespace,identity,channel,message_id) DO UPDATE SET
       title=excluded.title,original_url=excluded.original_url,
       posted_ts=excluded.posted_ts,price_cents=excluded.price_cents,
       previous_cents=excluded.previous_cents""",
       (*identity,message.channel,message.message_id,message.title,url,ts,price,before))
    return True

def trends(db, namespace='hacoo', days=7, limit=10, now=None):
    """Recent observed products, not engagement/stock/popularity claims."""
    now = time.time() if now is None else now
    days, limit = max(1,min(30,days)), max(1,min(20,limit))
    rows = db.conn.execute("""SELECT * FROM community_offers
       WHERE namespace=? AND posted_ts BETWEEN ? AND ?
       ORDER BY posted_ts DESC,message_id DESC""",
       (namespace, now-days*86400, now)).fetchall()
    related = db.conn.execute("""SELECT l.channel,l.message_id,l.url,
          l.product_id,l.resolved_url,l.dead_at FROM links l
          JOIN community_offers o ON o.channel=l.channel
            AND o.message_id=l.message_id AND o.original_url=l.url
          WHERE o.namespace=? AND o.posted_ts BETWEEN ? AND ?""",
          (namespace,now-days*86400,now)).fetchall()
    resolved = {(r["channel"],r["message_id"],r["url"]): r["product_id"]
        for r in related if r["product_id"] and is_hacoo_url(r["resolved_url"])
        and r["dead_at"] is None}
    dead = {(r["channel"],r["message_id"],r["url"]) for r in related
            if r["dead_at"] is not None}
    grouped = {}
    for row in rows:
        row = dict(row)
        key = (row["channel"],row["message_id"],row["original_url"])
        if key in dead:
            continue
        # Revalidate legacy rows at read boundary.
        if offer_identity(row['original_url']) != (row['namespace'],row['identity']):
            continue
        if row["namespace"] == "hacoo" and key in resolved:
            row["identity"] = resolved[key]
        if row['identity'] not in grouped:
            grouped[row['identity']] = dict(row, source_channels=set(), posts=0)
        r = grouped[row['identity']]
        r['source_channels'].add(row['channel']); r['posts'] += 1
    result = []
    for r in grouped.values():
        age_days = max(0, (now-r['posted_ts'])/86400)
        r['sources'] = len(r.pop('source_channels'))
        r['discount_pct'] = (round(100*(r['previous_cents']-r['price_cents'])/
                                   r['previous_cents'],1)
                             if r['price_cents'] and r['previous_cents'] else None)
        # Recency dominates, bounded source repetition and claimed reduction.
        r['rank'] = 100/(1+age_days) + min(r['sources']-1,4)*3 + min(r['discount_pct'] or 0,50)/5
        result.append(r)
    return sorted(result,key=lambda r:(r['rank'],r['posted_ts'],r['identity']),reverse=True)[:limit]

def format_offer(row):
    """HTML draft suitable for review. Never sends or invents an affiliate URL."""
    title = html.escape(row['title'][:200])
    day = datetime.fromtimestamp(row['posted_ts'], timezone.utc).strftime('%Y-%m-%d')
    label = 'Hacoo' if row['namespace'] == 'hacoo' else row['namespace'].title()
    lines = [f'<b>{title}</b>', f'{label} · publicado {day} · {row["sources"]} fuentes distintas']
    if row['price_cents'] and row['previous_cents']:
        lines.append(f'El post anuncia {row["price_cents"]/100:.2f} EUR (antes {row["previous_cents"]/100:.2f} EUR, -{row["discount_pct"]:g}%).')
    else:
        lines.append('Precio/descuento no verificados.')
    if row['original_url']:
        lines.append(f'<a href="{html.escape(row["original_url"],quote=True)}">Ver enlace ({label})</a>')
    else:
        lines.append('Enlace omitido: puede estar caído.')
    if row.get('health'):
        lines.append(html.escape(row['health']))
    channel = row['channel']
    if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', channel) and row['message_id'] > 0:
        lines.append(f'<a href="https://t.me/{channel}/{row["message_id"]}">Fuente: @{html.escape(channel)}</a>')
    lines.append('Enlace de la fuente, no afiliación propia verificada. No comprueba stock, talla ni precio actual.')
    return '\n'.join(lines)
