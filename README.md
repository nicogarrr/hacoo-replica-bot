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

## Canal propio (preparado, apagado por defecto)

El canal de Telegram es de difusión y no recibe preguntas de suscriptores.
Los miembros podrán pulsar `https://t.me/Hacoo_brother_bot` y buscar **por
privado**. El bot comprobará en cada consulta que son miembros del canal; no
comparte resultados en el canal, no revela listas de miembros y conserva
`/stats`, `/canales` y la búsqueda por foto solo para Nico/Rodrigo.

Para activarlo después de la aprobación, un operador con acceso al servidor
debe: (1) obtener el ID numérico del canal por Telegram, verificar que el
bot es admin y `getChatMember` distingue miembro y no miembro; (2) poner
`PUBLIC_CHANNEL_ID=-100...` y `PUBLIC_SEARCH_ENABLED=1` en `.env`; (3)
reiniciar solo este contenedor y comprobar una consulta privada de prueba
con Nico, un suscriptor distinto y un no miembro. Sin ID o con un error de
Telegram, el acceso falla cerrado. **No se activa con el código solo.**

Los resultados usan el enlace ya resuelto y guardado en el índice (o el
shortlink original si no se resolvió). No se fabrican URLs `/detail/<id>`.
Cuando la afiliación esté aprobada y el panel confirme el formato, se puede
montar un fichero JSON `{"12345": "https://enlace-verificado"}` dentro del
contenedor y configurar `AFFILIATE_MAPPING_FILE=/ruta/links.json`; el ID
procede de `resolver.py`. Sin fichero válido no hay reescritura de enlaces.
**No convertir a afiliación enlaces sin ID, ni atribuir ventas a URLs directas.**

### Tendencias privadas y borradores de alertas

`/tendencias hacoo|taobao|tmall|weidian|1688` (solo dueño, chat privado) muestra
hasta cinco borradores de los últimos siete días. No publica en ningún canal.
Observa repetición entre fuentes y frescura, no ventas ni popularidad real.

El rastreo guarda ofertas en `community_offers`, separadas por namespace.
Los IDs marketplace no entran en `/buscar`. Mismo ID se agrupa; títulos iguales
no bastan. Hacoo resuelto agrupa shortlinks; muertos conocidos se omiten.
Se mantienen enlaces de la fuente, no enlaces afiliados propios inventados.

Ranking: frescura dominante, fuentes adicionales acotadas y descuento acotado.
Precio/descuento solo de una pareja explícita `antes 100 EUR ahora 80 EUR`
(o €), moneda en ambos importes y una única identidad de producto en el post.
Es una afirmación del post, no precio actual verificado. No infiere porcentajes.

Se llena con páginas nuevas tras desplegar. Sin backfill automático ni scrape
de marketplaces. `/agregarcanal` sigue exigiendo enlaces Hacoo/onlyaff: el parser
marketplace recoge links coexistentes en fuentes ya aprobadas. Cero coste añadido.

### Operación segura

Arranque normal y `INDEXER_ONLY` validan límites antes de abrir la BD:
intervalo 1..1440 minutos, páginas 1..400, resolver 1..120 enlaces/minuto.
El backfill también valida sin exigir token Telegram. Se crea el directorio
de DB_PATH cuando falta. Ciclos de crawl cuentan inserciones reales, no
repeticiones. Tmall conserva namespace y URL Tmall, no se transforma en Taobao.
Consultas de tendencias limitan estado de resolución/muerte a su ventana de
observación, no cargan todo el histórico de enlaces.
