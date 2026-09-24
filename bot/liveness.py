"""Chequeo de vida de enlaces.

El shortlink de afiliado (onlyaff y similares) devuelve 404 cuando el
enlace muere: esa es la senal comprobable desde servidor. La ficha de
Hacoo devuelve siempre la misma cascara SPA (200 identico para productos
vivos y borrados), asi que la muerte del PRODUCTO no es detectable sin
navegador; solo marcamos muerto lo que el acortador confirma.
"""
import logging
import time

log = logging.getLogger(__name__)

DEAD_CODES = {404, 410}


def check_pending(session, db, rate_per_min: int = 30,
                  max_seconds: float = 0) -> tuple:
    """Devuelve (chequeados, muertos). max_seconds=0 -> sin tope."""
    started = time.time()
    done = dead = 0
    delay = 60.0 / max(1, rate_per_min)
    while True:
        rows = db.links_to_check(25)
        if not rows:
            break
        for row in rows:
            is_dead = False
            try:
                r = session.get(row["url"], allow_redirects=False,
                                timeout=15, stream=True)
                r.close()
                is_dead = r.status_code in DEAD_CODES
            except Exception as e:
                log.debug("liveness %s: %s", row["url"], e)
            db.mark_checked(row["id"], is_dead)
            done += 1
            dead += int(is_dead)
            time.sleep(delay)
            if max_seconds and time.time() - started > max_seconds:
                return done, dead
    return done, dead
