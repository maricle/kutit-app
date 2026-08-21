import xmlrpc.client

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


def _buscar_producto_por_code(models, uid, code):
    ids = _llamar(models, uid, "product.product", "search", [["default_code", "=", code]], limit=1)
    return ids[0] if ids else None


def _buscar_producto_por_nombre(models, uid, nombre):
    ids = _llamar(models, uid, "product.product", "search", [["name", "=", nombre]], limit=1)
    return ids[0] if ids else None


def _buscar_o_crear_partner(models, uid, solicitud):
    telefono = solicitud.get("telefono")
    if telefono:
        ids = _llamar(models, uid, "res.partner", "search", [["phone", "=", telefono]], limit=1)
        if ids:
            return ids[0]
    return _llamar(
        models, uid, "res.partner", "create",
        {
            "name": solicitud["contacto"],
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


def crear_presupuesto(solicitud: dict) -> dict:
    uid, models = _conectar()

    producto_corte_id = _buscar_producto_por_code(models, uid, config.ODOO_PRODUCT_CORTE_CODE)
    if not producto_corte_id:
        raise OdooError(
            f"No se encontró en Odoo el producto con código '{config.ODOO_PRODUCT_CORTE_CODE}'"
        )

    partner_id = _buscar_o_crear_partner(models, uid, solicitud)

    cortes = solicitud["cortes"]
    total_piezas = sum(c["cantidad"] for c in cortes) or 1
    total_cantos = sum(
        c["cantidad"] * sum([bool(c["canto_1"]), bool(c["canto_2"]), bool(c["canto_3"]), bool(c["canto_4"])])
        for c in cortes
    )

    lineas_pedido = [(0, 0, {
        "product_id": producto_corte_id,
        "product_uom_qty": total_piezas,
        "name": f"Servicio de corte CNC - Solicitud #{solicitud['id']}\n{_describir_cortes(cortes)}",
    })]

    if total_cantos > 0:
        producto_canto_id = _buscar_producto_por_nombre(models, uid, config.ODOO_PRODUCT_CANTO_NOMBRE)
        if producto_canto_id:
            lineas_pedido.append((0, 0, {
                "product_id": producto_canto_id,
                "product_uom_qty": total_cantos,
                "name": config.ODOO_PRODUCT_CANTO_NOMBRE,
            }))

    pedido_id = _llamar(
        models, uid, "sale.order", "create",
        {"partner_id": partner_id, "order_line": lineas_pedido},
    )
    pedido = _llamar(models, uid, "sale.order", "read", [pedido_id], fields=["name"])[0]

    return {"odoo_pedido_id": pedido_id, "odoo_pedido_nombre": pedido["name"]}
