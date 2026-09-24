import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))

import vision


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_identify_ok(monkeypatch):
    payload = {"choices": [{"message": {"content": " Jordan 4 Military Black. "}}]}
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=0: FakeResponse(payload))
    out = vision.identify_from_photo(b"\xff\xd8img", "k", "http://x/v1", "m", "s")
    assert out == "Jordan 4 Military Black"


def test_identify_error_returns_empty(monkeypatch):
    def boom(req, timeout=0):
        raise OSError("red caida")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert vision.identify_from_photo(b"x", "k", "http://x/v1", "m", "s") == ""


def test_identify_empty_content(monkeypatch):
    payload = {"choices": [{"message": {"content": ""}}]}
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=0: FakeResponse(payload))
    assert vision.identify_from_photo(b"x", "k", "http://x/v1", "m", "s") == ""
