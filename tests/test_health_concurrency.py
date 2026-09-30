import threading
import time
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from link_health import LinkHealth
from test_product_state import Resp,FIX

def test_same_product_concurrent_probe_only_one_network_call():
    started=threading.Event();release=threading.Event()
    class Session:
        calls=0
        def get(self,url,**kw):
            self.calls+=1;started.set();release.wait(2)
            return Resp((FIX/'40302592.html').read_text())
    s=Session();h=LinkHealth()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(h.probe_product,s,'40302592')
        assert started.wait(1)
        b=pool.submit(h.probe_product,s,'40302592')
        time.sleep(.01);release.set()
        assert a.result()[0]==b.result()[0]=='present'
    assert s.calls==1

def test_concurrent_route_cached_and_wait_budget_unknown():
    started=threading.Event();release=threading.Event()
    class Session:
        calls=0
        def get(self,url,**kw):
            self.calls+=1;started.set();release.wait(2)
            return Resp('',404)
    s=Session();h=LinkHealth();url='https://onlyaff.app/a'
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(h.check,s,url)
        assert started.wait(1)
        b=pool.submit(h.check,s,url,time.monotonic()+.01)
        assert b.result().status=='unknown'
        release.set();assert a.result().status=='dead'
    assert h.check(s,url).status=='dead' and s.calls==1
    assert len(h.route_locks)==len(h.product_locks)==32
