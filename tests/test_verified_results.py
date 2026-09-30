import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from db import DB
from link_health import Health
from product_links import ProductLinks
from verified_results import verify_results,confirmed_model_present

def rows():
    db=DB(':memory:')
    for n in range(1,9):
        db.insert_message('sourcea',n,'2099-01-01','Jordan 4','')
        db.insert_link('sourcea',n,f'https://hacoo.app/detail/{n}')
        db.mark_resolved(n,f'https://hacoo.app/detail/{n}',str(n))
    return db,[dict(r) for r in db.fuzzy_candidates()]
class Checker:
    def __init__(self,states):self.states=states;self.calls=[]
    def check(self,session,url,deadline):
        self.calls.append(url);pid=url.rsplit('/',1)[-1]
        return Health(self.states.get(pid,'reachable'),url,'test')

def test_first_five_dead_refilled_without_new_search_or_budget():
    db,r=rows();h=Checker({str(i):'dead' for i in range(4,9)});budget=[12]
    got=verify_results(None,db,r,h,ProductLinks(),budget,None)
    assert [x['product_id'] for x in got]==['3','2','1']
    assert len(h.calls)==8 and budget[0]==4

def test_unknowns_do_not_push_out_later_live_results():
    db,r=rows();h=Checker({str(i):'unknown' for i in range(4,9)})
    got=verify_results(None,db,r,h,ProductLinks(),[12],None)
    assert [x['product_id'] for x in got[:3]]==['3','2','1']
    assert len(got)==5 and all(not x['link'] for x in got[3:])

def test_exact_header_requires_visible_confirmed_model():
    assert not confirmed_model_present([{'title':'Jordan 4 Military Black','link':''}],'4 Military')
    assert not confirmed_model_present([{'title':'Jordan 14 Military Black','link':'yes'}],'4 Military')
    assert confirmed_model_present([{'title':'Jordan 4 Military Black','link':'yes'}],'4 Military')

def test_budget_not_reset_by_overfetch():
    db,r=rows();h=Checker({str(i):'dead' for i in range(1,9)})
    got=verify_results(None,db,r,h,ProductLinks(),[2],None)
    assert len(h.calls)==2
    assert all(not x['link'] for x in got)

def test_search_handler_refills_after_first_five_die(monkeypatch):
    import asyncio
    from types import SimpleNamespace as NS
    import handlers
    from config import Config
    db,r=rows();h=Checker({str(i):'dead' for i in range(4,9)})
    monkeypatch.setattr(handlers,'_link_health',h)
    monkeypatch.setattr(handlers,'_get_session',lambda:None)
    class Msg:
        text='Jordan 4'
        def __init__(self):self.replies=[]
        async def reply_text(self,t,**kw):self.replies.append(t)
    cfg=Config();m=Msg();u=NS(effective_user=NS(id=cfg.owner_id),effective_chat=NS(type='private'),message=m,effective_message=m)
    asyncio.run(handlers.make_handlers(cfg,db)['buscar'](u,NS(args=[])))
    text='\n'.join(m.replies)
    assert 'Abrir en Hacoo' in text and 'detail/3' in text and 'detail/8' not in text

def test_later_confirmed_duplicate_replaces_earlier_unknown(monkeypatch):
    import verified_results
    db,r=rows();a,b=r[:2]
    a['product_id']=b['product_id']='123'
    def choose(*args):
        row=args[2]
        return dict(row,link='' if row['id']==a['id'] else row['link'])
    monkeypatch.setattr(verified_results,'choose_link',choose)
    got=verify_results(None,db,[a,b],Checker({}),ProductLinks(),[12],None)
    assert len(got)==1 and got[0]['link'] and got[0]['id']==b['id']
