"""Configuracion por variables de entorno. Ningun secreto va al repo."""
import os
from source_name import public_source_name


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
                "hacoolinks,hacoolinksvip,hacoolinks10chanel,mkfashionfinds,iammmchannel,hacooenlacesdiarios,hacoofinds,hacoooofinds,LINKS_HACOO_ESP,hacooenlances,hacoospainn,only_hacoo,linkshacoo2,enlaceshacoolinks,enlaces_hacoo,hacoobuys,hacoolinksbladefinds",
            ).split(",")
            if c.strip()
        ]
        self.index_interval_min = _int("INDEX_INTERVAL_MIN", 60)
        self.max_pages_per_run = _int("MAX_PAGES_PER_RUN", 40)
        self.resolve_links = os.environ.get("RESOLVE_LINKS", "1") == "1"
        self.resolve_rate_per_min = _int("RESOLVE_RATE_PER_MIN", 30)
        self.db_path = os.environ.get("DB_PATH", "data/replicas.db")
        self.owner_id = 8258546109
        # Closed by default. Numeric ID must come from Telegram getChat or a
        # channel_post update, not from an invite URL or an assumed username.
        self.public_search_enabled = os.environ.get("PUBLIC_SEARCH_ENABLED", "0") == "1"
        self.public_channel_id = _int("PUBLIC_CHANNEL_ID", 0)
        self.affiliate_mapping_file = os.environ.get("AFFILIATE_MAPPING_FILE", "")
        self.opencode_go_api_key = os.environ.get("OPENCODE_GO_API_KEY", "").strip()
        self.opencode_go_base_url = os.environ.get(
            "OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1")
        self.vision_model = os.environ.get(
            "VISION_MODEL", "deepseek-v4-flash-vision-exp")
        self.opencode_go_session = os.environ.get(
            "OPENCODE_GO_SESSION", "hacoo-replica-bot")

    def validate(self, require_token=True) -> None:
        for name, low, high in (("index_interval_min", 1, 1440),
                                ("max_pages_per_run", 1, 400),
                                ("resolve_rate_per_min", 1, 120)):
            if not low <= getattr(self, name) <= high:
                raise SystemExit(f"Configuración inválida: {name} debe estar entre {low} y {high}.")
        try:
            for channel in self.channels:
                public_source_name(channel)
        except ValueError as exc:
            raise SystemExit("CHANNELS contiene un nombre inválido; usa solo usernames públicos.") from exc
        if not self.db_path.strip():
            raise SystemExit("DB_PATH no puede estar vacío.")
        if require_token and not self.telegram_bot_token:
            raise SystemExit("Falta TELEGRAM_BOT_TOKEN en el entorno (.env).")
