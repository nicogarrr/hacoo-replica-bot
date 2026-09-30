import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from channels import crawl_channel,parse_channel_page
from db import DB
from test_crawler_regressions import page

def test_gap_inside_known_min_max_not_assumed_present(monkeypatch):
    db=DB(':memory:')
    for n in [1,3]:
        db.insert_message('c',n,'','Nike','')
        db.insert_link('c',n,f'https://onlyaff.app/{n}')
    monkeypatch.setattr('channels.fetch_page',lambda *a:page([1,2,3],[1,2,3]))
    assert crawl_channel(None,'c',db,max_pages=1,sleep_s=0)==1
    assert db.stats()['links']==3
    assert crawl_channel(None,'c',db,max_pages=1,sleep_s=0)==0

def test_foreign_post_cannot_supply_source_citation_or_navigation(monkeypatch):
    db=DB(':memory:')
    html=page([1],[1]).replace('data-post="c/1"','data-post="other/1"')
    assert parse_channel_page(html,'c')==[]
    monkeypatch.setattr('channels.fetch_page',lambda *a:html)
    assert crawl_channel(None,'c',db,max_pages=4,sleep_s=0)==0
    assert db.stats()['links']==0

def test_alive_product_lookup_uses_partial_index():
    db=DB(':memory:')
    plan=db.conn.execute("EXPLAIN QUERY PLAN SELECT id FROM links WHERE product_id=? AND dead_at IS NULL",('123',)).fetchall()
    assert any('links_product_alive' in r['detail'] for r in plan)
