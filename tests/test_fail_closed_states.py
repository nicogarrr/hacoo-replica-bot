import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from channel_access import SubscriberGate
from product_state import classify_product_html
from test_product_state import page

def test_first_throttle_request_after_restart_not_denied(monkeypatch):
    monkeypatch.setattr('channel_access.time.monotonic',lambda:1.)
    gate=SubscriberGate(0,False)
    assert not gate.throttle(123)
    assert gate.throttle(123)

def test_inconsistent_abnormal_product_never_positive():
    d={'itemId':123,'itemDetail':{'id':123,'title':'shoe','status':1},'isAbnormalItem':True}
    assert classify_product_html(page(d),'123')[0]=='unknown'
    d['isAbnormalItem']=False;d['itemDetail']['status']=True
    assert classify_product_html(page(d),'123')[0]=='unknown'

def test_duplicate_state_scripts_never_positive():
    d={'itemId':123,'itemDetail':{'id':123,'title':'shoe','status':1}}
    assert classify_product_html(page(d)+page(d),'123')[0]=='unknown'
