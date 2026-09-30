import asyncio
import sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from db import DB
from trends import index_offer
from channels import ChannelMessage
from handlers import make_handlers
from config import Config

def test_replacement_uses_actual_source_and_not_old_post_discount(monkeypatch):
    import handlers
    db=DB(':memory:');now=datetime.now(timezone.utc)
    for n,c,age in [(1,'sourcea',0),(2,'sourceb',1)]:
        u=f'https://onlyaff.app/{n}'
        date=(now-timedelta(days=age)).isoformat()
        db.insert_message(c,n,date,'Jordan','');db.insert_link(c,n,u)
        db.mark_resolved(n,'https://hacoo.app/detail/123','123')
        index_offer(db,ChannelMessage(c,n,date,'Jordan','antes 100 EUR ahora 50 EUR',[u]),u)
    def choose(*args):
        r=args[2]
        return dict(r,link='https://hacoo.app/detail/123',channel='sourceb',message_id=2,health='present')
    monkeypatch.setattr(handlers,'choose_link',choose)
    monkeypatch.setattr(handlers,'_get_session',lambda:None)
    class Msg:
        def __init__(self):self.replies=[]
        async def reply_text(self,t,**kw):self.replies.append(t)
    cfg=Config();m=Msg();u=NS(effective_user=NS(id=cfg.owner_id),effective_chat=NS(type='private'),message=m,effective_message=m)
    asyncio.run(make_handlers(cfg,db)['tendencias'](u,NS(args=[])))
    text='\n'.join(m.replies)
    assert 'https://t.me/sourceb/2' in text
    assert 'https://t.me/sourcea/1' not in text
    assert 'El post anuncia' not in text
