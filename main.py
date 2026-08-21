import asyncio
import csv
import io
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

import config
import db
import odoo_client
import security
from models import CancelarIn, EtapaIn, FilaCorte, SolicitudCorteIn, SolicitudCorteUpdate


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield
    await db.close_db()


app = FastAPI(title="Kutit", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.ALLOWED_ORIGIN],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def sesion_activa(request: Request) -> bool:
    return security.token_valido(request.cookies.get(security.SESSION_COOKIE_NAME))


def requerir_sesion(request: Request):
    if not sesion_activa(request):
        raise HTTPException(status_code=401, detail="No autenticado")


def fila_vacia(c: FilaCorte) -> bool:
    return (
        not c.descripcion.strip()
        and c.alto == config.MEDIDA_LARGO_DEFAULT
        and c.ancho == config.MEDIDA_ANCHO_DEFAULT
        and c.cantidad == 1
        and not any([c.canto_1, c.canto_2, c.canto_3, c.canto_4])
    )


async def obtener_o_404(solicitud_id: int):
    solicitud = await db.obtener_solicitud(solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return solicitud


# ---------------------------------------------------------------- público

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "honeypot_field": config.HONEYPOT_FIELD_NAME,
            "whatsapp_number": config.WHATSAPP_NUMBER,
        },
    )


@app.post("/solicitudes")
async def crear_solicitud_endpoint(request: Request):
    payload = await request.json()
    if security.es_honeypot(payload.get(config.HONEYPOT_FIELD_NAME)):
        return {"ok": True}

    try:
        datos = SolicitudCorteIn.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    datos.cortes = [c for c in datos.cortes if not fila_vacia(c)]
    if not datos.cortes:
        raise HTTPException(status_code=400, detail="Agregá al menos un corte")

    solicitud_id = await db.crear_solicitud(datos)
    return {"ok": True, "id": solicitud_id, "estado": "esperando_confirmacion_whatsapp"}


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------- dashboard / auth

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not sesion_activa(request):
        return templates.TemplateResponse(request, "login.html")

    solicitudes = await db.listar_solicitudes()
    grupos = {
        "esperando": [s for s in solicitudes if s["estado"] == "esperando_confirmacion_whatsapp"],
        "por_hacer": [s for s in solicitudes if s["estado"] == "confirmada" and s["etapa_produccion"] == "por_hacer"],
        "en_proceso": [s for s in solicitudes if s["estado"] == "confirmada" and s["etapa_produccion"] == "en_proceso"],
        "terminado": [s for s in solicitudes if s["estado"] == "confirmada" and s["etapa_produccion"] == "terminado"],
        "canceladas": [s for s in solicitudes if s["estado"] == "cancelada"],
    }
    return templates.TemplateResponse(request, "dashboard.html", {"grupos": grupos})


@app.post("/dashboard/login")
async def dashboard_login(request: Request, api_key: str = Form(...)):
    if not security.api_key_valida(api_key):
        return templates.TemplateResponse(
            request, "login.html", {"error": "API key inválida"}, status_code=401
        )
    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.set_cookie(
        security.SESSION_COOKIE_NAME,
        security.crear_token_sesion(),
        max_age=security.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return resp


@app.post("/dashboard/logout")
async def dashboard_logout():
    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.delete_cookie(security.SESSION_COOKIE_NAME)
    return resp


@app.get("/dashboard/solicitudes/{solicitud_id}", response_class=HTMLResponse)
async def editar_solicitud_page(request: Request, solicitud_id: int):
    if not sesion_activa(request):
        return templates.TemplateResponse(request, "login.html")
    solicitud = await obtener_o_404(solicitud_id)
    return templates.TemplateResponse(request, "detalle.html", {"solicitud": solicitud})


# ---------------------------------------------------------------- API interna (requiere sesión)

@app.get("/solicitudes/{solicitud_id}", dependencies=[Depends(requerir_sesion)])
async def detalle_solicitud(solicitud_id: int):
    return await obtener_o_404(solicitud_id)


@app.get("/solicitudes/{solicitud_id}/csv", dependencies=[Depends(requerir_sesion)])
async def csv_solicitud(solicitud_id: int):
    solicitud = await obtener_o_404(solicitud_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["descripcion", "cantidad", "largo", "ancho", "l1", "l2", "a1", "a2", "rotar"])
    for c in solicitud["cortes"]:
        writer.writerow([
            c["descripcion"], c["cantidad"], c["alto"], c["ancho"],
            str(bool(c["canto_1"])).lower(), str(bool(c["canto_2"])).lower(),
            str(bool(c["canto_3"])).lower(), str(bool(c["canto_4"])).lower(),
            str(bool(c["rotar"])).lower(),
        ])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="solicitud-{solicitud_id}.csv"'},
    )


@app.put("/solicitudes/{solicitud_id}", dependencies=[Depends(requerir_sesion)])
async def editar_solicitud(solicitud_id: int, datos: SolicitudCorteUpdate):
    solicitud = await obtener_o_404(solicitud_id)
    if solicitud["etapa_produccion"] == "terminado":
        raise HTTPException(status_code=409, detail="No se puede editar una solicitud terminada")
    await db.actualizar_solicitud(solicitud_id, datos)
    return await db.obtener_solicitud(solicitud_id)


@app.post("/solicitudes/{solicitud_id}/confirmar", dependencies=[Depends(requerir_sesion)])
async def confirmar(solicitud_id: int):
    await obtener_o_404(solicitud_id)
    await db.confirmar_solicitud(solicitud_id)
    return {"ok": True}


@app.post("/solicitudes/{solicitud_id}/etapa", dependencies=[Depends(requerir_sesion)])
async def cambiar_etapa(solicitud_id: int, datos: EtapaIn):
    solicitud = await obtener_o_404(solicitud_id)
    if solicitud["etapa_produccion"] == "terminado":
        raise HTTPException(status_code=409, detail="Una solicitud terminada no cambia de etapa")
    await db.mover_etapa(solicitud_id, datos.etapa.value)
    return {"ok": True}


@app.post("/solicitudes/{solicitud_id}/cancelar", dependencies=[Depends(requerir_sesion)])
async def cancelar(solicitud_id: int, datos: CancelarIn):
    await obtener_o_404(solicitud_id)
    await db.cancelar_solicitud(solicitud_id, datos.motivo)
    return {"ok": True}


@app.delete("/solicitudes/{solicitud_id}", dependencies=[Depends(requerir_sesion)])
async def eliminar(solicitud_id: int):
    await obtener_o_404(solicitud_id)
    await db.eliminar_solicitud(solicitud_id)
    return {"ok": True}


@app.post("/solicitudes/{solicitud_id}/odoo", dependencies=[Depends(requerir_sesion)])
async def enviar_a_odoo(solicitud_id: int):
    solicitud = await obtener_o_404(solicitud_id)
    if solicitud["estado"] != "confirmada":
        raise HTTPException(status_code=409, detail="Solo se puede enviar a Odoo una solicitud confirmada")
    try:
        resultado = await asyncio.to_thread(odoo_client.crear_presupuesto, solicitud)
    except odoo_client.OdooError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    await db.guardar_odoo_pedido(solicitud_id, resultado["odoo_pedido_id"], resultado["odoo_pedido_nombre"])
    return {"ok": True, **resultado}
