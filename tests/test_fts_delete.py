import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from db import DB

def test_deleted_terms_do_not_match_reused_row_id():
    db=DB(':memory:')
    db.insert_message('sourcea',1,'','Nike','');db.insert_link('sourcea',1,'https://onlyaff.app/a')
    db.conn.execute('DELETE FROM links WHERE id=1')
    db.insert_message('sourcea',2,'','Dunk','')
    db.conn.execute("INSERT INTO links(id,channel,message_id,url) VALUES(1,'sourcea',2,'https://onlyaff.app/b')")
    assert db.search_fts('Nike')==[]
    assert len(db.search_fts('Dunk'))==1

def test_delete_after_title_edit_removes_current_terms(tmp_path):
    path=str(tmp_path/'db.sqlite');db=DB(path)
    db.insert_message('sourcea',1,'','Old','');db.insert_link('sourcea',1,'https://onlyaff.app/a')
    db.insert_message('sourcea',1,'','New','')
    db.conn.execute('DELETE FROM links WHERE id=1');db.close()
    db=DB(path);db.insert_message('sourcea',2,'','Final','')
    db.conn.execute("INSERT INTO links(id,channel,message_id,url) VALUES(1,'sourcea',2,'https://onlyaff.app/b')")
    assert not db.search_fts('Old') and not db.search_fts('New')
    assert db.search_fts('Final')
