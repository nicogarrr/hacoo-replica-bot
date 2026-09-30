import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from db import DB
from config import Config
from channels import crawl_channel
from marketplace_links import normalize_marketplace_link

@pytest.mark.parametrize('name,value', [('INDEX_INTERVAL_MIN','0'),('INDEX_INTERVAL_MIN','-1'),('INDEX_INTERVAL_MIN','1441'),('MAX_PAGES_PER_RUN','0'),('MAX_PAGES_PER_RUN','401'),('RESOLVE_RATE_PER_MIN','0'),('RESOLVE_RATE_PER_MIN','121')])
def test_config_invalid_operational_bounds(monkeypatch,name,value):
    monkeypatch.setenv(name,value)
    with pytest.raises(SystemExit,match='Configuración inválida'):
        Config().validate(require_token=False)

def test_indexer_no_token_ok_bot_no_token_fails(monkeypatch):
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN',raising=False)
    cfg=Config();cfg.validate(require_token=False)
    with pytest.raises(SystemExit,match='Falta TELEGRAM'):
        cfg.validate()
    cfg.db_path=' '
    with pytest.raises(SystemExit,match='DB_PATH'):
        cfg.validate(require_token=False)

def test_nested_db_directory_and_memory(tmp_path):
    db=DB(str(tmp_path/'nested'/'data'/'db.sqlite'))
    assert db.stats()['links']==0
    db.close()
    assert DB(':memory:').stats()['links']==0

def test_duplicate_link_returns_zero_and_crawl_counts_insertions(monkeypatch):
    db=DB(':memory:')
    db.insert_message('sourcea',1,'','Nike','')
    assert db.insert_link('sourcea',1,'https://onlyaff.app/a')==1
    assert db.insert_link('sourcea',1,'https://onlyaff.app/a')==0
    # Duplicate links in same new post must not inflate cycle metrics.
    page='<div class="tgme_widget_message" data-post="sourcea/2"><div class="tgme_widget_message_text">Nike <a href="https://onlyaff.app/b">b</a><a href="https://onlyaff.app/b">b</a></div></div>'
    monkeypatch.setattr('channels.fetch_page',lambda *a:page)
    assert crawl_channel(None,'sourcea',db,max_pages=1,sleep_s=0)==1

def test_tmall_identity_and_canonical_host_preserved():
    r=normalize_marketplace_link('https://detail.tmall.com/item.htm?id=123')
    assert r['marketplace']=='tmall'
    assert r['canonical_url']=='https://detail.tmall.com/item.htm?id=123'
    assert normalize_marketplace_link(r['canonical_url'])==r
