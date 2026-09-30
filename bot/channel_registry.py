"""Owner-only, public Telegram source registration with bounded validation."""
import re
from urllib.parse import urlparse

from channels import fetch_page, parse_channel_page
from resolver import is_hacoo_url

_USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
_SHORTLINK_HOSTS = {"onlyaff.app", "c.onlyaff.app"}


def normalize_source(value: str) -> str:
    """Accept only canonical public-channel usernames and t.me/s URLs."""
    value = value.strip()
    if value.startswith("@"):
        value = value[1:]
    elif value.startswith("https://"):
        url = urlparse(value)
        if (url.hostname not in ("t.me", "www.t.me") or url.port
                or url.username or url.password or url.query or url.fragment
                or not url.path.startswith("/s/")):
            raise ValueError("Solo enlaces públicos https://t.me/s/usuario.")
        value = url.path.removeprefix("/s/")
    if not _USERNAME.fullmatch(value):
        raise ValueError("Usa un nombre público de canal o https://t.me/s/usuario.")
    return value.lower()


def _product_candidate(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (parsed.scheme == "https" and parsed.hostname is not None
                and (is_hacoo_url(url) or parsed.hostname in _SHORTLINK_HOSTS))
    except ValueError:
        return False


def preview_source(session, username: str) -> dict:
    """One page, never crawl user-supplied URLs. Reject empty/non-product feeds."""
    messages = parse_channel_page(fetch_page(session, username), username)
    all_links = [link for m in messages for link in m.links]
    valid = [link for link in all_links if _product_candidate(link)]
    if not valid:
        raise ValueError("La vista pública no muestra enlaces Hacoo/onlyaff reconocibles.")
    # The existing crawler stores all outbound hrefs, so never register a
    # new feed that would let arbitrary third-party links reach subscribers.
    if len(valid) != len(all_links):
        raise ValueError("Hay enlaces ajenos o no seguros; revisa el canal a mano.")
    return {"messages_with_links": len(messages), "candidate_links": len(valid)}
