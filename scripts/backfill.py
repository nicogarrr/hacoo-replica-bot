"""Backfill profundo: recorre el historico completo de cada canal.

Uso dentro del contenedor:  python /app/scripts/backfill.py
Reanuda desde el ultimo mensaje conocido por canal; seguro relanzarlo.
"""
import sys
import time
import logging

sys.path.insert(0, "/app/bot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

from channels import crawl_channel, make_session  # noqa: E402
from db import DB  # noqa: E402
from config import Config  # noqa: E402


def main() -> None:
    cfg = Config()
    db = DB(cfg.db_path)
    session = make_session()
    for ch in cfg.channels:
        t0 = time.time()
        try:
            n = crawl_channel(session, ch, db, max_pages=400, sleep_s=1.2,
                              backfill=True)
            print(f"{ch}: +{n} enlaces en {time.time()-t0:.0f}s", flush=True)
        except Exception as e:
            print(f"{ch}: ERROR {e}", flush=True)
    print("BACKFILL COMPLETO", db.stats(), flush=True)


if __name__ == "__main__":
    main()
