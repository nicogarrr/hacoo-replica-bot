import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))

from resolver import extract_product_id, is_hacoo_url


def test_product_id():
    assert extract_product_id("https://www.hacoo.pl/detail/40777036?f=x") == "40777036"
    assert extract_product_id("https://www.hacoo.app/detail/12") == "12"
    assert extract_product_id("https://c.onlyaff.app/cpM9Dq") == ""


def test_hacoo_host():
    assert is_hacoo_url("https://www.hacoo.pl/detail/40777036")
    assert is_hacoo_url("https://hacoo.app/x")
    assert not is_hacoo_url("https://c.onlyaff.app/abc")
    assert not is_hacoo_url("https://hacoo.pl.evil.com/detail/1")
