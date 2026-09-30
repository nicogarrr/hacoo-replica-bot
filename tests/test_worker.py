import asyncio
import threading
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from worker import drain_worker

def test_cancellation_waits_for_thread_before_return():
    started=threading.Event();finish=threading.Event();events=[]
    def work():
        started.set();finish.wait(2);events.append('worker-finished')
    async def run():
        task=asyncio.create_task(drain_worker(work))
        while not started.is_set():await asyncio.sleep(.001)
        task.cancel();await asyncio.sleep(.01)
        assert not task.done()
        finish.set()
        try:await task
        except asyncio.CancelledError:events.append('cancel-returned')
    asyncio.run(run())
    assert events==['worker-finished','cancel-returned']

def test_worker_result_and_error_propagate():
    assert asyncio.run(drain_worker(lambda:42))==42
    def fail():raise ValueError('test')
    import pytest
    with pytest.raises(ValueError):asyncio.run(drain_worker(fail))

def test_indexer_cancel_closes_session_after_active_work(monkeypatch):
    import main
    from types import SimpleNamespace as NS
    events=[];started=threading.Event();finish=threading.Event()
    class Session:
        def close(self):events.append('session-closed')
    class DB:
        def channels(self,*a):return ['sourcea']
    def crawl(*a):started.set();finish.wait(2);events.append('crawl-finished');return 0
    monkeypatch.setattr(main,'make_session',lambda:Session())
    monkeypatch.setattr(main,'crawl_channel',crawl)
    cfg=NS(channels=[],max_pages_per_run=1,resolve_links=False,index_interval_min=1)
    async def run():
        task=asyncio.create_task(main.indexer_loop(cfg,DB()))
        while not started.is_set():await asyncio.sleep(.001)
        task.cancel();await asyncio.sleep(.01)
        assert events==[]
        finish.set()
        try:await task
        except asyncio.CancelledError:pass
    asyncio.run(run())
    assert events==['crawl-finished','session-closed']

def test_startup_failure_does_not_start_indexer_and_closes_db(monkeypatch):
    import main
    from config import Config
    events=[]
    class FakeDB:
        def __init__(self,*a):pass
        def close(self):events.append('db-closed')
    class App:
        def add_handler(self,*a):pass
        async def initialize(self):raise ValueError('startup')
        async def shutdown(self):events.append('shutdown')
    class Builder:
        def token(self,*a):return self
        def build(self):return App()
    monkeypatch.setattr(main,'DB',FakeDB)
    monkeypatch.setattr(main,'make_handlers',lambda *a:{k:None for k in ['start','ayuda','stats','tendencias','canales','agregarcanal','buscar','foto','texto']})
    monkeypatch.setattr(main.Application,'builder',lambda:Builder())
    monkeypatch.setattr(Config,'validate',lambda *a,**k:None)
    monkeypatch.delenv('INDEXER_ONLY',raising=False)
    import pytest
    with pytest.raises(ValueError,match='startup'):asyncio.run(main.main())
    assert events==['db-closed']
