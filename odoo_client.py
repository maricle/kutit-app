import xmlrpc.client

import calculos
import config


class OdooError(Exception):
    pass


def _conectar():
    if not (config.ODOO_URL and config.ODOO_DB and config.ODOO_USERNAME and config.ODOO_API_KEY):
        raise OdooError(
            "Falta configurar la conexión a Odoo (ODOO_URL / ODOO_DB / ODOO_USERNAME / ODOO_API_KEY)"
        )
    common = xmlrpc.client.ServerProxy(f"{config.ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(config.ODOO_DB, config.ODOO_USERNAME, config.ODOO_API_KEY, {})
    if not uid:
        raise OdooError("Odoo rechazó las credenciales")
    models = xmlrpc.client.ServerProxy(f"{config.ODOO_URL}/xmlrpc/2/object")
    return uid, models


def _llamar(models, uid, modelo, metodo, *args, **kwargs):
    return models.execute_kw(config.ODOO_DB, uid, config.ODOO_API_KEY, modelo, metodo, list(args), kwargs)


def _buscar_o_crear_partner(models, uid, solicitud: dict) -> int:
    """Identifica al cliente por teléfono: usa el res.partner existente con
    ese teléfono si lo encuentra, o crea uno nuevo. Así Odoo acumula el
    historial real de cada cliente en vez de agrupar todo bajo un partner
    genérico de "Consumidor final"."""
    telefono = (solicitud.get("telefono") or "").strip()
    if telefono:
        encontrados = _llamar(
            models, uid, "res.partner", "search", [["phone", "=", telefono]], limit=1
        )
        if encontrados:
            return encontrados[0]

    return _llamar(
        models, uid, "res.partner", "create",
        {
            "name": solicitud.get("contacto") or telefono or "Cliente web",
            "phone": telefono or False,
            "email": solicitud.get("email") or False,
        },
    )


def _describir_cortes(cortes):
    lineas = []
    for c in cortes:
        cantos = sum([bool(c["canto_1"]), bool(c["canto_2"]), bool(c["canto_3"]), bool(c["canto_4"])])
        detalle = f"- {c['cantidad']} x {c['descripcion'] or 'sin descripción'} ({c['alto']}x{c['ancho']} mm)"
        if cantos:
            detalle += f" - {cantos} canto(s)"
        lineas.append(detalle)
    return "\n".join(lineas)


def _resolver_variante(models, uid, id_dado):
    """Acepta un id de product.template (caso normal: los ids que configuramos
    y los que devuelve listar_materiales son de product.template) o, si no
    existe como plantilla, de product.product. Devuelve (id de product.product,
    list_price).

    Importante: product.product y product.template tienen secuencias de id
    independientes, así que un mismo número puede existir en los dos modelos
    apuntando a productos distintos — por eso hay que resolver primero por
    product.template (que es el caso real) y no al revés."""
    plantillas = _llamar(
        models, uid, "product.template", "read", [id_dado],
        fields=["list_price", "product_variant_id"],
    )
    if plantillas and plantillas[0].get("product_variant_id"):
        return plantillas[0]["product_variant_id"][0], plantillas[0]["list_price"]

    variantes = _llamar(models, uid, "product.product", "read", [id_dado], fields=["list_price"])
    if variantes:
        return id_dado, variantes[0]["list_price"]

    return None, None


def listar_materiales() -> list[dict]:
    uid, models = _conectar()
    productos = _llamar(
        models, uid, "product.template", "search_read",
        [
            ["public_categ_ids", "in", [config.ODOO_CATEGORIA_MATERIALES_ID]],
            ["sale_ok", "=", True],
            ["is_published", "=", True],
        ],
        fields=["id", "name", "list_price"],
    )
    return [{"id": p["id"], "nombre": p["name"], "precio": p["list_price"]} for p in productos]


def obtener_precios_servicios() -> dict:
    uid, models = _conectar()
    _, precio_corte = _resolver_variante(models, uid, config.ODOO_PRODUCT_CORTE_ID)
    _, precio_canto = _resolver_variante(models, uid, config.ODOO_PRODUCT_CANTO_ID)
    return {"corte": precio_corte, "canto": precio_canto}


#: Estados de sale.order en los que la cotización todavía no se confirmó
#: como venta — en estos casos "reenviar" actualiza la misma cotización en
#: vez de duplicarla. "sale"/"done" (ya confirmada) o "cancel" quedan afuera
#: a propósito: no se pisa una venta ya cerrada.
_ESTADOS_NO_CONFIRMADOS = ("draft", "sent")


def _estado_pedido_existente(models, uid, pedido_id: int) -> str | None:
    """Estado actual de una cotización ya enviada, o None si ya no existe
    en Odoo (se borró a mano)."""
    try:
        registros = _llamar(models, uid, "sale.order", "read", [pedido_id], fields=["state"])
    except xmlrpc.client.Fault:
        return None
    return registros[0]["state"] if registros else None


def crear_presupuesto(solicitud: dict) -> dict:
    uid, models = _conectar()

    producto_corte_id, _ = _resolver_variante(models, uid, config.ODOO_PRODUCT_CORTE_ID)
    if not producto_corte_id:
        raise OdooError(
            f"No se encontró en Odoo el producto de corte (id {config.ODOO_PRODUCT_CORTE_ID})"
        )

    cortes = solicitud["cortes"]
    total_metros_corte = calculos.metros_corte(cortes)
    total_metros_canto = calculos.metros_canto(cortes)

    lineas_valores = [{
        "product_id": producto_corte_id,
        "product_uom_qty": round(total_metros_corte, 2),
        "name": f"Servicio de corte CNC - Solicitud #{solicitud['id']}\n{_describir_cortes(cortes)}",
    }]

    if total_metros_canto > 0:
        producto_canto_id, _ = _resolver_variante(models, uid, config.ODOO_PRODUCT_CANTO_ID)
        if producto_canto_id:
            lineas_valores.append({
                "product_id": producto_canto_id,
                "product_uom_qty": round(total_metros_canto, 2),
                "name": "Servicio de pegado de canto Simple",
            })

    material_odoo_id = solicitud.get("material_odoo_id")
    material_ancho = solicitud.get("material_ancho")
    material_largo = solicitud.get("material_largo")
    if material_odoo_id and material_ancho and material_largo:
        placas = calculos.cantidad_placas(cortes, material_ancho, material_largo)
        if placas > 0:
            producto_material_id, _ = _resolver_variante(models, uid, material_odoo_id)
            if producto_material_id:
                lineas_valores.append({
                    "product_id": producto_material_id,
                    "product_uom_qty": placas,
                    "name": solicitud.get("material") or "Placa",
                })

    partner_id = _buscar_o_crear_partner(models, uid, solicitud)
    titulo = f"{solicitud['contacto']} - {solicitud['telefono']}"

    pedido_existente_id = solicitud.get("odoo_pedido_id")
    if pedido_existente_id:
        estado = _estado_pedido_existente(models, uid, pedido_existente_id)
        if estado in _ESTADOS_NO_CONFIRMADOS:
            # Todavía es una cotización sin confirmar: se actualiza en vez
            # de crear una duplicada. (5, 0, 0) borra las líneas actuales
            # antes de agregar las nuevas, en el mismo write.
            _llamar(
                models, uid, "sale.order", "write", [pedido_existente_id],
                {
                    "partner_id": partner_id,
                    "x_studio_titulo": titulo,
                    "order_line": [(5, 0, 0)] + [(0, 0, v) for v in lineas_valores],
                },
            )
            pedido = _llamar(models, uid, "sale.order", "read", [pedido_existente_id], fields=["name"])[0]
            return {"odoo_pedido_id": pedido_existente_id, "odoo_pedido_nombre": pedido["name"]}
        # Ya confirmada (o cancelada/borrada): no se toca, se crea una nueva abajo.

    pedido_id = _llamar(
        models, uid, "sale.order", "create",
        {
            "partner_id": partner_id,
            "x_studio_titulo": titulo,
            "order_line": [(0, 0, v) for v in lineas_valores],
        },
    )
    pedido = _llamar(models, uid, "sale.order", "read", [pedido_id], fields=["name"])[0]

    return {"odoo_pedido_id": pedido_id, "odoo_pedido_nombre": pedido["name"]}
