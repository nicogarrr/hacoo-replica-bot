import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bot'))
from db import DB
from search import search, categorize

def add(db, n, title, url=None, pid=None):
    db.insert_message('c', n, '2099-01-01', title, '')
    db.insert_link('c', n, url or f'https://c.onlyaff.app/{n}')
    if pid:
        db.mark_resolved(n, f'https://hacoo.app/detail/{pid}', pid)

def test_h1_jordan_four_exact_first():
    db = DB(':memory:')
    add(db, 1, 'Jordan 4 Military Black')
    add(db, 2, 'Jordan 1 Military Black')
    add(db, 3, 'Jordan 4 hoodie Military Black')
    r = search(db, 'Jordan 4 Military Black')
    assert r['exact'] is True
    assert r['results'][0]['title'] == 'Jordan 4 Military Black'
    assert '4' in r['model']
    assert not any('hoodie' in x['title'] for x in r['results'])
    assert search(db, 'Jordan (4) Military Black')['exact'] is True

def test_h5_brand_clothes_and_mixed_types():
    assert categorize('Jordan hoodie') == 'apparel'
    assert categorize('Jordan cap') == 'apparel'
    assert categorize('Jordan sneakers') == 'footwear'
    db = DB(':memory:')
    add(db, 1, 'Jordan sneakers hoodie')
    add(db, 2, 'Jordan hoodie')
    add(db, 3, 'Jordan sneakers')
    assert [r['title'] for r in search(db, 'Jordan hoodie')['results']] == ['Jordan hoodie']

def test_h7_numeric_id_and_exact_token_not_substring():
    db = DB(':memory:')
    add(db, 1, 'Jordan 14 Military Black', pid='987654')
    assert search(db, '987654')['results'][0]['product_id'] == '987654'
    assert search(db, '987654')['exact'] is True
    assert search(db, '987655')['results'] == []
    assert search(db, 'Jordan 4 Military Black')['exact'] is False

def test_h8_quotes_punctuation_unicode():
    db = DB(':memory:')
    add(db, 1, 'Nike Dunk café')
    for q in ['Nike "Dunk', 'Nike Dunk"', 'Nike (Dunk)', 'Nike-Dunk', 'Nike Dunk café']:
        assert search(db, q)['results']
    assert db.search_fts_with_any(['Nike"'], ['Dunk"'])

def test_h9_fragment_dedup_not_query_or_title():
    db = DB(':memory:')
    add(db, 1, 'Nike Dunk', 'https://c.onlyaff.app/a#one')
    add(db, 2, 'Nike Dunk', 'https://C.ONLYAFF.APP/a#two')
    add(db, 3, 'Nike Dunk', 'https://c.onlyaff.app/a?signature=x')
    r = search(db, 'Nike Dunk')['results']
    assert len(r) == 2
    assert all(x['sources'] == 1 for x in r) # distinct channels, not rows

def test_rapidfuzz_typos_and_numeric_guard():
    db = DB(':memory:')
    add(db, 1, 'Jordan 4 Military Black')
    add(db, 2, 'Jordan 14 Military Black')
    r = search(db, 'Jordna 4 Militry Black')
    assert r['results'][0]['title'] == 'Jordan 4 Military Black'
    assert r['exact'] is False
    assert search(db, 'Jordna 3 Militry Black')['exact'] is False
