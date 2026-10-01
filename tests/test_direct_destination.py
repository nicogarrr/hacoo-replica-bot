import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bot'))
from direct_product_url import canonical_observed_product
from product_links import ProductLinks
from link_health import LinkHealth,choose_link
from test_product_state import Resp,Session,FIX
from db import DB

def test_canonical_observed_route_no_invented_id_path_or_tag():
    assert canonical_observed_product('https://www.hacoo.pl/ES/detail/40800048?tag=other#x','40800048')=='https://www.hacoo.pl/ES/detail/40800048?tag=other'
    assert canonical_observed_product('https://onlyaff.app/40800048','40800048')==''
    assert canonical_observed_product('https://hacoo.app/detail/1','2')==''

def test_reserved_tag_never_invented_or_added_mapping_preserved(tmp_path):
    row={'product_id':'123','link':'https://hacoo.app/detail/123?tag=other'}
    assert ProductLinks(affiliate_tag='my-tag').for_result(row)=='https://hacoo.app/detail/123?tag=other'
    f=tmp_path/'map.json';f.write_text('{"123":"https://onlyaff.app/verified?tag=mine"}')
    assert ProductLinks(str(f),'my-tag').for_result(row)=='https://onlyaff.app/verified?tag=mine'

def test_observed_redirect_web_inconclusive_outputs_direct_not_telegram():
    db=DB(':memory:');u='https://onlyaff.app/a'
    db.insert_message('sourcea',1,'','shoe','');db.insert_link('sourcea',1,u)
    row=dict(db.fuzzy_candidates()[0])
    s=Session([Resp(status=302,location='https://www.hacoo.pl/p/40800048?tag=source'),Resp(),Resp((FIX/'40800048.html').read_text())])
    c=choose_link(s,db,row,LinkHealth())
    assert c['link']=='https://www.hacoo.pl/p/40800048?tag=source'
    assert c['verified'] is False and 'Sin verificar' in c['health']

def test_unresolved_unknown_keeps_real_shortlink_not_synthetic_detail():
    db=DB(':memory:');u='https://onlyaff.app/a'
    db.insert_message('sourcea',1,'','shoe','');db.insert_link('sourcea',1,u)
    row=dict(db.fuzzy_candidates()[0])
    c=choose_link(Session([Resp()]),db,row,LinkHealth())
    assert c['link']==u and not c['direct']

def test_verified_pipeline_shortlink_is_not_affiliate_mapping():
    from verified_results import verify_results
    import time
    db=DB(':memory:');u='https://onlyaff.app/a'
    db.insert_message('sourcea',1,'','shoe','');db.insert_link('sourcea',1,u)
    row=dict(db.fuzzy_candidates()[0])
    s=Session([Resp(status=302,location='https://hacoo.app/detail/40302592'),Resp(),Resp((FIX/'40302592.html').read_text())])
    result=verify_results(s,db,[row],LinkHealth(),ProductLinks(),[8],time.monotonic()+8)
    assert result[0]['link']=='https://hacoo.app/detail/40302592'
    assert result[0]['verified']
