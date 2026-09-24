"""Entrada: bot de Telegram (polling) + rastreador programado."""
import asyncio
import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from channels import crawl_channel, make_session
from config import Config
from db import DB
from handlers import make_handlers
from resolver import resolve_pending
from liveness import check_pending

logging.getLogger("httpx").setLevel(logging.WARNING)  # no filtrar token en URLs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("replica-bot")


async def indexer_loop(cfg: Config, db: DB) -> None:
    session = make_session()
    while True:
        total = 0
        for channel in cfg.channels:
            try:
                # en hilo: crawl_channel es sincrono y si no congela el
                # event loop (bot sordo durante todo el rastreo)
                total += await asyncio.to_thread(
                    crawl_channel, session, channel, db,
                    cfg.max_pages_per_run)
            except Exception:
                log.exception("rastreo de %s fallo", channel)
        log.info("rastreo: %s enlaces nuevos", total)
        if cfg.resolve_links:
            try:
                # resuelve en hueco entre rastreos, dejando 60s de margen
                budget_s = max(60.0, cfg.index_interval_min * 60 - 60)
                done = await asyncio.to_thread(
                    resolve_pending, session, db,
                    cfg.resolve_rate_per_min, budget_s)
                if done:
                    log.info("resolver: %s enlaces procesados", done)
                # liveness con presupuesto propio: ~300/ciclo, no atraganta
                checked, dead = await asyncio.to_thread(
                    check_pending, session, db,
                    cfg.resolve_rate_per_min, 600)
                if checked:
                    log.info("liveness: %s chequeados, %s muertos",
                             checked, dead)
            except Exception:
                log.exception("resolver fallo")
        await asyncio.sleep(cfg.index_interval_min * 60)


async def main() -> None:
    cfg = Config()
    import os
    if os.environ.get("INDEXER_ONLY") == "1":
        # Modo solo indice: precalienta la base sin token de Telegram.
        db = DB(cfg.db_path)
        await indexer_loop(cfg, db)
        return
    cfg.validate()
    db = DB(cfg.db_path)
    handlers = make_handlers(cfg, db)

    app = Application.builder().token(cfg.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", handlers["start"]))
    app.add_handler(CommandHandler("ayuda", handlers["ayuda"]))
    app.add_handler(CommandHandler("help", handlers["ayuda"]))
    app.add_handler(CommandHandler("stats", handlers["stats"]))
    app.add_handler(CommandHandler("canales", handlers["canales"]))
    app.add_handler(CommandHandler("buscar", handlers["buscar"]))
    app.add_handler(MessageHandler(filters.PHOTO, handlers["foto"]))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers["texto"]))

    indexer = asyncio.create_task(indexer_loop(cfg, db))
    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=False)
        # False: mensajes mandados durante un reinicio se responden
        # al volver, no se tiran
        log.info("bot en marcha")
        while True:
            await asyncio.sleep(3600)
    finally:
        indexer.cancel()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
