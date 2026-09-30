"""One strict Hacoo path parser, including observed production /ES/detail/."""
import re
from urllib.parse import urlsplit
from url_policy import is_hacoo_url
_PATH = re.compile(r'/(?:[A-Za-z]{2}(?:-[A-Za-z]{2})?/)?(?:detail|product|p)/([0-9]{1,15})/?')

def hacoo_product_id(url):
    if not is_hacoo_url(url):
        return ''
    match = _PATH.fullmatch(urlsplit(url).path)
    return match.group(1) if match else ''
