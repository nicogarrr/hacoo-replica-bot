import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from db import DB
from trends import index_offer, trends, format_offer, offer_identity
from channels import ChannelMessage, crawl_channel
from config import Config
from handlers import make_handlers
NOW=1800000000

def offer(db, channel, n, url, age=0, text='Jordan 4', links=None):
    date=datetime.fromtimestamp(NOW-age*86400,timezone.utc).isoformat()
    msg=ChannelMessage(channel,n,date,'Jordan 4',text,links or [url])
    return index_offer(db,msg,url,now=NOW)

def test_namespaces_never_collide_or_enter_hacoo_search():
    db=DB(':memory:')
    for u in ['https://hacoo.app/detail/123','https://weidian.com/item.html?itemID=123','https://cnfans.com/product?id=123&platform=TAOBAO','https://detail.1688.com/offer/123.html']:
        assert offer(db,'sourcea',1,u)
    for ns in ['hacoo','weidian','taobao','1688']:
        assert len(trends(db,ns,now=NOW))==1
    assert db.stats()['links']==0

def test_dedup_sources_not_duplicate_posts_and_latest_link():
    db=DB(':memory:')
    offer(db,'sourcea',1,'https://item.taobao.com/item.htm?id=123&spm=x',age=2)
    offer(db,'sourcea',2,'https://cnfans.com/product?id=123&platform=TAOBAO',age=1)
    offer(db,'sourceb',3,'https://item.taobao.com/item.htm?id=123',age=0)
    r=trends(db,'taobao',now=NOW)[0]
    assert r['sources']==2 and r['posts']==3
    assert r['original_url']=='https://item.taobao.com/item.htm?id=123'
    assert r['channel']=='sourceb'
    offer(db,'sourceb',3,r['original_url'])
    assert trends(db,'taobao',now=NOW)[0]['posts']==3

def test_price_claims_and_recency_ranking():
    db=DB(':memory:')
    offer(db,'sourcea',1,'https://hacoo.app/detail/1',age=1,text='Antes 100 EUR ahora 70 EUR')
    offer(db,'sourcea',2,'https://hacoo.app/detail/2',age=0,text='Antes 100€ ahora 80€')
    r=trends(db,now=NOW)
    assert r[0]['identity']=='2' and r[0]['discount_pct']==20
    assert r[1]['discount_pct']==30
    assert 'El post anuncia 80.00 EUR' in format_offer(r[0])
    assert 'No comprueba stock' in format_offer(r[0])

def test_no_discount_guesses_or_multiproduct_prices():
    from trends import _prices
    for t in ['-50%!', '100 EUR 50 EUR', 'antes 10 EUR ahora 20 EUR',
              'antes 100 USD ahora 50 EUR', 'antes 100 EUR ahora 0 EUR',
              'antes 100 EUR ahora 50 EUR antes 80 EUR ahora 40 EUR']:
        assert _prices(t)==(None,None)
    db=DB(':memory:')
    offer(db,'sourcea',1,'https://hacoo.app/detail/1',text='Antes 100 EUR ahora 50 EUR',
          links=['https://hacoo.app/detail/1','https://hacoo.app/detail/2'])
    assert trends(db,now=NOW)[0]['discount_pct'] is None

def test_hostile_missing_old_future_and_html_escape():
    db=DB(':memory:')
    assert not offer(db,'sourcea',1,'https://evil.test/detail/1')
    assert not offer(db,'sourcea',2,'https://hacoo.app/detail/2',age=-1)
    assert index_offer(db,ChannelMessage('sourcea',3,'bad','a','',[]),'https://onlyaff.app/a',now=NOW) is False
    offer(db,'sourcea',4,'https://hacoo.app/detail/4',age=40)
    assert not trends(db,now=NOW)
    offer(db,'sourcea',5,'https://hacoo.app/detail/5')
    row=trends(db,now=NOW)[0];row['title']='<script>&'
    assert '&lt;script&gt;&amp;' in format_offer(row)
    assert 'afiliación propia verificada' in format_offer(row)

def test_shortlinks_no_title_based_merge_and_no_query_strip():
    db=DB(':memory:')
    for n,u in enumerate(['https://onlyaff.app/a#one','https://onlyaff.app/a#two','https://onlyaff.app/a?s=1','https://onlyaff.app/b'],1):
        offer(db,'sourcea',n,u)
    assert len(trends(db,now=NOW))==3

def test_crawler_marketplace_namespace_and_hacoo_only_links(monkeypatch):
    db=DB(':memory:')
    date=datetime.now(timezone.utc).isoformat()
    html=f'<div class="tgme_widget_message" data-post="sourcea/1"><time datetime="{date}"></time><div class="tgme_widget_message_text">Jordan <a href="https://cnfans.com/product?id=123&amp;platform=TAOBAO">agent</a><a href="https://onlyaff.app/a">hacoo</a></div></div>'
    monkeypatch.setattr('channels.fetch_page',lambda *a:html)
    assert crawl_channel(None,'sourcea',db,max_pages=1,sleep_s=0)==1
    assert len(trends(db,'taobao'))==1
    assert db.stats()['links']==1

def test_owner_private_only_no_publication():
    db=DB(':memory:');cfg=Config();h=make_handlers(cfg,db)
    class Msg:
        def __init__(self):self.replies=[]
        async def reply_text(self,t,**kw):self.replies.append(t)
    for uid,chat in [(cfg.owner_id,'group'),(1484047314,'private'),(123,'private')]:
        m=Msg();u=NS(effective_user=NS(id=uid),effective_chat=NS(type=chat),message=m,effective_message=m)
        asyncio.run(h['tendencias'](u,NS(args=[])))
        assert not m.replies or m.replies==['Este bot es privado. Pide acceso a su dueño.']

def test_resolved_hacoo_shortlinks_unify_dead_omitted():
    db=DB(':memory:')
    for n,c in [(1,'sourcea'),(2,'sourceb'),(3,'sourcec')]:
        u=f'https://onlyaff.app/{n}'
        offer(db,c,n,u)
        db.insert_message(c,n,'','Jordan','')
        db.insert_link(c,n,u)
        db.mark_resolved(n,'https://hacoo.app/detail/999','999')
    db.mark_checked(3,True)
    r=trends(db,now=NOW)
    assert len(r)==1 and r[0]['identity']=='999' and r[0]['sources']==2

def test_legacy_resolved_pid_mismatch_cannot_merge_unrelated_offers():
    db=DB(':memory:')
    for n in [1,2]:
        u=f'https://onlyaff.app/{n}'
        offer(db,'sourcea',n,u)
        db.insert_message('sourcea',n,'','Jordan','');db.insert_link('sourcea',n,u)
        db.mark_resolved(n,f'https://hacoo.app/detail/{n}','999')
    result=trends(db,now=NOW)
    assert len(result)==2 and all(r['identity']!='999' for r in result)

def test_legacy_invalid_price_pair_not_ranked_as_discount():
    db=DB(':memory:');offer(db,'sourcea',1,'https://hacoo.app/detail/1')
    db.conn.execute('UPDATE community_offers SET price_cents=20000,previous_cents=10000')
    r=trends(db,now=NOW)[0]
    assert r['price_cents'] is None and r['discount_pct'] is None
    assert 'El post anuncia' not in format_offer(r)
