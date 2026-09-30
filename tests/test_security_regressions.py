import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bot'))
from db import DB
from product_links import ProductLinks
from url_policy import safe_product_url
from resolver import resolve_one
from handlers import make_handlers
from config import Config

@pytest.mark.parametrize('value', [123, True, [], {}, None])
def test_h2_mapping_wrong_types_no_startup_crash(tmp_path, value):
    f = tmp_path / 'map.json'
    f.write_text(json.dumps({'123': value}))
    assert ProductLinks(str(f)).mapping == {}

def test_h3_dead_or_precedence():
    db = DB(':memory:')
    for n, title in enumerate(['Nike', 'Dunk', 'Nike Dunk'], 1):
        db.insert_message('c', n, '', title, '')
        db.insert_link('c', n, f'https://onlyaff.app/{n}')
    db.mark_checked(1, True)
    db.mark_checked(2, True)
    assert [r['id'] for r in db.search_like('Nike Dunk', mode='or')] == [3]

@pytest.mark.parametrize('url', ['https://attacker.example/detail/123',
    'http://hacoo.app/detail/1', 'https://hacoo.app@attacker.example/x',
    'https://hacoo.app.evil.com/x', 'https://hacoo.xyz/x',
    'https://hacoo.app:123/x', 'https://hacoo.app:bad/x'])
def test_h6_unsafe_urls_never_requested_or_output(url):
    assert not safe_product_url(url)
    assert ProductLinks().for_result({'link': url}) == ''
    class Session:
        def get(self, *a, **kw): raise AssertionError('unsafe request')
    assert resolve_one(Session(), url) == (None, None)

def test_h6_cross_host_redirect_and_shortlink_id():
    class Resp:
        status_code = 302
        headers = {'Location': 'https://attacker.example/detail/123'}
        def close(self): pass
    class Session:
        calls = []
        def get(self, url, **kw): self.calls.append(url); return Resp()
    s = Session()
    assert resolve_one(s, 'https://onlyaff.app/a') == (None, None)
    assert len(s.calls) == 1
    Resp.status_code = 200
    assert resolve_one(s, 'https://onlyaff.app/detail/123') == ('https://onlyaff.app/detail/123', '')

def test_h12_stats_failed_not_resolved():
    db = DB(':memory:')
    db.insert_message('c', 1, '', 'Nike', '')
    db.insert_link('c', 1, 'https://onlyaff.app/a')
    db.mark_failed(1)
    assert db.stats()['resolved'] == 0
    db.mark_resolved(1, 'https://hacoo.app/detail/123', '123')
    assert db.stats()['resolved'] == 1

class Msg:
    text = 'Nike Dunk'
    def __init__(self): self.replies = []
    async def reply_text(self, text, **kw): self.replies.append(text)

@pytest.mark.parametrize('command', ['stats', 'canales', 'foto', 'agregarcanal'])
def test_h11_private_only_and_missing_chat(command):
    cfg = Config()
    db = DB(':memory:')
    h = make_handlers(cfg, db)
    for chat in [NS(type='group'), None]:
        m = Msg()
        u = NS(effective_user=NS(id=cfg.owner_id), effective_chat=chat,
               message=m, effective_message=m)
        asyncio.run(h[command](u, NS(args=[])))
        assert not m.replies

def test_private_owner_and_off_nonmember_and_controlled_sql_error():
    cfg = Config()
    cfg.public_search_enabled = False
    db = DB(':memory:')
    h = make_handlers(cfg, db)
    class Bot:
        async def get_chat_member(self, *a): raise AssertionError('OFF')
    ctx = NS(args=['Nike', 'Dunk'], bot=Bot())
    m = Msg()
    u = NS(effective_user=NS(id=cfg.owner_id), effective_chat=NS(type='private'),
           message=m, effective_message=m)
    asyncio.run(h['stats'](u, ctx))
    assert m.replies
    m.replies.clear()
    u.effective_user.id = 123
    asyncio.run(h['buscar'](u, ctx))
    assert m.replies == ['Este bot es privado. Pide acceso a su dueño.']
    u.effective_user.id = cfg.owner_id
    db.close()
    asyncio.run(h['buscar'](u, ctx))
    assert m.replies[-1] == 'No pude consultar el índice. Prueba otra vez.'
