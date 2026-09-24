import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))

from db import DB
from search import search, clean_title, categorize


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
    res = search(db, "Jordan 4 Military Black")
    assert len(res["results"]) == 1  # mismo product_id desde dos canales
    assert res["results"][0]["sources"] == 2
    assert res["results"][0]["link"] == "https://www.hacoo.pl/detail/100"


def test_search_accents_and_case(tmp_path):
    db = make_db(tmp_path)
    assert search(db, "jordan military")["results"]
    assert search(db, "DUNK panda")["results"]
    assert not search(db, "yeezy foam")["results"]


def test_search_too_short(tmp_path):
    db = make_db(tmp_path)
    assert search(db, "a")["results"] == []


def test_progressive_relaxation(tmp_path):
    db = DB(str(tmp_path / "r.db"))
    db.insert_message("c", 1, "2026-09-24", "Zapatillas Ralph Lauren Heritage", "")
    db.insert_link("c", 1, "https://x.sh/rl")
    db.commit()
    # frase larga tipo vision: marca+modelo+tipo+colorway
    res = search(db, "Polo Ralph Lauren Court sneaker white black gum")
    assert res["results"] and "Ralph Lauren" in res["results"][0]["title"]


def test_exact_ranks_before_relaxed(tmp_path):
    db = DB(str(tmp_path / "e.db"))
    db.insert_message("c", 1, "2026-09-24", "Jordan 4 Military Black", "")
    db.insert_link("c", 1, "https://x.sh/a")
    db.insert_message("c", 2, "2026-09-23", "Jordan 4", "")
    db.insert_link("c", 2, "https://x.sh/b")
    db.commit()
    res = search(db, "Jordan 4 Military Black")
    assert res["results"][0]["title"] == "Jordan 4 Military Black"
    assert res["exact"] is True


def test_footwear_query_never_returns_apparel(tmp_path):
    db = DB(str(tmp_path / "g.db"))
    db.insert_message("c", 1, "2026-09-24", "Ralph Lauren sweater women", "")
    db.insert_link("c", 1, "https://x.sh/jersey")
    db.insert_message("c", 2, "2026-09-23", "Zapatillas Ralph Lauren Heritage", "")
    db.insert_link("c", 2, "https://x.sh/heri")
    db.commit()
    res = search(db, "Polo Ralph Lauren Bedford sneakers white")
    titles = [r["title"] for r in res["results"]]
    assert any("Heritage" in t for t in titles)
    assert not any("sweater" in t.lower() for t in titles)


def test_exact_false_when_model_absent(tmp_path):
    db = DB(str(tmp_path / "h.db"))
    db.insert_message("c", 1, "2026-09-24", "Zapatillas Ralph Lauren Heritage", "")
    db.insert_link("c", 1, "https://x.sh/heri")
    db.commit()
    res = search(db, "Polo Ralph Lauren Bedford sneakers")
    assert res["exact"] is False
    assert res["model"] == "Bedford"


def test_exact_true_when_model_present(tmp_path):
    db = DB(str(tmp_path / "i.db"))
    db.insert_message("c", 1, "2026-09-24", "Polo Ralph Lauren Bedford white", "")
    db.insert_link("c", 1, "https://x.sh/bed")
    db.commit()
    res = search(db, "Polo Ralph Lauren Bedford sneakers white")
    assert res["exact"] is True


def test_clean_title_strips_emoji_and_link_junk():
    assert clean_title("Zapatillas Ralph Lauren Heritage 👔 Link: Link: (Varios colores)") == \
        "Zapatillas Ralph Lauren Heritage (Varios colores)"
    assert clean_title("Polo Ralph Lauren 👶👶") == "Polo Ralph Lauren"
    assert clean_title("") == "(sin titulo)"


def test_categorize():
    assert categorize("Nike Dunk Low Panda") == "footwear"
    assert categorize("sudadera trapstar negra") == "apparel"
    assert categorize("bolso goyard tote") == "accessory"
    assert categorize("Ralph Lauren") == ""
