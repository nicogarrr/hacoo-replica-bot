"""One output boundary for product links; affiliate mappings are opt-in.

Affiliate mappings must be generated and verified in Hacoo's dashboard first.
Never fabricate them by modifying a /detail/<id> URL or guessing parameters.
"""
import json
import logging
from pathlib import Path
from url_policy import safe_product_url

log = logging.getLogger(__name__)


class ProductLinks:
    def __init__(self, mapping_file: str = ""):
        self.mapping = {}
        if not mapping_file:
            return
        try:
            rows = json.loads(Path(mapping_file).read_text(encoding="utf-8"))
            if not isinstance(rows, dict):
                raise ValueError("expected {product_id: verified_url}")
            for pid, link in rows.items():
                if isinstance(pid, str) and pid.isdecimal() and safe_product_url(link):
                    self.mapping[str(pid)] = link
                else:
                    raise ValueError("invalid product ID or URL")
        except (OSError, ValueError, TypeError):
            log.exception("Affiliate mapping invalid; direct product links only")
            self.mapping = {}

    def for_result(self, row: dict) -> str:
        pid = str(row.get("product_id") or "")
        # The stored URL is the resolved product URL where available; do not
        # manufacture an unverified /detail URL from a product ID.
        link = self.mapping.get(pid, row["link"])
        return link if safe_product_url(link) else ""
