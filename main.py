import asyncio
import csv
import io
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

import calculos
import config
import db
import odoo_client
import security
import vision_extract
from models import CancelarIn, EtapaIn, FilaCorte, MedidaMaterialIn, SolicitudCorteIn, SolicitudCorteUpdate


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


async def _preparar_solicitud_para_odoo(solicitud: dict) -> dict:
    if solicitud.get("con_material") and solicitud.get("material_id"):
        medida = await db.obtener_medida_material(solicitud["material_id"])
        if medida and medida["ancho"] and medida["largo"]:
            return {
                **solicitud,
                "material_odoo_id": solicitud["material_id"],
                "material_ancho": medida["ancho"],
                "material_largo": medida["largo"],
            }
    return solicitud


ESTADOS_LABELS = {
    "esperando_confirmacion_whatsapp": "Esperando confirmación por WhatsApp",
    "confirmada": "Confirmada",
    "cancelada": "Cancelada",
}
ETAPAS_LABELS = {
    "por_hacer": "Por hacer",
    "en_proceso": "En proceso",
    "terminado": "Terminado",
}


# ---------------------------------------------------------------- público

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "honeypot_field": config.HONEYPOT_FIELD_NAME,
            "whatsapp_number": config.WHATSAPP_NUMBER,
            "clever_site_url": config.CLEVER_SITE_URL,
        },
    )


async def _crear_solicitud(datos: SolicitudCorteIn) -> int:
    datos.cortes = [c for c in datos.cortes if not fila_vacia(c)]
    if not datos.cortes:
        raise HTTPException(status_code=400, detail="Agregá al menos un corte")

    solicitud_id = await db.crear_solicitud(datos)

    solicitud = await _preparar_solicitud_para_odoo(await db.obtener_solicitud(solicitud_id))
    try:
        resultado = await asyncio.to_thread(odoo_client.crear_presupuesto, solicitud)
    except odoo_client.OdooError:
        resultado = None
    if resultado:
        await db.guardar_odoo_pedido(solicitud_id, resultado["odoo_pedido_id"], resultado["odoo_pedido_nombre"])

    return solicitud_id


@app.post("/solicitudes")
async def crear_solicitud_endpoint(request: Request):
    payload = await request.json()
    if security.es_honeypot(payload.get(config.HONEYPOT_FIELD_NAME)):
        return {"ok": True}

    try:
        datos = SolicitudCorteIn.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    solicitud_id = await _crear_solicitud(datos)
    return {"ok": True, "id": solicitud_id, "estado": "esperando_confirmacion_whatsapp"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/materiales")
async def listar_materiales():
    try:
        materiales = await asyncio.to_thread(odoo_client.listar_materiales)
    except odoo_client.OdooError:
        materiales = []
    if not materiales:
        materiales = [{"id": None, "nombre": "MDF", "precio": None}, {"id": None, "nombre": "Acrilico", "precio": None}]
    medidas = await db.listar_medidas_materiales()
    visibles = []
    for m in materiales:
        medida = medidas.get(m["id"])
        if medida and not medida["habilitado"]:
            continue
        m["ancho"] = medida["ancho"] if medida else None
        m["largo"] = medida["largo"] if medida else None
        visibles.append(m)
    return visibles


@app.get("/precios")
async def precios_servicios():
    try:
        return await asyncio.to_thread(odoo_client.obtener_precios_servicios)
    except odoo_client.OdooError:
        return {"corte": None, "canto": None}


@app.get("/pedido/{solicitud_id}", response_class=HTMLResponse)
async def ver_pedido(request: Request, solicitud_id: int):
    solicitud = await db.obtener_solicitud(solicitud_id)
    if not solicitud:
        return templates.TemplateResponse(
            request, "pedido_no_encontrado.html", {}, status_code=404
        )
    return templates.TemplateResponse(
        request,
        "ver_pedido.html",
        {
            "solicitud": solicitud,
            "estado_label": ESTADOS_LABELS.get(solicitud["estado"], solicitud["estado"]),
            "etapa_label": ETAPAS_LABELS.get(solicitud["etapa_produccion"]),
            "whatsapp_number": config.WHATSAPP_NUMBER,
            "clever_site_url": config.CLEVER_SITE_URL,
        },
    )


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


@app.get("/dashboard/precios", response_class=HTMLResponse)
async def precios_page(request: Request):
    if not sesion_activa(request):
        return templates.TemplateResponse(request, "login.html")

    error = None
    materiales = []
    servicios = {"corte": None, "canto": None}
    try:
        materiales = await asyncio.to_thread(odoo_client.listar_materiales)
        servicios = await asyncio.to_thread(odoo_client.obtener_precios_servicios)
    except odoo_client.OdooError as exc:
        error = str(exc)

    medidas = await db.listar_medidas_materiales()
    for m in materiales:
        medida = medidas.get(m["id"])
        m["ancho"] = medida["ancho"] if medida else None
        m["largo"] = medida["largo"] if medida else None
        m["habilitado"] = bool(medida["habilitado"]) if medida else True

    return templates.TemplateResponse(
        request, "precios.html", {"materiales": materiales, "servicios": servicios, "error": error}
    )


@app.post("/dashboard/precios/medidas", dependencies=[Depends(requerir_sesion)])
async def guardar_medida_material_endpoint(datos: MedidaMaterialIn):
    await db.guardar_medida_material(
        datos.odoo_id, datos.nombre, datos.ancho, datos.largo, datos.habilitado
    )
    return {"ok": True}


@app.post("/dashboard/extraer-piezas", dependencies=[Depends(requerir_sesion)])
async def extraer_piezas_endpoint(imagen: UploadFile = File(...)):
    contenido = await imagen.read()
    if len(contenido) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="La imagen es demasiado grande (máx 10 MB)")

    media_type = imagen.content_type or "image/jpeg"
    try:
        piezas = await asyncio.to_thread(vision_extract.extraer_piezas, contenido, media_type)
    except vision_extract.ExtraccionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"piezas": piezas}


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


