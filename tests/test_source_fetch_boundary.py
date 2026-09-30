import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from channels import fetch_page
from config import Config

@pytest.mark.parametrize('source',['foo?before=2','foo/bar','https://evil.test','../foo','foo#x','foo\nbar','@foo','a',123])
def test_fetch_rejects_untrusted_source_without_request(source):
    class Session:
        def get(self,*a,**kw):raise AssertionError('no request')
    with pytest.raises(ValueError):fetch_page(Session(),source)

@pytest.mark.parametrize('cursor',[-1,True,'2'])
def test_fetch_cursor_must_be_nonnegative_integer(cursor):
    with pytest.raises(ValueError):fetch_page(None,'sourcea',cursor)

def test_config_invalid_source_fails_before_crawl(monkeypatch):
    monkeypatch.setenv('CHANNELS','sourcea,foo?before=2')
    with pytest.raises(SystemExit,match='CHANNELS'):Config().validate(require_token=False)
