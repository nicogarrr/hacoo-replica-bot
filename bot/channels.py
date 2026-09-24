"""Rastreo de la vista web publica de canales de Telegram (t.me/s/<canal>).

Sin API ni login: la vista previa publica devuelve 20 mensajes por pagina,
paginados hacia atras con ?before=<message_id>. Solo lectura, ritmo suave.
"""
import logging
import re
import time
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE = "https://t.me/s/{channel}"
LINK_RE = re.compile(r"https?://[^\s<>\"']+")


@dataclass
class ChannelMessage:
    channel: str
    message_id: int
    posted_at: str
    title: str
    raw_text: str
    links: list = field(default_factory=list)


def parse_channel_page(html: str, channel: str) -> list:
    """Extrae mensajes con al menos un enlace de una pagina t.me/s/."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for div in soup.select("div.tgme_widget_message"):
        post = div.get("data-post", "")
        m = re.match(r"([^/]+)/(\d+)$", post)
        if not m:
            continue
        msg_id = int(m.group(2))
        text_el = div.select_one(".tgme_widget_message_text")
        raw = text_el.get_text(" ", strip=True) if text_el else ""
        time_el = div.select_one("time[datetime]")
        posted_at = time_el["datetime"] if time_el else ""
        links = []
        if text_el:
            for a in text_el.select("a[href]"):
                href = a["href"]
                if href.startswith("http") and "t.me" not in href:
                    links.append(href)
        if not links:
            links = [u for u in LINK_RE.findall(raw) if "t.me" not in u]
        if not links:
            continue
        title = LINK_RE.sub("", raw)
        for a in (text_el.select("a[href]") if text_el else []):
            if a.get("href", "").startswith("http"):
                title = title.replace(a.get_text(), " ")
        title = re.sub(r"\s+", " ", title).strip(" -–—\n")
        out.append(ChannelMessage(channel, msg_id, posted_at, title, raw, links))
    return out


def fetch_page(session: requests.Session, channel: str, before: int = 0) -> str:
    url = BASE.format(channel=channel)
    if before:
        url += f"?before={before}"
    r = session.get(url, timeout=20)
    r.raise_for_status()
    return r.text


def crawl_channel(session: requests.Session, channel: str, db,
                  max_pages: int = 40, sleep_s: float = 2.0) -> int:
    """Rastreo incremental: retrocede hasta alcanzar mensajes ya conocidos."""
    known_max = db.max_message_id(channel)
    before = 0
    new_count = 0
    for page in range(max_pages):
        try:
            html = fetch_page(session, channel, before)
        except Exception as e:
            log.warning("canal %s pagina %s: %s", channel, page, e)
            break
        msgs = parse_channel_page(html, channel)
        if not msgs:
            break
        oldest_in_page = None
        for msg in msgs:
            if msg.message_id <= known_max:
                continue
            db.insert_message(msg.channel, msg.message_id, msg.posted_at,
                              msg.title, msg.raw_text)
            for link in msg.links:
                db.insert_link(msg.channel, msg.message_id, link)
                new_count += 1
        db.commit()
        ids = [m.message_id for m in msgs]
        oldest_in_page = min(ids)
        if oldest_in_page <= known_max or len(msgs) < 5:
            break
        before = oldest_in_page
        time.sleep(sleep_s)
    return new_count


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"})
    return s
