import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from db import DB
from search import search
from channels import crawl_channel

def test_post_edit_replaces_fts_terms_without_duplicate_links():
    db=DB(':memory:')
    db.insert_message('sourcea',1,'2099-01-01','Jordan 1','old')
    db.insert_link('sourcea',1,'https://onlyaff.app/a')
    assert db.search_fts('Jordan 1')
    db.insert_message('sourcea',1,'2099-01-01','Nike Dunk Panda','edited')
    assert not db.search_fts('Jordan')
    assert db.search_fts('Dunk Panda')
    assert db.stats()['links']==1
    db.insert_message('sourcea',1,'2099-01-01','Nike Dunk Panda','edited')
    assert len(db.search_fts('Panda'))==1
    assert db.conn.execute('SELECT raw_text FROM messages').fetchone()[0]=='edited'

def test_repeated_edits_update_all_link_fts_rows():
    db=DB(':memory:');db.insert_message('sourcea',1,'','Old','')
    for i in range(3):db.insert_link('sourcea',1,f'https://onlyaff.app/{i}')
    for title in ['First','Second','Final']:
        db.insert_message('sourcea',1,'',title,'')
        assert len(db.search_fts(title))==3
    assert not db.search_fts('First')

def test_crawler_refreshes_edited_existing_post(monkeypatch):
    db=DB(':memory:');db.insert_message('sourcea',1,'','Old Jordan','')
    db.insert_link('sourcea',1,'https://onlyaff.app/a')
    html='<div class="tgme_widget_message" data-post="sourcea/1"><div class="tgme_widget_message_text">Nike Dunk <a href="https://onlyaff.app/a">link</a></div></div>'
    monkeypatch.setattr('channels.fetch_page',lambda *a:html)
    assert crawl_channel(None,'sourcea',db,max_pages=1,sleep_s=0)==0
    assert db.search_fts('Dunk') and not db.search_fts('Jordan')
