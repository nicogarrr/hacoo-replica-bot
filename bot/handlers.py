"""Handlers de Telegram. Interfaz en espanol."""
import asyncio
import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

from search import search
from liveness import check_one
from channels import make_session

_live_session = None


def _get_session():
    global _live_session
    if _live_session is None:
        _live_session = make_session()
    return _live_session
from vision import identify_from_photo

log = logging.getLogger(__name__)

HELP = (
    "Busco replicas en Hacoo usando lo que publica la comunidad.\n\n"
    "Escribeme el modelo tal cual y te mando los enlaces:\n"
    "  Jordan 4 Military Black\n"
    "  Dunk Low Panda\n"
    "  Trapstar chandal\n\n"
    "Comandos:\n"
    "/buscar <modelo> - buscar\n"
    "/stats - estado del indice\n"
    "/canales - canales que indexo\n"
    "/ayuda - esta ayuda\n\n"
    "Tambien puedes mandarme una FOTO del modelo y lo identifico yo.\n\n"
    "Importante: el enlace va al producto; la talla se elige dentro de Hacoo "
    "al comprar."
)


def _authorized(update: Update, allowed: set) -> bool:
    user = update.effective_user
    return bool(user and user.id in allowed)


async def _deny(update: Update) -> None:
    await update.message.reply_text(
        "Este bot es privado. Pide acceso a su dueño.")


def make_handlers(cfg, db):
    async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not _authorized(update, cfg.authorized_user_ids):
            await _deny(update)
            return
        await update.message.reply_text(
            "Mandame el modelo de la zapa o prenda y te busco el enlace de "
            "Hacoo mas reciente de la comunidad.\n\n" + HELP)

    async def ayuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not _authorized(update, cfg.authorized_user_ids):
            await _deny(update)
            return
        await update.message.reply_text(HELP)

    async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not _authorized(update, cfg.authorized_user_ids):
            await _deny(update)
            return
        s = db.stats()
        await update.message.reply_text(
            f"Mensajes indexados: {s['msgs']}\n"
            f"Enlaces: {s['links']} ({s['resolved']} resueltos a Hacoo)\n"
            f"Canales: {s['channels']}")

    async def canales(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not _authorized(update, cfg.authorized_user_ids):
            await _deny(update)
            return
        await update.message.reply_text(
            "Indexando:\n" + "\n".join(f"- @{c}" for c in cfg.channels))

    async def buscar(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not _authorized(update, cfg.authorized_user_ids):
            await _deny(update)
            return
        query = " ".join(ctx.args) if ctx.args else (update.message.text or "")
        if update.message.text and update.message.text.startswith("/buscar"):
            query = " ".join(ctx.args)
        query = query.strip()
        if len(query) < 3:
            await update.message.reply_text(
                "Dime el modelo, por ejemplo: Jordan 4 Military Black")
            return
        found = search(db, query, limit=5)
        results = found["results"]
        if not results:
            await update.message.reply_text(
                "No tengo nada para eso todavia. Prueba con el nombre en "
                "ingles (Jordan 4, Dunk Panda...) o mas corto.")
            return
        if not found["exact"] and found["model"]:
            lines = [
                f"La <b>{html.escape(found['model'])}</b> exacta no esta en el indice.\n"
                "Lo mas parecido:\n"]
        else:
            lines = [f"Resultados para <b>{html.escape(query)}</b>:\n"]
        # chequeo en vivo de enlaces viejos (>25 dias): el shortlink 404
        # = muerto, se marca y se oculta antes de ensenarlo
        alive = []
        for r in results:
            if r.get("stale"):
                dead = await asyncio.to_thread(
                    check_one, _get_session(), r["orig_url"])
                db.mark_checked(r["id"], dead)
                if dead:
                    continue
            alive.append(r)
        results = alive
        if not results:
            await update.message.reply_text(
                "Lo que tenia para eso son enlaces viejos y ya estan "
                "muertos (los de Hacoo duran ~1 mes). Cuando un canal "
                "publique uno nuevo saldra aqui.")
            return
        for i, r in enumerate(results, 1):
            extra = f" (+{r['sources']-1} fuentes)" if r["sources"] > 1 else ""
            date = f" · {r['posted_at']}" if r["posted_at"] else ""
            warn = " ⚠️ viejo" if r.get("stale") else ""
            lines.append(
                f"{i}. {html.escape(r['title'])}{extra}{date}{warn}\n"
                f"<a href=\"{html.escape(r['link'])}\">Abrir en Hacoo</a>")
        lines.append("\nLa talla se elige dentro de Hacoo al comprar.")
        await update.message.reply_text(
            "\n".join(lines), parse_mode="HTML",
            disable_web_page_preview=True)

    async def texto(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        ctx.args = (update.message.text or "").split()
        await buscar(update, ctx)

    async def foto(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not _authorized(update, cfg.authorized_user_ids):
            await _deny(update)
            return
        if not cfg.opencode_go_api_key:
            await update.message.reply_text(
                "Las fotos aun no estan activas. Mandame el nombre del "
                "modelo (por ejemplo: Jordan 4 Military Black).")
            return
        try:
            photo = update.message.photo[-1]
            tg_file = await photo.get_file()
            image = bytes(await tg_file.download_as_bytearray())
        except Exception:
            log.exception("descarga de foto fallo")
            await update.message.reply_text(
                "No pude bajar la foto. Prueba otra vez o mandame el "
                "nombre del modelo.")
            return
        await update.message.reply_text("Analizando la foto...")
        phrase = await asyncio.to_thread(
            identify_from_photo, image, cfg.opencode_go_api_key,
            cfg.opencode_go_base_url, cfg.vision_model,
            cfg.opencode_go_session)
        if not phrase:
            await update.message.reply_text(
                "No saque el modelo de la foto. Mandame el nombre "
                "(por ejemplo: Jordan 4 Military Black) y lo busco.")
            return
        await update.message.reply_text(f"Veo: {phrase}. Buscando...")
        ctx.args = phrase.split()
        await buscar(update, ctx)

    return {
        "start": start, "ayuda": ayuda, "stats": stats,
        "canales": canales, "buscar": buscar, "texto": texto, "foto": foto,
    }
