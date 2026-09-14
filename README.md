# Kutit

Backend for **Clever CNC**'s panel-cutting order form. Customers submit a cutting
list (panel material, sizes, edge-banding) through a public web form; staff confirm
and track each order through production from an internal dashboard.

## Stack

- **FastAPI** (Python) — HTTP API + server-rendered HTML via Jinja2
- **asyncpg** — talks to a **PostgreSQL** database (`DATABASE_URL`)
- **Uvicorn** — ASGI server (`Procfile` runs it for Railway)

## Data model

Created automatically on startup (`db.init_db`, called from the FastAPI
`lifespan` hook):

**`solicitudes`** (orders)
| column | meaning |
|---|---|
| `contacto`, `telefono`, `email` | customer contact info |
| `fecha`, `material` | requested date, panel material name |
| `con_material` | whether Clever CNC provides the panel (false = customer brings their own) |
| `material_id` | Odoo `product.template` id of the chosen panel, if it's an Odoo-backed material |
| `material_manual_id` | id into `materiales_manuales`, if it's a manually-added (non-Odoo) material — mutually exclusive with `material_id` |
| `estado` | `esperando_confirmacion_whatsapp` → `confirmada` → (optionally) `cancelada` |
| `etapa_produccion` | production stage once confirmed: `por_hacer` → `en_proceso` → `terminado` |
| `motivo_cancelacion` | reason, if cancelled |

**`lineas_corte`** (cut lines, one order has many)
| column | meaning |
|---|---|
| `descripcion`, `cantidad` | what it is, how many pieces |
| `alto`, `ancho` | height/width in mm (defaults 2750×1830, a standard panel) |
| `canto_1..4` | which of the 4 edges get edge-banding (canto) |
| `rotar` | whether the piece may be rotated to fit the cutting layout |

**`medidas_material`** (local overrides for an Odoo-backed price, keyed by Odoo `product.template` id)

Covers both the two fixed services (`ODOO_PRODUCT_CORTE_ID`/`ODOO_PRODUCT_CANTO_ID`)
and the dynamically-discovered materials — Odoo has price/name for each, but
not physical size, and staff sometimes need to override the shown price or
temporarily hide an item; both are managed here from the unified list at
`/dashboard/precios` (see **Pricing** below).
| column | meaning |
|---|---|
| `odoo_id` | Odoo `product.template` id (primary key) |
| `nombre` | cached product name |
| `ancho`, `largo` | full-panel dimensions in mm — materials only, `NULL` for services |
| `habilitado` | whether it's active: shown on the public form/estimate |
| `precio_manual` | optional override shown instead of Odoo's `list_price` — for when Odoo has no price loaded, or staff don't want to show that price to customers |

**`materiales_manuales`** (priced items — materials or services — with no Odoo product at all)

For anything staff want in Kutit's price list / the public form's material
dropdown without creating an Odoo product for it. Not tied to Odoo in any
way — a material row here is never pushed as a line item to the generated
`sale.order` (see **Odoo sync**); a service row here is purely for internal
reference and isn't used by the public budget estimate (which only computes
Corte and Canto, both always Odoo-backed).
| column | meaning |
|---|---|
| `id` | local id (referenced by `solicitudes.material_manual_id` for materials) |
| `categoria` | `material` or `servicio` |
| `nombre`, `precio` | shown wherever an Odoo item's name/price would be |
| `ancho`, `largo` | full-panel dimensions in mm — materials only, `NULL` for services |
| `habilitado` | whether it's active: shown on the public form's material dropdown (materials only) |

## Request lifecycle

1. Customer fills the public form (`GET /`) — a 3-step wizard (data & material →
   cut list → budget estimate) — and submits it (`POST /solicitudes`). The
   estimate is computed client-side from `/materiales` and `/precios`; it's
   informational only, the real quotation is the Odoo `sale.order`. Empty/
   placeholder rows are dropped server-side (`fila_vacia`); a hidden honeypot
   field silently no-ops bot submissions instead of erroring. Staff can also
   create an order on a customer's behalf from `/dashboard/solicitudes/nueva`,
   optionally extracting the cut list from a photo (see **Photo extraction**).
2. Order is created with `estado = esperando_confirmacion_whatsapp`. The
   customer gets a link to `/pedido/{id}` (a read-only status page) and is
   expected to confirm via WhatsApp (number from `WHATSAPP_NUMBER`) before
   staff act on it.
3. Staff log into `/dashboard`, review the order, and call **confirm**
   (`POST /solicitudes/{id}/confirmar`), which sets `estado = confirmada` and
   `etapa_produccion = por_hacer`.
