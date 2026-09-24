# Hacoo Replica Finder Bot

Bot de Telegram que busca replicas de ropa y zapatillas en Hacoo usando
los enlaces que publica la comunidad en canales publicos de Telegram.

## Como funciona

- **Indice propio**: un rastreador lee la vista web publica de canales de
  Telegram donde la comunidad publica hallazgos de Hacoo
  (`https://t.me/s/<canal>`, solo lectura, sin API ni login), extrae
  modelo + enlace, resuelve los shortlinks de afiliado a la URL canonica
  de producto de Hacoo (`/detail/<id>`) y guarda todo en SQLite con
  busqueda de texto completo (FTS5, sin tildes).
- **Busqueda**: le escribes al bot el modelo (`Jordan 4 Military Black`)
  y te devuelve los enlaces mas recientes/relevantes, agrupados por
  producto cuando varios canales publican lo mismo.

## Limitaciones honestas

- **No hay API publica de Hacoo**: la web es una SPA tras WAF y las
  paginas de producto no exponen datos. Por eso el indice es de fuentes
  comunitarias, no del catalogo completo.
- **Precios y resenas no estan disponibles** en las fuentes comunitarias;
  el bot devuelve enlaces, no comparador de precios.
- **La talla no se busca**: el enlace lleva al producto y la talla se
  elige dentro de Hacoo al comprar.
- **Busqueda por foto**: en pruebas (Google Lens no responde bien desde
  IPs de datacenter). Por ahora, nombre del modelo.

## Despliegue (Oracle VM)

```bash
cp .env.example .env   # rellena TELEGRAM_BOT_TOKEN
chmod 600 .env
docker compose up -d --build
```

Sin puertos publicados (polling saliente). Datos persistentes en `./data`.

## Desarrollo

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
TELEGRAM_BOT_TOKEN=... DB_PATH=data/replicas.db python bot/main.py
```
