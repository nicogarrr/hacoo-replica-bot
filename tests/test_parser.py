import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))

from channels import parse_channel_page


def test_parse_real_structure():
    html = open(os.path.join(os.path.dirname(__file__), "fixture_channel.html"),
                encoding="utf8").read()
    msgs = parse_channel_page(html, "hacoolinks")
    assert len(msgs) == 2  # el mensaje sin enlace se ignora
    first = msgs[0]
    assert first.message_id == 79435
    assert "Jordan 4" in first.title
    assert "http" not in first.title
    assert first.links == ["https://c.onlyaff.app/cpM9Dq"]
    assert first.posted_at.startswith("2026-09-24")
    second = msgs[1]
    assert second.title == "Dunk Low Panda"
