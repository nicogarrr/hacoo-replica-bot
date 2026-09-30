"""Prefer confirmed product links over uncertain warnings within one budget."""
from search import query_tokens
from link_health import choose_link
from url_policy import safe_product_url

def verify_results(session,db,rows,checker,product_links,budget,deadline,limit=5):
    alive, uncertain, seen = [], [], set()
    for row in rows:
        if not safe_product_url(row['orig_url']):
            continue
        checked=choose_link(session,db,row,checker,
                            product_links.for_result(row),budget,deadline)
        if not checked:
            continue
        key=checked.get('product_id') or checked['orig_url']
        if key in seen:
            continue
        seen.add(key)
        (alive if checked['link'] else uncertain).append(checked)
        if len(alive)>=limit:
            break
    return (alive+uncertain)[:limit]

def confirmed_model_present(results,model):
    terms={t.lower() for t in query_tokens(model)}
    return bool(terms) and any(r['link'] and terms <= {
        t.lower() for t in query_tokens(r['title'])} for r in results)
