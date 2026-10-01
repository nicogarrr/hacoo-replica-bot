import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from db import DB
from link_health import LinkHealth,choose_link
from test_product_state import Resp,Session,FIX

def test_app_live_40800048_web_unavailable_original_link_retained():
    db=DB(':memory:');url='https://www.hacoo.pl/p/40800048'
    db.insert_message('sourcea',1,'','shoe','');db.insert_link('sourcea',1,url)
    db.mark_resolved(1,url,'40800048');r=dict(db.search_product_id('40800048')[0])
    s=Session([Resp(),Resp((FIX/'40800048.html').read_text())])
    c=choose_link(s,db,r,LinkHealth())
    assert c['link']==url and not c['verified']
    assert c['health']=='Sin verificar en web ES; puede estar disponible en la app.'
    assert 'caído' not in c['health'] and 'omitido' not in c['health']
    assert db.conn.execute('SELECT dead_at FROM links').fetchone()[0] is None

def test_positive_dead_route_still_suppressed():
    db=DB(':memory:');url='https://onlyaff.app/dead'
    db.insert_message('sourcea',1,'','shoe','');db.insert_link('sourcea',1,url)
    r=dict(db.fuzzy_candidates()[0])
    assert choose_link(Session([Resp(status=410)]),db,r,LinkHealth()) is None
    assert db.conn.execute('SELECT dead_at FROM links').fetchone()[0] is not None

def test_published_unverified_does_not_count_as_confirmed_model():
    from verified_results import confirmed_model_present
    r={'title':'Jordan 4','link':'https://www.hacoo.pl/p/40800048','verified':False}
    assert not confirmed_model_present([r],'4')
    r['verified']=True
    assert confirmed_model_present([r],'4')

def test_dedup_prefers_confirmed_over_clickable_unverified(monkeypatch):
    import verified_results
    from product_links import ProductLinks
    db=DB(':memory:')
    rows=[{'id':1,'product_id':'123','orig_url':'https://onlyaff.app/a','link':'https://onlyaff.app/a','title':'shoe'},
          {'id':2,'product_id':'123','orig_url':'https://onlyaff.app/b','link':'https://onlyaff.app/b','title':'shoe'}]
    monkeypatch.setattr(verified_results,'choose_link',lambda *a:dict(a[2],verified=a[2]['id']==2))
    got=verified_results.verify_results(None,db,rows,None,ProductLinks(),[12],None)
    assert len(got)==1 and got[0]['id']==2 and got[0]['verified']