4. Staff move the order through production stages
   (`POST /solicitudes/{id}/etapa`) until `terminado`. A `terminado` order can
   no longer be edited or have its stage changed.
5. An order can be cancelled at any point (`POST /solicitudes/{id}/cancelar`),
   or deleted outright (`DELETE /solicitudes/{id}`).
6. Once `confirmada`, staff can push the order to Odoo as a quotation
   (`POST /solicitudes/{id}/odoo`) — see **Odoo sync** below.

## Photo extraction

From `/dashboard/solicitudes/nueva`, staff can upload a photo of a customer's
handwritten or WhatsApp-sent cut list (`POST /dashboard/extraer-piezas`).
`vision_extract.py` sends the image to Claude (`ANTHROPIC_API_KEY`) with a
prompt describing the expected fields and gets back a structured list of
pieces (description, quantity, height/width in mm, edge-banding), which
pre-fills the cut list table for staff to review before creating the order.
The image itself is never stored.

## Pricing

`/dashboard/precios` is one unified, sortable/filterable/paginated table
(server-renders the rows, DataTables — SB Admin 2's usual pairing — handles
sort/search/paging client-side) built in `main._lista_precios()` by merging
four sources every time the page loads:
1. The two fixed services (`ODOO_PRODUCT_CORTE_ID`/`_CANTO_ID`) with their live Odoo price.
2. Materials dynamically discovered in Odoo (`odoo_client.listar_materiales`).
3. Local overrides/dimensions for either of the above (`medidas_material`).
4. Fully manual items with no Odoo product (`materiales_manuales`).

Each row's *effective* price is its `precio_manual` override if set, else the
live Odoo price. Actions per row:
- **Guardar** — for an Odoo-backed row, upserts its `medidas_material` override
  (dimensions/active state/manual price); for a manual row, updates it in place.
- **Archivar/Activar** — toggles active state (`habilitado`). Inactive rows are
  excluded from `/materiales`, `/precios`, and the public form's dropdown, but
  stay in this admin list.
- **Eliminar** — for a manual row, deletes it outright. For an Odoo-backed row,
  it deletes the *local override* only — the underlying Odoo product is
  untouched, so if it's still Odoo-discoverable it reappears on next page load
  with default (unconfigured) values, which is the intended "reset" behavior.

Manual services are informational only — the public budget estimate only ever
computes Corte and Canto (both always Odoo-backed), so a manual service row
has nowhere to plug into that calculation.

## Auth

There's no user database — a single shared **API key** (`DASHBOARD_API_KEY`)
logs into the dashboard (`POST /dashboard/login`). On success the server issues
a signed session cookie (`kutit_session`): `timestamp.HMAC-SHA256(timestamp)`,
keyed by `SESSION_SECRET`, valid for 7 days, verified with a constant-time
comparison. All `/solicitudes/*` API routes (except creating a new order) and
the dashboard pages require this cookie via the `requerir_sesion` dependency.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | — | Public order form |
| POST | `/solicitudes` | — | Create a new order (attempts an Odoo quotation immediately, best-effort) |
| GET | `/materiales` | — | List enabled panel materials with price + dimensions, for the public form |
| GET | `/precios` | — | Current corte/canto unit prices, for the public form's live estimate |
| GET | `/pedido/{id}` | — | Read-only order status page for the customer |
| GET | `/health` | — | Health check |
| GET | `/dashboard` | cookie | Kanban-style board grouped by state/stage |
| GET | `/dashboard/precios` | cookie | Unified, sortable/filterable price list — services and materials, Odoo and manual (see **Pricing**) |
| POST | `/dashboard/precios/medidas` | cookie | Save an Odoo-backed item's dimensions/active state/manual price override |
| DELETE | `/dashboard/precios/medidas/{odoo_id}` | cookie | Clear local overrides for an Odoo-backed item (reverts to live Odoo values) |
| POST | `/dashboard/precios/materiales-manuales` | cookie | Create or update a manual (non-Odoo) priced item |
| DELETE | `/dashboard/precios/materiales-manuales/{id}` | cookie | Permanently delete a manual priced item |
| POST | `/dashboard/extraer-piezas` | cookie | Extract a cut list from an uploaded photo (see **Photo extraction**) |
| GET | `/dashboard/solicitudes/nueva` | cookie | Form for staff to create an order on a customer's behalf |
| POST | `/dashboard/solicitudes` | cookie | Create an order as staff (same as `POST /solicitudes`, cookie-authed) |
| POST | `/dashboard/login` | API key | Exchange API key for session cookie |
| POST | `/dashboard/logout` | — | Clear session cookie |
| GET | `/dashboard/solicitudes/{id}` | cookie | Order detail/edit page |
| GET | `/solicitudes/{id}` | cookie | Order detail (JSON) |
| GET | `/solicitudes/{id}/csv` | cookie | Export cut lines as CSV |
| PUT | `/solicitudes/{id}` | cookie | Edit order/cut lines (blocked once `terminado`) |
| POST | `/solicitudes/{id}/confirmar` | cookie | Mark order confirmed, enter production |
| POST | `/solicitudes/{id}/etapa` | cookie | Move production stage (blocked once `terminado`) |
| POST | `/solicitudes/{id}/cancelar` | cookie | Cancel order with optional reason |
| DELETE | `/solicitudes/{id}` | cookie | Delete order and its cut lines |
| POST | `/solicitudes/{id}/odoo` | cookie | (Re-)send the order to Odoo as a quotation (blocked once `cancelada`) |

