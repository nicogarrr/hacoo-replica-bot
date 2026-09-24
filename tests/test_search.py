import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))

from db import DB
from search import search


def make_db(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    db.insert_message("hacoolinks", 1, "2026-09-24", "Nike Air Jordan 4 Military Black", "")
    db.insert_link("hacoolinks", 1, "https://c.onlyaff.app/a")
    db.mark_resolved(1, "https://www.hacoo.pl/detail/100", "100")
    db.insert_message("hacoolinks", 2, "2026-09-23", "Dunk Low Panda", "")
    db.insert_link("hacoolinks", 2, "https://c.onlyaff.app/b")
    db.mark_resolved(2, "https://www.hacoo.pl/detail/200", "200")
    db.insert_message("otro", 5, "2026-09-22", "Jordan 4 Military Black restock", "")
    db.insert_link("otro", 5, "https://x.sh/c")
    db.mark_resolved(3, "https://www.hacoo.pl/detail/100", "100")
    db.commit()
    return db


def test_search_groups_same_product(tmp_path):
    db = make_db(tmp_path)
    results = search(db, "Jordan 4 Military Black")
    assert len(results) == 1  # mismo product_id desde dos canales = un resultado
    assert results[0]["sources"] == 2
    assert results[0]["link"] == "https://www.hacoo.pl/detail/100"


def test_search_accents_and_case(tmp_path):
    db = make_db(tmp_path)
    assert search(db, "jordan military")
    assert search(db, "DUNK panda")
    assert not search(db, "yeezy foam")


def test_search_too_short(tmp_path):
    db = make_db(tmp_path)
    assert search(db, "a") == []


def test_progressive_relaxation(tmp_path):
    db = DB(str(tmp_path / "r.db"))
    db.insert_message("c", 1, "2026-09-24", "Ralph Lauren", "")
    db.insert_link("c", 1, "https://x.sh/rl")
    db.commit()
    # frase larga tipo vision: marca+modelo+colorway; debe caer a "ralph lauren"
    res = search(db, "Polo Ralph Lauren Court sneaker white black gum")
    assert res and "Ralph Lauren" in res[0]["title"]


def test_exact_ranks_before_relaxed(tmp_path):
    db = DB(str(tmp_path / "e.db"))
    db.insert_message("c", 1, "2026-09-24", "Jordan 4 Military Black", "")
    db.insert_link("c", 1, "https://x.sh/a")
    db.insert_message("c", 2, "2026-09-23", "Jordan 4", "")
    db.insert_link("c", 2, "https://x.sh/b")
    db.commit()
    res = search(db, "Jordan 4 Military Black")
    assert res[0]["title"] == "Jordan 4 Military Black"
