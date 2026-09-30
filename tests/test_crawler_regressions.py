import sys
from pathlib import Path
import pytest
import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bot'))
from db import DB
from liveness import check_pending
from channels import crawl_channel
from resolver import resolve_pending, resolve_one, normalize_marketplace_link

class Resp:
    def __init__(self, status=200, location=None):
        self.status_code = status
        self.headers = {'Location': location} if location else {}
    def close(self): pass

class Session:
    def __init__(self, responses): self.responses = iter(responses); self.calls = []
    def get(self, url, **kw):
        self.calls.append(url)
        r = next(self.responses)
        if isinstance(r, Exception): raise r
        return r

def add(db, n):
    db.insert_message('c', n, '', 'Nike', '')
    db.insert_link('c', n, f'https://onlyaff.app/{n}')

def test_h4_finite_unlimited_pass_and_oldest_rotation(monkeypatch):
    monkeypatch.setattr('liveness.time.sleep', lambda _: None)
    db = DB(':memory:')
    for n in range(1, 31): add(db, n)
    s = Session([Resp() for _ in range(30)])
    assert check_pending(s, db, max_seconds=0) == (30, 0)
    assert len(set(s.calls)) == 30
    db.conn.execute('UPDATE links SET checked_at = id')
    assert [r['id'] for r in db.links_to_check(2, 99)] == [1, 2]
    assert db.links_to_check(2, 0) == []

def page(ids, products=()):
    return ''.join(f'<div class="tgme_widget_message" data-post="c/{n}">'
        '<div class="tgme_widget_message_text">Nike ' +
        (f'<a href="https://onlyaff.app/{n}">link</a>' if n in products else '') +
        '</div></div>' for n in ids)

def test_h10_sparse_empty_link_pages_and_no_progress(monkeypatch):
    db = DB(':memory:')
    pages = iter([page(range(41, 61), [60]), page(range(21, 41)),
                  page(range(1, 21), [5]), page(range(1, 21), [5])])
    calls = []
    def fetch(s, c, before): calls.append(before); return next(pages)
    monkeypatch.setattr('channels.fetch_page', fetch)
    assert crawl_channel(None, 'c', db, sleep_s=0) == 2
    assert calls == [0, 41, 21, 1]
    assert db.stats()['links'] == 2

def test_h6_crawler_ingestion_guard(monkeypatch):
    db = DB(':memory:')
    html = page([1], [1]).replace('</div></div>', '<a href="https://evil.test/a">x</a></div></div>')
    monkeypatch.setattr('channels.fetch_page', lambda *a: html)
    assert crawl_channel(None, 'c', db, max_pages=1, sleep_s=0) == 1
    assert db.stats()['links'] == 1

def test_h13_relative_and_cross_domain_redirects():
    s = Session([Resp(302, '/detail/123')])
    assert resolve_one(s, 'https://hacoo.app/start') == ('https://hacoo.app/detail/123', '123')
    assert s.calls == ['https://hacoo.app/start']
    s = Session([Resp(302, 'https://evil.test/detail/123')])
    assert resolve_one(s, 'https://onlyaff.app/a') == (None, None)
    assert len(s.calls) == 1

@pytest.mark.parametrize('failure', [requests.Timeout(), Resp(429), Resp(503), Resp(408)])
def test_h13_transient_retry_persisted_finite_pass(tmp_path, monkeypatch, failure):
    monkeypatch.setattr('resolver.time.sleep', lambda _: None)
    path = str(tmp_path / 'db.sqlite')
    db = DB(path)
    add(db, 1)
    s = Session([failure])
    assert resolve_pending(s, db) == 1
    assert len(s.calls) == 1
    row = db.conn.execute('SELECT * FROM links').fetchone()
    assert row['resolved_at'] is None and row['resolve_attempts'] == 1
    assert row['resolve_retry_at'] > 0
    assert db.unresolved_links(25) == []
    db.close()
    db = DB(path)
    assert db.unresolved_links(25) == []
    db.conn.execute('UPDATE links SET resolve_retry_at=0')
    s = Session([Resp(302, 'https://hacoo.app/detail/321')])
    assert resolve_pending(s, db) == 1
    assert db.stats()['resolved'] == 1
    assert db.unresolved_links(25) == []

