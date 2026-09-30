import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from main import remaining_cycle_budget,cycle_sleep

def test_cycle_does_not_add_full_interval_after_work():
    assert cycle_sleep(100,3600,now=1300)==2400
    assert cycle_sleep(100,3600,now=3700)==60
    assert cycle_sleep(100,3600,now=5000)==60

def test_shared_resolver_health_budget_reserves_pause():
    assert remaining_cycle_budget(100,3600,now=1300)==2340
    assert remaining_cycle_budget(100,3600,now=3650)==0
    assert remaining_cycle_budget(100,60,now=100)==0

def test_overrun_skips_resolver_and_health_not_unlimited(monkeypatch):
    import asyncio
    import main
    from types import SimpleNamespace as NS
    calls=[];clock=[100.]
    class Session:
        def close(self):calls.append('closed')
    class DB:
        def channels(self,*a):return ['sourcea']
    monkeypatch.setattr(main,'make_session',lambda:Session())
    monkeypatch.setattr(main.time,'monotonic',lambda:clock[0])
    def crawl(*a):calls.append('crawl');clock[0]+=3700;return 0
    monkeypatch.setattr(main,'crawl_channel',crawl)
    monkeypatch.setattr(main,'resolve_pending',lambda *a:(_ for _ in ()).throw(AssertionError('overrun resolver')))
    monkeypatch.setattr(main,'check_pending',lambda *a:(_ for _ in ()).throw(AssertionError('overrun health')))
    async def sleep(seconds):calls.append(seconds);raise asyncio.CancelledError()
    monkeypatch.setattr(main.asyncio,'sleep',sleep)
    cfg=NS(channels=[],max_pages_per_run=1,resolve_links=True,index_interval_min=60,resolve_rate_per_min=30)
    async def run():
        try:await main.indexer_loop(cfg,DB())
        except asyncio.CancelledError:pass
    asyncio.run(run())
    assert calls==['crawl',60,'closed']

def test_backlogged_resolver_reserves_liveness_turn(monkeypatch):
    import asyncio
    import main
    from types import SimpleNamespace as NS
    clock=[100.];calls=[]
    class Session:
        def close(self):pass
    class DB:
        def channels(self,*a):return []
    monkeypatch.setattr(main,'make_session',lambda:Session())
    monkeypatch.setattr(main.time,'monotonic',lambda:clock[0])
    def resolve(s,d,r,budget):calls.append(('resolver',budget));clock[0]+=budget;return 1
    def health(s,d,r,budget):calls.append(('health',budget));return (1,0)
    monkeypatch.setattr(main,'resolve_pending',resolve)
    monkeypatch.setattr(main,'check_pending',health)
    async def stop(_):raise asyncio.CancelledError()
    monkeypatch.setattr(main.asyncio,'sleep',stop)
    cfg=NS(channels=[],max_pages_per_run=1,resolve_links=True,index_interval_min=60,resolve_rate_per_min=30)
    async def run():
        try:await main.indexer_loop(cfg,DB())
        except asyncio.CancelledError:pass
    asyncio.run(run())
    assert calls==[('resolver',2940),('health',600)]
