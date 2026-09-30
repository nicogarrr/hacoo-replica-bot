"""Entrada: bot de Telegram (polling) + rastreador programado."""
import asyncio
import logging
from contextlib import suppress
from worker import drain_worker

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
    try:
        while True:
            total = 0
            # New owner-approved sources appear on the next cycle, no restart.
            for channel in db.channels(cfg.channels):
                try:
                    # en hilo: crawl_channel es sincrono y si no congela el
                    # event loop (bot sordo durante todo el rastreo)
                    total += await drain_worker(
                        crawl_channel, session, channel, db,
                        cfg.max_pages_per_run)
                except Exception:
                    log.exception("rastreo de %s fallo", channel)
            log.info("rastreo: %s enlaces nuevos", total)
            if cfg.resolve_links:
                try:
                    # resuelve en hueco entre rastreos, dejando 60s de margen
                    budget_s = max(60.0, cfg.index_interval_min * 60 - 60)
                    done = await drain_worker(
                        resolve_pending, session, db,
                        cfg.resolve_rate_per_min, budget_s)
                    if done:
                        log.info("resolver: %s enlaces procesados", done)
                    # liveness con presupuesto propio: ~300/ciclo, no atraganta
                    checked, dead = await drain_worker(
                        check_pending, session, db,
                        cfg.resolve_rate_per_min, 600)
                    if checked:
                        log.info("liveness: %s chequeados, %s muertos",
                                 checked, dead)
                except Exception:
                    log.exception("resolver fallo")
            await asyncio.sleep(cfg.index_interval_min * 60)
    finally:
        session.close()


async def main() -> None:
    cfg = Config()
    import os
    indexer_only = os.environ.get("INDEXER_ONLY") == "1"
    cfg.validate(require_token=not indexer_only)
    if indexer_only:
        # Modo solo indice: precalienta la base sin token de Telegram.
        db = DB(cfg.db_path)
        try:
            await indexer_loop(cfg, db)
        finally:
            db.close()
        return
    db = DB(cfg.db_path)
    handlers = make_handlers(cfg, db)

    app = Application.builder().token(cfg.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", handlers["start"]))
    app.add_handler(CommandHandler("ayuda", handlers["ayuda"]))
    app.add_handler(CommandHandler("help", handlers["ayuda"]))
    app.add_handler(CommandHandler("stats", handlers["stats"]))
    app.add_handler(CommandHandler("tendencias", handlers["tendencias"]))
    app.add_handler(CommandHandler("canales", handlers["canales"]))
    app.add_handler(CommandHandler("agregarcanal", handlers["agregarcanal"]))
    app.add_handler(CommandHandler("buscar", handlers["buscar"]))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handlers["foto"]))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, handlers["texto"]))

    indexer = None
    initialized = started = polling = False
    try:
        await app.initialize()
        initialized = True
        await app.start()
        started = True
        await app.updater.start_polling(drop_pending_updates=False)
        polling = True
        indexer = asyncio.create_task(indexer_loop(cfg, db))
        # False: mensajes mandados durante un reinicio se responden
        # al volver, no se tiran
        log.info("bot en marcha")
        while True:
            await asyncio.sleep(3600)
    finally:
        if indexer is not None:
            indexer.cancel()
            with suppress(asyncio.CancelledError):
                await indexer
        try:
            if polling:
                await app.updater.stop()
            if started:
                await app.stop()
        finally:
            try:
                if initialized:
                    await app.shutdown()
            finally:
                db.close()


if __name__ == "__main__":
    asyncio.run(main())
