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

### Enlaces caídos: comprobación en consulta

`/buscar` y tendencias Hacoo prueban enlaces originales en el momento de la
consulta (caché local 120s, timeout hasta 3s por solicitud, máximo cuatro saltos,
presupuesto de 8s y 12 comprobaciones búsqueda / 8 tendencias por consulta).
404/410 y destinos no seguros se marcan muertos. Timeout, 429, errores y un
onlyaff 200 sin destino Hacoo confirmado son desconocidos, no prueba de muerte.
Desconocidos se muestran con "puede estar caído" SIN enlace de producto clicable.

Al morir un enlace se buscan hasta dos alternativas ya indexadas con el MISMO
ID Hacoo confirmado y se comprueban; no se fabrica una URL desde el ID. Mappings
aprobados también se comprueban; si fallan se usa solo la ruta comprobada. El
mapping verificado conserva su URL original y parámetros de atribución.

Un 200 de Hacoo prueba ruta accesible, NO existencia del producto, stock o talla.
No hay garantía absoluta: la SPA puede responder 200 para una ficha eliminada y
la ruta puede caducar después del check. Marketplace continúa offline; tendencias
marketplace omiten enlace clicable con aviso hasta tener comprobación soportada.
No se usa navegador, pagos, catálogo privado ni API inventada para la recuperación.

### Existencia real: probe SSR de producto (web ES)

Un HTTP 200 NO habilita ya el botón por sí solo. Tras comprobar la ruta, el
checker consulta la ficha pública oficial `shop.hacoo.pl/es-ES/detail/<ID>`:
requiere `__F_STATE__.detail.itemDetail` con ID coincidente, `status=1` y título.
Solo entonces muestra enlace, con texto "Ficha presente en la web ES al
comprobar; no verifica stock/talla". Nunca cambia el ID pedido por otra ficha.

`itemDetail=null` + `isAbnormalItem=true` + aviso visible específico + ausencia
de error declara "No disponible en la web ES", sin botón. No marca permanentemente
muerto un shortlink por ese estado: región/restricciones pueden cambiar. Genéricos,
errores, HTML sin estado, IDs distintos y presupuesto agotado son desconocidos,
sin botón. Caché de ficha 120s, compartida por ID y dentro del presupuesto existente.
Respuesta SSR acotada a 2 MB. Probe no se usa como URL afiliada o sustituto inventado.

Verificación real 2026-09-30: búsqueda oficial de shoes enlaza 40302592/39928200,
ambos SSR presentes. 40777036 declara no disponible. Fixtures mínimos derivados
con fuentes en tests/fixtures/product-state/SOURCES.md. No se ha probado todavía
un producto que el dueño etiquete inequívocamente como borrado global. La lógica
prueba disponibilidad web ES, no eliminación global ni disponibilidad en la app.
La mayoría de rutas www/hacoo.app son home genérico: se prueba la ficha shop aparte,
y si ahí no existe señal válida, se suprime botón. Puede reducir mucho resultados.
No requiere render JS ni acceso al panel afiliado; no cambia allowlist ni flags.

### Alias reales y muestras de producción

Parser compartido de producto: `/p/ID`, `/detail/ID`, `/product/ID` y prefijos
`/ES/` o `/es-ES/`. Rechaza sufijos basura, IDs Unicode y paths arbitrarios.
El probe solo acepta SSR de la ruta `shop.hacoo.pl/es-ES/detail/ID`, no una
redirección a otra región. Errores desconocidos tienen caché de 15s (positivos y
no disponible 120s), para no bloquear una recuperación transitoria dos minutos.

Cinco muestras de producción contrastadas 2026-10-01: 14642740, 14642718,
14638268, 39459713, 39512968. Todas muestran no disponible en web ES. Las primeras
tres eran resolved/not-dead en BD: eso NO demuestra producto vivo. Las últimas
dos tenían dead_at: eso NO demuestra borrado global. Fixtures documentan etiquetas
sin confundir estado de transporte con existencia de producto.

### Resultados después del filtrado

Buscar recoge hasta 15 candidatos y presenta hasta cinco: verifica con el MISMO
presupuesto compartido de 8s/12 checks. Si los primeros mueren, prueba candidatos
posteriores sin ampliar llamadas. Confirmados primero, avisos sin botón después.
El encabezado de modelo exacto se calcula sobre botones realmente confirmados,
no sobre un candidato muerto u omitido. Sin inventar stock o cambiar OFF.

### Apagado del indexador

Al cancelar, espera a que termine el trabajo síncrono activo antes de cerrar su
sesión/SQLite: cancelar `to_thread` no detiene el hilo. El indexador solo arranca
tras polling inicializado; fallos parciales del arranque no llaman stop de un
updater que nunca empezó. INDEXER_ONLY también cierra DB en salida.
Un apagado puede tardar hasta que termine el crawl/resolver acotado activo;
no se promete parada inmediata ni se interrumpe una operación SQLite en vuelo.

### Respuestas largas

Buscar y tendencias dividen HTML solo entre bloques completos, con límite
conservador 3800 caracteres por mensaje. Un bloque demasiado largo (por ejemplo
URL firmada gigante) se omite con aviso, no se corta dentro del href. Títulos de
búsqueda limitados a 200 caracteres antes de escapar HTML. No se pierde silencio
por superar el límite de Telegram con cinco fichas extensas.

### Índice disperso y rendimiento

Un rango min..max de posts conocidos ya no se interpreta como completo: un post
hueco dentro de ese rango se procesa si aparece en la página. Inserts idempotentes
mantienen duplicados a cero. Mensajes/nav IDs cuyo data-post no coincide con el
canal pedido se ignoran, para no atribuir fuente equivocada. Índices parciales de
SQLite aceleran búsqueda de alternativa por ID y colas resolver/liveness sin
borrar datos. No hace recrawl histórico automático ni amplía fuentes.
