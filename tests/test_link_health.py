import sys
import time
from pathlib import Path
import requests
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from db import DB
from link_health import LinkHealth, choose_link
from trends import format_offer
from test_crawler_regressions import Resp, Session

@pytest.fixture(autouse=True)
def isolate_route_tests_from_product_probe(monkeypatch):
    # Original route-check regressions. SSR product checker tested separately.
    monkeypatch.setattr(LinkHealth, 'probe_product',
                        lambda *a, **k: ('present', 'ficha presente; stock no verificado'))

def rows():
    db=DB(':memory:')
    for n in [1,2]:
        db.insert_message('sourcea',n,'2099-01-01','Jordan 4','')
        db.insert_link('sourcea',n,f'https://onlyaff.app/{n}')
        db.mark_resolved(n,'https://hacoo.app/detail/123','123')
    return db,dict(db.search_product_id('123')[1])

def test_dead_detected_replaced_by_other_confirmed_source():
    db,r=rows()
    s=Session([Resp(410),Resp(302,'https://hacoo.app/detail/123'),Resp(200)])
    chosen=choose_link(s,db,r,LinkHealth())
    assert chosen['id']==2 and chosen['orig_url']=='https://onlyaff.app/2'
    assert chosen['link']=='https://hacoo.app/detail/123'
    assert db.conn.execute('SELECT dead_at FROM links WHERE id=1').fetchone()[0]
    assert len(s.calls)==3

def test_all_dead_omitted_and_never_synthesize_url():
    db,r=rows();s=Session([Resp(404),Resp(404)])
    assert choose_link(s,db,r,LinkHealth()) is None
    assert all('detail' not in u for u in s.calls)
    assert db.search_product_id('123')==[]

def test_timeout_unknown_warning_without_clickable_product_link():
    db,r=rows();s=Session([requests.Timeout(),requests.Timeout()])
    chosen=choose_link(s,db,r,LinkHealth())
    assert chosen['link']==r['orig_url'] and 'Sin verificar' in chosen['health'] and not chosen['verified']
    assert db.conn.execute('SELECT COUNT(*) FROM links WHERE dead_at IS NOT NULL').fetchone()[0]==0

def test_200_shortlink_not_treated_as_product_and_spa_only_route():
    h=LinkHealth()
    assert h.check(Session([Resp(200)]),'https://onlyaff.app/a').status=='unknown'
    result=h.check(Session([Resp(200)]),'https://hacoo.app/detail/123')
    assert result.status=='reachable' and 'stock no verificado' in result.reason

def test_cache_short_lived_and_hostile_redirect_not_followed(monkeypatch):
    clock=[1.0];monkeypatch.setattr('link_health.time.monotonic',lambda:clock[0])
    h=LinkHealth(ttl=120);s=Session([Resp(404),Resp(200)])
    assert h.check(s,'https://hacoo.app/detail/1').status=='dead'
    assert h.check(s,'https://hacoo.app/detail/1').status=='dead'
    assert len(s.calls)==1
    clock[0]=122
    assert h.check(s,'https://hacoo.app/detail/1').status=='reachable'
    s=Session([Resp(302,'https://evil.test/a')])
    assert h.check(s,'https://onlyaff.app/unsafe').status=='dead'
    assert len(s.calls)==1

def test_mapping_dead_falls_back_to_confirmed_route_mapping_preserved():
    db,r=rows();r['orig_url']='https://hacoo.app/detail/123'
    s=Session([Resp(200),Resp(404)])
    c=choose_link(s,db,r,LinkHealth(),output_url='https://onlyaff.app/mapping')
    assert c['link']=='https://hacoo.app/detail/123'
    s=Session([Resp(200),Resp(302,'https://hacoo.app/detail/123'),Resp(200)])
    c=choose_link(s,db,r,LinkHealth(),output_url='https://onlyaff.app/map?tag=approved')
    assert c['link']=='https://onlyaff.app/map?tag=approved'

def test_budget_deadline_zero_no_network_and_warning():
    db,r=rows();s=Session([])
    c=choose_link(s,db,r,LinkHealth(),deadline=time.monotonic()-1)
    assert c['link']==r['orig_url'] and not c['verified'] and not s.calls
    assert choose_link(s,db,r,LinkHealth(),budget=[0])['verified'] is False

def test_draft_unknown_has_no_clickable_product_link():
    r=dict(title='Jordan',posted_ts=1800000000,namespace='hacoo',sources=1,
           price_cents=None,previous_cents=None,original_url='',channel='sourcea',
           message_id=1,health='Puede estar caído')
    text=format_offer(r)
    assert 'Puede estar caído' in text
    assert 'Abrir en Hacoo' not in text and 'href="https://hacoo' not in text

def test_search_and_trends_handlers_omit_dead_replace_or_warn(monkeypatch):
    import asyncio
    from types import SimpleNamespace as NS
    import handlers
    from config import Config
    from handlers import make_handlers
    from trends import index_offer
    from channels import ChannelMessage
    from datetime import datetime,timezone
    for command, responses, expected in [
        ('buscar',[Resp(404),Resp(404)],'rutas están caídas'),
        ('buscar',[requests.Timeout(),requests.Timeout()],'Sin verificar'),
        ('buscar',[Resp(404),Resp(302,'https://hacoo.app/detail/123'),Resp(200)],'Abrir en Hacoo'),
        ('tendencias',[requests.Timeout(),requests.Timeout()],'Sin verificar'),
    ]:
        db,r=rows()
        now=datetime.now(timezone.utc).isoformat()
        for n in [1,2]:
            index_offer(db,ChannelMessage('sourcea',n,now,'Jordan 4','Jordan 4',
                       [f'https://onlyaff.app/{n}']),f'https://onlyaff.app/{n}')
        session=Session(responses)
        monkeypatch.setattr(handlers,'_get_session',lambda:session)
        monkeypatch.setattr(handlers,'_link_health',LinkHealth())
        class Msg:
            text='Jordan 4'
            def __init__(self):self.replies=[]
            async def reply_text(self,t,**kw):self.replies.append(t)
        m=Msg();cfg=Config();h=make_handlers(cfg,db)
        u=NS(effective_chat=NS(type='private'),effective_user=NS(id=cfg.owner_id),message=m,effective_message=m)
        asyncio.run(h[command](u,NS(args=[])))
        text='\n'.join(m.replies)
        assert expected in text
        if expected == 'rutas están caídas':
            assert 'Abrir en Hacoo' not in text
