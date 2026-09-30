"""Handlers de Telegram. Interfaz en espanol."""
import asyncio
import html
import logging
import sqlite3
from url_policy import safe_product_url

from telegram import Update
from telegram.ext import ContextTypes

from search import search
from channel_access import SubscriberGate
from product_links import ProductLinks
from liveness import check_one
from channels import make_session
from channel_registry import normalize_source, preview_source

_live_session = None


def _get_session():
    global _live_session
    if _live_session is None:
        _live_session = make_session()
    return _live_session
from trends import trends, format_offer
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
    "/canales - fuentes y métricas\n"
    "/agregarcanal <usuario o https://t.me/s/usuario> - añadir fuente pública\n"
    "/ayuda - esta ayuda\n\n"
    "Tambien puedes mandarme una FOTO del modelo y lo identifico yo.\n\n"
    "Importante: el enlace va al producto; la talla se elige dentro de Hacoo "
    "al comprar."
)


PUBLIC_HELP = (
    "Busca por nombre de modelo, por ejemplo: Jordan 4 Military Black.\n"
    "Puedes escribir el nombre directamente o usar /buscar <modelo>.\n\n"
    "El índice recoge enlaces publicados por canales de la comunidad, "
    "no el catálogo completo de Hacoo. No verifico precio, talla ni reseñas."
)


def _authorized(update: Update, allowed: set) -> bool:
    user = update.effective_user
    return bool(user and user.id in allowed)


def _private_authorized(update, allowed):
    return bool(update.effective_chat
                and update.effective_chat.type == "private"
                and _authorized(update, allowed))


async def _deny(update: Update) -> None:
    if update.effective_chat and update.effective_chat.type == "private":
        await update.effective_message.reply_text(
            "Este bot es privado. Pide acceso a su dueño.")


