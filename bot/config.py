"""Configuracion por variables de entorno. Ningun secreto va al repo."""
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


class Config:
    def __init__(self) -> None:
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.authorized_user_ids = {
            int(x)
            for x in os.environ.get(
                "AUTHORIZED_USER_IDS", "8258546109,1484047314"
            ).split(",")
            if x.strip().isdigit()
        }
        self.channels = [
            c.strip().lstrip("@")
            for c in os.environ.get(
                "CHANNELS",
                "hacoolinks,hacoolinksvip,hacoolinks10chanel,mkfashionfinds,iammmchannel,hacooenlacesdiarios,hacoofinds,hacoooofinds",
            ).split(",")
            if c.strip()
        ]
        self.index_interval_min = _int("INDEX_INTERVAL_MIN", 60)
        self.max_pages_per_run = _int("MAX_PAGES_PER_RUN", 40)
        self.resolve_links = os.environ.get("RESOLVE_LINKS", "1") == "1"
        self.resolve_rate_per_min = _int("RESOLVE_RATE_PER_MIN", 60)
        self.db_path = os.environ.get("DB_PATH", "data/replicas.db")
        self.owner_id = 8258546109

    def validate(self) -> None:
        if not self.telegram_bot_token:
            raise SystemExit("Falta TELEGRAM_BOT_TOKEN en el entorno (.env).")
