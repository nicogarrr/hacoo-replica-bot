import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))
from channel_registry import normalize_source, preview_source
from db import DB


@pytest.mark.parametrize("raw, expected", [
    ("https://t.me/s/Links_Hacoo", "links_hacoo"),
    ("@hacoolinks", "hacoolinks"),
    ("hacoolinks", "hacoolinks"),
])
def test_valid_public_source(raw, expected):
    assert normalize_source(raw) == expected


@pytest.mark.parametrize("raw", [
    "https://t.me/+invite", "https://t.me/s/foo?before=5",
    "https://t.me/s/foo/4", "http://t.me/s/foo", "https://evil.tld/s/foo",
    "https://t.me.evil.tld/s/foo", "https://t.me:123/s/foo",
    "https://t.me/s/foo#x", "../../../etc/passwd", "a",
])
def test_reject_nonpublic_or_hostile_source(raw):
    with pytest.raises(ValueError):
        normalize_source(raw)


def test_preview_and_persistent_registration(tmp_path):
    html = open(os.path.join(os.path.dirname(__file__), "fixture_channel.html")).read()
    class Resp:
        status_code = 200
        headers = {}
        def close(self): pass
        text = html
        def raise_for_status(self): pass
    class Session:
        def get(self, url, timeout, allow_redirects=False):
            assert url == "https://t.me/s/hacoolinks"
            return Resp()
    preview = preview_source(Session(), "hacoolinks")
    assert preview == {"messages_with_links": 2, "candidate_links": 2}
    path = str(tmp_path / "index.db")
    db = DB(path)
    assert db.add_channel("hacoolinks", [])
    assert not db.add_channel("hacoolinks", [])
    db.close()
    db = DB(path)
    assert db.channels([]) == ["hacoolinks"]
    db.close()


def test_preview_rejects_external_link_even_with_one_hacoo_candidate():
    class Resp:
        status_code = 200
        headers = {}
        def close(self): pass
        text = ('<div class="tgme_widget_message" data-post="sample/1">'
                '<div class="tgme_widget_message_text">Nike Dunk '
                '<a href="https://c.onlyaff.app/a">Hacoo</a> '
                '<a href="https://attacker.example/collect">extra</a>'
                '</div></div>')
        def raise_for_status(self): pass
    class Session:
        def get(self, url, timeout, allow_redirects=False): return Resp()
    with pytest.raises(ValueError, match="ajenos"):
        preview_source(Session(), "sample")