## Odoo sync

Every order gets a best-effort push to Odoo as a `sale.order` (quotation)
right when it's created (`_crear_solicitud`) — failures are swallowed so a
down/misconfigured Odoo never blocks a customer's request. Staff can also
(re-)send it later from the order detail page (`POST /solicitudes/{id}/odoo`,
blocked only once `cancelada`). Both paths call `odoo_client.crear_presupuesto`:

- Authenticates over XML-RPC (`ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`,
  `ODOO_API_KEY`) — runs in a worker thread since `xmlrpc.client` is blocking.
- Uses a single fixed partner (`ODOO_PARTNER_CONSUMIDOR_FINAL_ID`, e.g.
  "Consumidor Final") for every order — the customer's name/phone go into the
  quotation's `x_studio_titulo` instead of a dedicated `res.partner`.
- Adds one order line for the CNC cutting service (`ODOO_PRODUCT_CORTE_ID`).
  Quantity is the total cut perimeter in meters (`calculos.metros_corte`); the
  line description lists every cut (size, quantity, edge-banding).
- If any cut has edge-banding, adds a second line for the edge-banding
  service (`ODOO_PRODUCT_CANTO_ID`), quantity = total banded edge length in
  meters (`calculos.metros_canto`).
- If the order has `con_material` with a `material_id` whose dimensions are
  configured (`medidas_material`), adds a third line for that panel product,
  quantity = number of full panels needed (`calculos.cantidad_placas`, ceil of
  total piece area over panel area).
- The resulting Odoo order id/name is saved back on the order
  (`odoo_pedido_id`, `odoo_pedido_nombre`) so re-sending is visible as
  "Reenviar a Odoo" rather than silently duplicating the quotation — note
  this only prevents *accidental* re-clicks from being confusing; clicking it
  again still creates a second `sale.order` in Odoo.

Odoo product ids passed around the app (`ODOO_PRODUCT_CORTE_ID`, `_ID` config
in general) are `product.template` ids; `odoo_client._resolver_variante`
resolves each to its `product.product` variant id (what `sale.order` lines
actually need) and its price, falling back to treating the id as already a
`product.product` id if no matching template exists.

## Configuration (`config.py` / `.env`)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql://user:pass@host:port/db`) |
| `DASHBOARD_API_KEY` | Shared secret to log into `/dashboard` |
| `SESSION_SECRET` | HMAC key for session cookies (falls back to `DASHBOARD_API_KEY`, then a dev default — always set explicitly in production) |
| `HONEYPOT_FIELD_NAME` | Hidden form field name used to silently drop bot submissions |
| `ALLOWED_ORIGIN` | CORS allow-origin for the public form |
| `WHATSAPP_NUMBER` | Number shown to customers for order confirmation |
| `CLEVER_SITE_URL` | Clever CNC's site, linked from the "← Volver a Clever CNC" back link |
| `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_API_KEY` | Odoo XML-RPC connection |
| `ODOO_PRODUCT_CORTE_ID` | `product.template` id of the CNC cutting service in Odoo |
| `ODOO_PRODUCT_CANTO_ID` | `product.template` id of the edge-banding service in Odoo |
| `ODOO_CATEGORIA_MATERIALES_ID` | eCommerce category id grouping panel/material products in Odoo |
| `ODOO_PARTNER_CONSUMIDOR_FINAL_ID` | `res.partner` id used on every generated quotation |
| `ANTHROPIC_API_KEY` | Claude API key used for photo-based cut list extraction |

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in secrets
uvicorn main:app --reload
```

## Deployment

Deployed on **Railway** via the `Procfile`
(`uvicorn main:app --host 0.0.0.0 --port $PORT`). Set the variables above in the
Railway project's environment before the first deploy.
