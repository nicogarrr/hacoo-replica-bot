"""Conservative Hacoo boundary. Verify additional production hosts before adding."""
from urllib.parse import urlparse
HACOO_ROOTS = {'hacoo.app', 'hacoo.pl'}
SHORTLINK_HOSTS = {'onlyaff.app', 'c.onlyaff.app'}

def safe_product_url(url):
    if not isinstance(url, str):
        return False
    try:
        p = urlparse(url)
        host = (p.hostname or '').lower()
        return (p.scheme == 'https' and not p.username and not p.password
                and p.port in (None, 443)
                and (host in SHORTLINK_HOSTS or any(
                    host == root or host.endswith('.' + root) for root in HACOO_ROOTS)))
    except ValueError:
        return False

def is_hacoo_url(url):
    return safe_product_url(url) and (urlparse(url).hostname or '').lower() not in SHORTLINK_HOSTS