def make_handlers(cfg, db):
    gate = SubscriberGate(cfg.public_channel_id, cfg.public_search_enabled)
    product_links = ProductLinks(cfg.affiliate_mapping_file)

    async def search_allowed(update, ctx):
        if not update.effective_chat or update.effective_chat.type != "private":
            return False
        if _authorized(update, cfg.authorized_user_ids):
            return True
        if update.effective_chat.type != "private" or not update.effective_user:
            return False
        if not await gate.allowed(ctx.bot, update.effective_user.id):
            return False
        return True

    async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not await search_allowed(update, ctx):
            await _deny(update)
            return
        if _authorized(update, cfg.authorized_user_ids):
            await update.message.reply_text(
                "Mandame el modelo de la zapa o prenda y te busco el enlace de "
                "Hacoo mas reciente de la comunidad.\n\n" + HELP)
        else:
            await update.message.reply_text(PUBLIC_HELP)

    async def ayuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not await search_allowed(update, ctx):
            await _deny(update)
            return
        await update.message.reply_text(
            HELP if _authorized(update, cfg.authorized_user_ids) else PUBLIC_HELP)

    async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not _private_authorized(update, cfg.authorized_user_ids):
            await _deny(update)
            return
        s = db.stats()
        await update.message.reply_text(
            f"Mensajes indexados: {s['msgs']}\n"
            f"Enlaces: {s['links']} ({s['resolved']} resueltos a Hacoo)\n"
            f"Canales: {s['channels']}")

    async def canales(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not _private_authorized(update, cfg.authorized_user_ids):
            await _deny(update)
            return
        channels = db.channels(cfg.channels)
        # Telegram has a 4096 character limit; keep summary bounded.
        lines = ["Fuentes (posts con enlace / enlaces / con ID sin 404 / 404):"]
        for c in channels:
            m = db.channel_metrics(c)
            lines.append(f"@{c}: {m['posts']} / {m['links']} / "
                         f"{m['resolved_not_dead']} / {m['shortlinks_dead']}")
        await update.message.reply_text("\n".join(lines)[:3900])

    async def tendencias(update, ctx):
        if not _private_authorized(update, {cfg.owner_id}):
            await _deny(update)
            return
        namespace = ctx.args[0].lower() if ctx.args else "hacoo"
        if namespace not in {"hacoo", "taobao", "tmall", "weidian", "1688"}:
            await update.message.reply_text("Uso: /tendencias hacoo|taobao|tmall|weidian|1688")
            return
        rows = trends(db, namespace=namespace, limit=5)
        if not rows:
            await update.message.reply_text("No hay ofertas observadas en los últimos 7 días para esa fuente.")
            return
        await update.message.reply_text(
            "Borradores: repetición entre fuentes y frescura, no ventas ni popularidad verificada. No he publicado nada en el canal.")
        for row in rows:
            await update.message.reply_text(format_offer(row), parse_mode="HTML",
                                           disable_web_page_preview=True)

    async def agregarcanal(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        # Only the account owner can expand the crawl set, not Rodrigo.
        if (not update.effective_user or update.effective_user.id != cfg.owner_id
                or not update.effective_chat or update.effective_chat.type != "private"):
            await _deny(update)
            return
        if len(ctx.args) != 1:
            await update.message.reply_text(
                "Uso: /agregarcanal https://t.me/s/nombre_del_canal")
            return
        try:
            username = normalize_source(ctx.args[0])
            if username in {c.lower() for c in db.channels(cfg.channels)}:
                await update.message.reply_text(f"@{username} ya está en las fuentes.")
                return
            preview = await asyncio.to_thread(
                preview_source, _get_session(), username)
            if not db.add_channel(username, cfg.channels):
                await update.message.reply_text(f"@{username} ya estaba añadido.")
                return
        except (ValueError, OSError) as exc:
            await update.message.reply_text(f"No añadí el canal: {exc}")
            return
        except Exception:
            log.exception("fallo validando canal público")
            await update.message.reply_text(
                "No pude validar ese canal público; no lo añadí.")
            return
        await update.message.reply_text(
            f"@{username} añadido. Vista previa: {preview['messages_with_links']} "
            f"posts con enlaces y {preview['candidate_links']} enlaces "
            "Hacoo/onlyaff candidatos. Se rastrea en el próximo ciclo; "
            "no he comprobado aún cada producto en Hacoo.")

    async def buscar(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not await search_allowed(update, ctx):
            await _deny(update)
            return
        if (not _authorized(update, cfg.authorized_user_ids)
                and gate.throttle(update.effective_user.id)):
            await update.message.reply_text(
                "Espera unos segundos antes de otra búsqueda.")
            return
        query = " ".join(ctx.args) if ctx.args else (update.message.text or "")
        if update.message.text and update.message.text.startswith("/buscar"):
            query = " ".join(ctx.args)
        query = query.strip()
        if len(query) > 120:
            await update.message.reply_text("Busca por nombre de modelo, hasta 120 caracteres.")
            return
        if len(query) < 3:
            await update.message.reply_text(
                "Dime el modelo, por ejemplo: Jordan 4 Military Black")
            return
        try:
            found = search(db, query, limit=5)
        except sqlite3.Error:
            log.exception("fallo buscando en el indice")
            await update.message.reply_text("No pude consultar el índice. Prueba otra vez.")
            return
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
            if not product_links.for_result(r) or not safe_product_url(r["orig_url"]):
                continue
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
            warn = " ⚠️ enlace antiguo" if r.get("stale") else ""
            # This proves only the original shortlink was not 404/410 at
            # the checked time. A 200 from the Hacoo SPA proves no stock.
            state = ("Último intento sin 404/410 (errores no prueban validez)" if
                     r.get("checked_at") else "Shortlink sin comprobar")
            source = (f"https://t.me/{r['channel']}/{r['message_id']}"
                      if r["channel"].replace("_", "").isalnum()
                      and r["message_id"] else "")
            citation = (f'<a href="{html.escape(source, quote=True)}">'
                        f'@{html.escape(r["channel"])}</a>' if source else
                        html.escape(r["channel"]))
            lines.append(
                f"{i}. {html.escape(r['title'])}{extra}{date}{warn}\n"
                f"Fuente: {citation} · {state} (no verifica disponibilidad).\n"
                f"<a href=\"{html.escape(product_links.for_result(r), quote=True)}\">"
                "Abrir en Hacoo</a>")
        lines.append("\nLa talla se elige dentro de Hacoo al comprar.")
        await update.message.reply_text(
            "\n".join(lines), parse_mode="HTML",
            disable_web_page_preview=True)

    async def texto(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or update.effective_chat.type != "private":
            return
        ctx.args = (update.message.text or "").split()
        await buscar(update, ctx)

    async def foto(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        # Vision calls a keyed LLM; preserve Nico and Rodrigo's scope.
        if not _private_authorized(update, cfg.authorized_user_ids):
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
        "canales": canales, "agregarcanal": agregarcanal,
        "buscar": buscar, "texto": texto, "foto": foto, "tendencias": tendencias,
    }
