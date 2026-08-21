# Kutit

Backend for **Clever CNC**'s panel-cutting order form. Customers submit a cutting
list (panel material, sizes, edge-banding) through a public web form; staff confirm
and track each order through production from an internal dashboard.

## Stack

- **FastAPI** (Python) — HTTP API + server-rendered HTML via Jinja2
- **libsql-client** — talks to either a local SQLite file or a remote **Turso**
  database, depending on config
- **Uvicorn** — ASGI server (`Procfile` runs it for Railway)

## Data model

Two tables, created automatically on startup (`db.init_db`, called from the FastAPI
`lifespan` hook):

**`solicitudes`** (orders)
| column | meaning |
|---|---|
| `contacto`, `telefono`, `email` | customer contact info |
| `fecha`, `material` | requested date, panel material (default `MDF`) |
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

## Request lifecycle

1. Customer fills the public form (`GET /`) and submits it (`POST /solicitudes`).
   Empty/placeholder rows are dropped server-side (`fila_vacia`); a hidden
   honeypot field silently no-ops bot submissions instead of erroring.
2. Order is created with `estado = esperando_confirmacion_whatsapp` — the
   customer is expected to confirm via WhatsApp (number from `WHATSAPP_NUMBER`)
   before staff act on it.
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
| POST | `/solicitudes` | — | Create a new order |
| GET | `/health` | — | Health check |
| GET | `/dashboard` | cookie | Kanban-style board grouped by state/stage |
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
| POST | `/solicitudes/{id}/odoo` | cookie | Push a confirmed order to Odoo as a quotation |

## Odoo sync

From the order detail page, a **confirmed** order can be sent to Odoo
(`odoo_client.crear_presupuesto`) as a `sale.order` (quotation):

- Authenticates over XML-RPC (`ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`,
  `ODOO_API_KEY`) — runs in a worker thread since `xmlrpc.client` is blocking.
- Finds or creates a `res.partner` by matching `telefono` (falls back to
  creating one from `contacto`/`telefono`/`email`).
- Adds one order line for the CNC cutting service, looked up in Odoo by
  `default_code` (`ODOO_PRODUCT_CORTE_CODE`, default `cnc`) rather than a
  hardcoded numeric ID — product IDs aren't stable across Odoo instances.
  Quantity is the total piece count across all cut lines; the line
  description lists every cut (size, quantity, edge-banding).
- If any cut has edge-banding (`canto_1..4`), adds a second line for
  `ODOO_PRODUCT_CANTO_NOMBRE` (looked up by exact product name, since it has
  no `default_code`), quantity = total number of banded edges across the
  order.
- The resulting Odoo order id/name is saved back on the order
  (`odoo_pedido_id`, `odoo_pedido_nombre`) so re-sending is visible as
  "Reenviar a Odoo" rather than silently duplicating the quotation — note
  this only prevents *accidental* re-clicks from being confusing; clicking it
  again still creates a second `sale.order` in Odoo.

## Configuration (`config.py` / `.env`)

| Variable | Purpose |
|---|---|
| `TURSO_URL`, `TURSO_TOKEN` | Remote Turso DB; if unset, falls back to a local SQLite file |
| `LOCAL_DB_PATH` | Path for the local SQLite fallback (default `data/kutit.db`) |
| `DASHBOARD_API_KEY` | Shared secret to log into `/dashboard` |
| `SESSION_SECRET` | HMAC key for session cookies (falls back to `DASHBOARD_API_KEY`, then a dev default — always set explicitly in production) |
| `HONEYPOT_FIELD_NAME` | Hidden form field name used to silently drop bot submissions |
| `ALLOWED_ORIGIN` | CORS allow-origin for the public form |
| `WHATSAPP_NUMBER` | Number shown to customers for order confirmation |
| `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_API_KEY` | Odoo XML-RPC connection for the "send to Odoo" button |
| `ODOO_PRODUCT_CORTE_CODE` | `default_code` of the CNC cutting product in Odoo (default `cnc`) |
| `ODOO_PRODUCT_CANTO_NOMBRE` | Exact product name of the edge-banding service in Odoo |

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
