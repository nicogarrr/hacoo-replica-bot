import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from channels import fetch_page

class Response:
    def __init__(self,code=200,location=None):
        self.status_code=code;self.headers={'Location':location} if location else {};self.text='page';self.closed=False
    def raise_for_status(self):pass
    def close(self):self.closed=True
class Session:
    def __init__(self,responses):self.responses=iter(responses);self.calls=[]
    def get(self,url,**kw):
        assert kw['allow_redirects'] is False
        self.calls.append(url);return next(self.responses)

@pytest.mark.parametrize('location',['https://evil.test/s/sourcea','http://t.me/s/sourcea','https://t.me/sourcea','https://t.me/s/sourceb','https://t.me/s/sourcea?before=9','https://t.me@evil.test/s/sourcea','https://t.me:123/s/sourcea'])
def test_redirect_outside_exact_source_not_fetched(location):
    r=Response(302,location);s=Session([r])
    with pytest.raises(ValueError):fetch_page(s,'sourcea')
    assert len(s.calls)==1 and r.closed

def test_relative_canonical_redirect_same_cursor_allowed():
    r=Response(302,'/s/sourcea/?before=10');end=Response();s=Session([r,end])
    assert fetch_page(s,'sourcea',10)=='page'
    assert len(s.calls)==2 and r.closed and end.closed

def test_redirect_loop_and_non200_bounded():
    s=Session([Response(302,'/s/sourcea') for _ in range(4)])
    with pytest.raises(ValueError,match='Demasiadas'):fetch_page(s,'sourcea')
    assert len(s.calls)==4
    with pytest.raises(ValueError):fetch_page(Session([Response(204)]),'sourcea')
