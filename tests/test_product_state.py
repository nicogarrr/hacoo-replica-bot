import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from product_state import classify_product_html
FIX=Path(__file__).parent/'fixtures'/'product-state'

def page(detail,text=''):
    return '<p>'+text+'</p><script id="__F_STATE__">'+json.dumps({'detail':detail})+'</script>'

def test_two_real_positive_ssr_fixtures():
    for pid in ['40302592','39928200']:
        status,reason=classify_product_html((FIX/(pid+'.html')).read_text(),pid)
        assert status=='present' and 'stock no verificado' in reason

def test_real_web_unavailable_not_global_deletion():
    status,reason=classify_product_html((FIX/'40777036.html').read_text(),'40777036')
    assert status=='unavailable' and 'región' in reason
    assert 'borrado' not in reason

def test_spa_landing_mismatched_id_and_error_unknown():
    assert classify_product_html('<title>Hacoo</title>','123')[0]=='unknown'
    assert classify_product_html((FIX/'40302592.html').read_text(),'123')[0]=='unknown'
    d={'itemId':123,'itemDetail':None,'isAbnormalItem':True,'errorCode':'E429'}
    assert classify_product_html(page(d,'Este producto no está disponible'),'123')[0]=='unknown'
    d['errorCode']=''
    assert classify_product_html(page(d),'123')[0]=='unknown'
    assert classify_product_html('<script id="__F_STATE__">broken</script>','123')[0]=='unknown'

def test_status_or_title_or_inner_id_insufficient():
    for item in [{'id':123,'status':0,'title':'shoe'},{'id':999,'status':1,'title':'shoe'},{'id':123,'status':1,'title':''}]:
        assert classify_product_html(page({'itemId':123,'itemDetail':item}),'123')[0]=='unknown'

from link_health import LinkHealth,choose_link
from db import DB
import requests

class Resp:
    def __init__(self,body='',status=200,location=None):
        self.status_code=status;self.headers={'Location':location} if location else {};self.body=body
        self.closed=False
    def close(self):self.closed=True
    def iter_content(self,chunk_size):yield self.body.encode()
class Session:
    def __init__(self,responses):self.responses=iter(responses);self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append(url);r=next(self.responses)
        if isinstance(r,Exception):raise r
        return r

def test_live_route_plus_real_positive_probe_and_cache():
    html=(FIX/'40302592.html').read_text()
    s=Session([Resp(),Resp(html),Resp()]);h=LinkHealth()
    assert h.check(s,'https://hacoo.app/detail/40302592').status=='reachable'
    assert s.calls[1]=='https://shop.hacoo.pl/es-ES/detail/40302592'
    assert h.check(s,'https://hacoo.pl/detail/40302592').status=='reachable'
    assert len(s.calls)==3 # product cache reused across route hosts

def test_real_unavailable_has_no_button_not_marked_dead():
    db=DB(':memory:');url='https://hacoo.app/detail/40777036'
    db.insert_message('sourcea',1,'','Jordan','');db.insert_link('sourcea',1,url)
    db.mark_resolved(1,url,'40777036');r=dict(db.search_product_id('40777036')[0])
    s=Session([Resp(),Resp((FIX/'40777036.html').read_text())])
    c=choose_link(s,db,r,LinkHealth())
    assert c['link']==url and not c['verified'] and 'Sin verificar' in c['health']
    assert db.conn.execute('SELECT dead_at FROM links').fetchone()[0] is None

def test_generic_200_never_gets_link_and_errors_unknown():
    for response in [Resp('<title>Hacoo</title>'),Resp('',503),requests.Timeout()]:
        s=Session([Resp(),response]);h=LinkHealth()
        assert h.check(s,'https://hacoo.app/detail/123').status=='unknown'

def test_probe_redirect_external_not_requested_and_mismatched_id():
    s=Session([Resp(status=302,location='https://evil.test/x')])
    assert LinkHealth().probe_product(s,'123')[0]=='unknown'
    assert len(s.calls)==1
    s=Session([Resp((FIX/'40302592.html').read_text())])
    assert LinkHealth().probe_product(s,'999')[0]=='unknown'