def test_h13_permanent_404_not_retry(monkeypatch):
    monkeypatch.setattr('resolver.time.sleep', lambda _: None)
    db = DB(':memory:'); add(db, 1)
    assert resolve_pending(Session([Resp(404)]), db) == 1
    row = db.conn.execute('SELECT * FROM links').fetchone()
    assert row['resolved_at'] is not None and row['resolve_attempts'] == 0
    assert db.stats()['resolved'] == 0

@pytest.mark.parametrize('url, platform, pid', [
    ('https://item.taobao.com/item.htm?id=123&spm=x', 'taobao', '123'),
    ('https://detail.tmall.com/item.htm?id=123', 'taobao', '123'),
    ('https://weidian.com/item.html?itemID=3053526244&vc_cps_track=x', 'weidian', '3053526244'),
    ('https://detail.1688.com/offer/1025411009174.html', '1688', '1025411009174'),
    ('https://www.cssbuy.com/item-1688-1025411009174.html', '1688', '1025411009174'),
    ('https://www.cssbuy.com/item-123.html', 'taobao', '123'),
    ('https://www.cssbuy.com/item-weidian-123.html', 'weidian', '123'),
    ('https://cnfans.com/product?id=889819872782&platform=TAOBAO', 'taobao', '889819872782'),
    ('https://cnfans.com/product?id=1025411009174&platform=ALI_1688', '1688', '1025411009174'),
    ('https://cnfans.com/product/?shop_type=weidian&id=7360033751&ref=77746', 'weidian', '7360033751'),
    ('https://cssbuy.com/?url=https%3A%2F%2Fweidian.com%2Fitem.html%3FitemID%3D123', 'weidian', '123'),
])
def test_cnlinks_formats_offline_namespace_separate(url, platform, pid):
    r = normalize_marketplace_link(url)
    assert r['marketplace'] == platform and r['product_id'] == pid
    assert normalize_marketplace_link(r['canonical_url']) == r
    s = Session([])
    assert resolve_one(s, url) == (None, None) # never a Hacoo ID
    assert s.calls == []

@pytest.mark.parametrize('url', [
    'https://cnfans.com/product?id=abc123&platform=TAOBAO',
    'https://cnfans.com/product?id=123',
    'https://cnfans.com/product?id=1&id=2&platform=TAOBAO',
    'https://cnfans.com.evil.test/product?id=123&platform=TAOBAO',
    'https://evil.test/?url=https://weidian.com/item.html?itemID=123',
    'https://weidian.com@evil.test/item.html?itemID=123',
    'https://item.taobao.com/item.htm?id=1&id=2',
    'https://m.tb.cn/a', 'https://weidian.com/item.html?itemID=abc',
])
def test_cnlinks_unknown_ambiguous_and_hostile_fail_closed(url):
    assert normalize_marketplace_link(url) is None

def test_resolver_identity_entrypoint():
    from resolver import resolve_identity
    s = Session([])
    result = resolve_identity(s, 'https://cnfans.com/product?id=123&platform=TAOBAO')
    assert result['kind'] == 'marketplace' and result['marketplace'] == 'taobao'
    assert result['canonical_url'] == 'https://item.taobao.com/item.htm?id=123'
    assert not s.calls
    assert resolve_identity(s, 'https://hacoo.app/detail/123')['kind'] == 'hacoo'

def test_retry_never_reenters_same_long_pass(monkeypatch):
    import resolver
    db = DB(':memory:'); add(db, 1)
    clock = [1000.0]
    monkeypatch.setattr(resolver.time, 'time', lambda: clock[0])
    monkeypatch.setattr(resolver.time, 'sleep', lambda _: clock.__setitem__(0, clock[0] + 120))
    s = Session([Resp(503)])
    assert resolve_pending(s, db) == 1
    assert len(s.calls) == 1
    assert db.unresolved_links(25) # eligible next invocation, not same pass

def test_existing_schema_migration_keeps_rows(tmp_path):
    import sqlite3
    path = str(tmp_path / 'legacy.db')
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE links (id INTEGER PRIMARY KEY, channel TEXT, message_id INTEGER, url TEXT, resolved_url TEXT, product_id TEXT, resolved_at REAL)')
    conn.execute("INSERT INTO links VALUES (1,'c',1,'https://onlyaff.app/a',NULL,NULL,NULL)")
    conn.commit(); conn.close()
    db = DB(path)
    row = db.conn.execute('SELECT * FROM links').fetchone()
    assert row['url'] == 'https://onlyaff.app/a'
    assert row['resolve_attempts'] == 0 and row['resolve_retry_at'] is None
    assert len(db.unresolved_links(25)) == 1
