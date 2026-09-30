import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from product_identity import hacoo_product_id
from product_state import classify_product_html
from resolver import extract_product_id
from trends import offer_identity
from link_health import LinkHealth
from test_product_state import Resp,Session,FIX

@pytest.mark.parametrize('url,pid',[
 ('https://www.hacoo.pl/p/14642740','14642740'),
 ('https://www.hacoo.pl/p/14642718','14642718'),
 ('https://www.hacoo.pl/p/14638268','14638268'),
 ('https://www.hacoo.pl/ES/detail/39459713','39459713'),
 ('https://www.hacoo.pl/ES/detail/39512968','39512968'),
 ('https://shop.hacoo.pl/es-ES/detail/40302592?tag=x','40302592')])
def test_shared_parser_production_aliases(url,pid):
    assert hacoo_product_id(url)==extract_product_id(url)==pid
    assert offer_identity(url)==('hacoo',pid)

@pytest.mark.parametrize('url',['https://hacoo.pl/foo/detail/123','https://hacoo.pl/detail/123junk','https://evil.test/ES/detail/123','https://hacoo.pl/ES/detail/１２３','https://hacoo.pl/detail/123/extra'])
def test_noncanonical_paths_never_get_ids(url):
    assert not hacoo_product_id(url)
    assert not extract_product_id(url)

@pytest.mark.parametrize('pid',['14642740','14642718','14638268','39459713','39512968'])
def test_production_db_label_not_product_label(pid):
    assert classify_product_html((FIX/(pid+'.html')).read_text(),pid)[0]=='unavailable'

def test_region_redirect_cannot_be_es_positive():
    s=Session([Resp(status=302,location='/en-US/detail/40302592'),Resp((FIX/'40302592.html').read_text())])
    assert LinkHealth().probe_product(s,'40302592')[0]=='unknown'

def test_short_unknown_cache_rechecks_after_15_seconds(monkeypatch):
    clock=[100.];monkeypatch.setattr('link_health.time.monotonic',lambda:clock[0])
    s=Session([Resp('',503),Resp((FIX/'40302592.html').read_text())]);h=LinkHealth()
    assert h.probe_product(s,'40302592')[0]=='unknown'
    clock[0]+=10
    assert h.probe_product(s,'40302592')[0]=='unknown' and len(s.calls)==1
    clock[0]+=6
    assert h.probe_product(s,'40302592')[0]=='present' and len(s.calls)==2

def test_es_alias_live_check_positive_fixture():
    s=Session([Resp(),Resp((FIX/'40302592.html').read_text())])
    assert LinkHealth().check(s,'https://www.hacoo.pl/ES/detail/40302592').status=='reachable'