def test_probe_timeout_response_size_and_deadline_unknown():
    import time
    s=Session([])
    assert LinkHealth().probe_product(s,'123',deadline=time.monotonic()-1)[0]=='unknown'
    assert not s.calls
    s=Session([Resp('x'*2_000_001)])
    assert LinkHealth().probe_product(s,'123')[0]=='unknown'

def test_no_id_route_not_proven_product():
    s=Session([Resp()])
    assert LinkHealth().check(s,'https://hacoo.app/').status=='unknown'
    assert len(s.calls)==1

def test_checker_product_unavailable_handler_has_no_clickable_product(monkeypatch):
    import asyncio
    from types import SimpleNamespace as NS
    import handlers
    from config import Config
    from handlers import make_handlers
    db=DB(':memory:');url='https://hacoo.app/detail/40777036'
    db.insert_message('sourcea',1,'2099-01-01','Jordan 4','')
    db.insert_link('sourcea',1,url);db.mark_resolved(1,url,'40777036')
    session=Session([Resp(),Resp((FIX/'40777036.html').read_text())])
    monkeypatch.setattr(handlers,'_get_session',lambda:session)
    monkeypatch.setattr(handlers,'_link_health',LinkHealth())
    class Msg:
        text='Jordan 4'
        def __init__(self):self.replies=[]
        async def reply_text(self,t,**kw):self.replies.append(t)
    m=Msg();cfg=Config();h=make_handlers(cfg,db)
    u=NS(effective_chat=NS(type='private'),effective_user=NS(id=cfg.owner_id),message=m,effective_message=m)
    asyncio.run(h['buscar'](u,NS(args=[])))
    text='\n'.join(m.replies)
    assert 'Sin verificar' in text and 'Abrir en Hacoo' in text and 'Enlace omitido' not in text

# A real globally-deleted fixture must be owner-labeled before adding a deletion
# assertion. Current negative fixture proves web-ES unavailability only.

def test_redirect_to_different_real_product_not_substitute():
    db=DB(':memory:');url='https://onlyaff.app/a'
    db.insert_message('sourcea',1,'','Jordan','');db.insert_link('sourcea',1,url)
    db.mark_resolved(1,'https://hacoo.app/detail/40777036','40777036')
    r=dict(db.search_product_id('40777036')[0])
    s=Session([Resp(status=302,location='https://hacoo.app/detail/40302592'),Resp(),Resp((FIX/'40302592.html').read_text())])
    c=choose_link(s,db,r,LinkHealth())
    assert c is None

def test_unresolved_original_cannot_emit_old_destination_of_different_product():
    db=DB(':memory:');url='https://onlyaff.app/new'
    db.insert_message('sourcea',1,'','shoe','');db.insert_link('sourcea',1,url)
    # Legacy resolved destination without trustworthy product_id.
    db.mark_resolved(1,'https://hacoo.app/detail/39928200',None)
    r=dict(db.fuzzy_candidates()[0])
    s=Session([Resp(status=302,location='https://hacoo.app/detail/40302592'),Resp(),
        Resp((FIX/'40302592.html').read_text()),Resp(),Resp((FIX/'39928200.html').read_text())])
    c=choose_link(s,db,r,LinkHealth())
    assert c['product_id']=='40302592'
    assert c['link']=='https://hacoo.app/detail/40302592'

def test_second_route_cache_cannot_extend_product_presence_ttl(monkeypatch):
    clock=[100.];monkeypatch.setattr('link_health.time.monotonic',lambda:clock[0])
    h=LinkHealth(ttl=120)
    html=(FIX/'40302592.html').read_text()
    s=Session([Resp(),Resp(html),Resp(),Resp(),Resp('<title>Hacoo</title>')])
    assert h.check(s,'https://hacoo.app/detail/40302592').status=='reachable'
    clock[0]=219
    assert h.check(s,'https://hacoo.pl/detail/40302592').status=='reachable'
    assert len(s.calls)==3 # older product proof reused, not renewed
    clock[0]=221
    assert h.check(s,'https://hacoo.pl/detail/40302592').status=='unknown'
    assert len(s.calls)==5
