"""Identificacion de modelo/colorway por foto con LLM de vision.

Usa el gateway OpenAI-compatible de OpenCode Go (el mismo que CavaAI;
modelo gratuito en la tier actual). Si no hay clave configurada, el
handler de fotos responde con el mensaje de reserva.
"""
import base64
import json
import logging
import urllib.request

log = logging.getLogger(__name__)

PROMPT = (
    "Eres un experto en zapatillas y ropa de marca. Identifica el articulo "
    "de la foto: marca, modelo exacto y colorway (colores). Responde SOLO "
    "con una frase corta de busqueda en ingles, por ejemplo: "
    "Nike Dunk Low Panda o Jordan 4 Military Black o Trapstar tracksuit "
    "black. Sin explicaciones, sin puntuacion final."
)


def identify_from_photo(image_bytes: bytes, api_key: str, base_url: str,
                        model: str, session: str, timeout: int = 120) -> str:
    """Devuelve la frase de busqueda o cadena vacia si falla."""
    img_b64 = base64.b64encode(image_bytes).decode()
    body = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url",
             "image_url": {"url": "data:image/jpeg;base64," + img_b64}},
        ]}],
        "max_tokens": 2000,  # los modelos con razonamiento queman presupuesto
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "x-opencode-session": session,
            "User-Agent": "python-httpx/0.27",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        content = (data.get("choices", [{}])[0]
                   .get("message", {}).get("content") or "")
        return " ".join(content.split()).strip(" .")[:120]
    except Exception as e:
        log.warning("vision fallo: %s", e)
        return ""