@app.get("/dashboard/solicitudes/nueva", response_class=HTMLResponse)
async def nueva_solicitud_page(request: Request):
    if not sesion_activa(request):
        return templates.TemplateResponse(request, "login.html")

    try:
        materiales = await asyncio.to_thread(odoo_client.listar_materiales)
    except odoo_client.OdooError:
        materiales = []
    if not materiales:
        materiales = [{"id": None, "nombre": "MDF"}, {"id": None, "nombre": "Acrilico"}]

    return templates.TemplateResponse(request, "nueva_solicitud.html", {"materiales": materiales})


@app.post("/dashboard/solicitudes", dependencies=[Depends(requerir_sesion)])
async def crear_solicitud_staff(datos: SolicitudCorteIn):
    solicitud_id = await _crear_solicitud(datos)
    return {"ok": True, "id": solicitud_id}


@app.get("/dashboard/solicitudes/{solicitud_id}", response_class=HTMLResponse)
async def editar_solicitud_page(request: Request, solicitud_id: int):
    if not sesion_activa(request):
        return templates.TemplateResponse(request, "login.html")
    solicitud = await obtener_o_404(solicitud_id)

    try:
        materiales = await asyncio.to_thread(odoo_client.listar_materiales)
    except odoo_client.OdooError:
        materiales = []
    if not materiales:
        materiales = [{"id": None, "nombre": "MDF"}, {"id": None, "nombre": "Acrilico"}]

    placas_necesarias = None
    if solicitud.get("con_material") and solicitud.get("material_id"):
        medida = await db.obtener_medida_material(solicitud["material_id"])
        if medida and medida["ancho"] and medida["largo"]:
            placas_necesarias = calculos.cantidad_placas(solicitud["cortes"], medida["ancho"], medida["largo"])

    return templates.TemplateResponse(
        request,
        "detalle.html",
        {"solicitud": solicitud, "materiales": materiales, "placas_necesarias": placas_necesarias},
    )


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
    if solicitud["estado"] == "cancelada":
        raise HTTPException(status_code=409, detail="No se puede enviar a Odoo una solicitud cancelada")

    solicitud = await _preparar_solicitud_para_odoo(solicitud)
    try:
        resultado = await asyncio.to_thread(odoo_client.crear_presupuesto, solicitud)
    except odoo_client.OdooError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    await db.guardar_odoo_pedido(solicitud_id, resultado["odoo_pedido_id"], resultado["odoo_pedido_nombre"])
    return {"ok": True, **resultado}
