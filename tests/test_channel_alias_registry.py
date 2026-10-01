import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from db import DB

def test_case_aliases_crawl_once_keep_first_spelling():
    db=DB(':memory:')
    db.conn.execute("INSERT INTO extra_channels VALUES('sourcea',1)")
    db.conn.execute("INSERT INTO extra_channels VALUES('SOURCEB',2)")
    assert db.channels(['SourceA','sourceA','sourceb'])==['SourceA','sourceb']
    assert db.conn.execute('SELECT COUNT(*) FROM extra_channels').fetchone()[0]==2
    assert db.add_channel('sourcea',['SourceA']) is False

def test_aliases_do_not_consume_registration_cap():
    db=DB(':memory:')
    defaults=[f'source{i}' for i in range(34)]+['SOURCE0']
    assert db.add_channel('newsource',defaults)
    assert len(db.channels(defaults))==35
