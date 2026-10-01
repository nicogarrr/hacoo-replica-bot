"""Direct observed Hacoo destination, never synthetic ID-to-URL or affiliate tag."""
from urllib.parse import urlsplit,urlunsplit
from product_identity import hacoo_product_id

def canonical_observed_product(url,expected_id=''):
    pid=hacoo_product_id(url)
    if not pid or (expected_id and pid != str(expected_id)):
        return ''
    p=urlsplit(url)
    # Preserve query: without documented semantics it may be signed/functional.
    # Never replace another attribution with an invented own tag.
    return urlunsplit(('https',p.netloc.lower(),p.path,p.query,''))
