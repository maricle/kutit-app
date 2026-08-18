import os

import libsql_client

import config

_client = None

SCHEMA_SOLICITUDES = """
CREATE TABLE IF NOT EXISTS solicitudes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contacto TEXT NOT NULL,
    telefono TEXT NOT NULL,
    email TEXT,
    fecha TEXT,
    material TEXT,
    estado TEXT NOT NULL DEFAULT 'esperando_confirmacion_whatsapp',
    etapa_produccion TEXT,
    motivo_cancelacion TEXT,
    creado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

SCHEMA_LINEAS = """
CREATE TABLE IF NOT EXISTS lineas_corte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    solicitud_id INTEGER NOT NULL REFERENCES solicitudes(id),
    descripcion TEXT,
    cantidad INTEGER DEFAULT 1,
    alto INTEGER,
    ancho INTEGER,
    canto_1 INTEGER DEFAULT 0,
    canto_2 INTEGER DEFAULT 0,
    canto_3 INTEGER DEFAULT 0,
    canto_4 INTEGER DEFAULT 0,
    rotar INTEGER DEFAULT 1
);
"""


async def get_client():
    global _client
    if _client is None:
        if config.TURSO_URL:
            url = config.TURSO_URL
        else:
            os.makedirs(os.path.dirname(config.LOCAL_DB_PATH) or ".", exist_ok=True)
            url = f"file:{config.LOCAL_DB_PATH}"
        _client = libsql_client.create_client(url=url, auth_token=config.TURSO_TOKEN)
    return _client


async def init_db():
    client = await get_client()
    await client.execute(SCHEMA_SOLICITUDES)
    await client.execute(SCHEMA_LINEAS)


async def close_db():
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def _rows_a_dicts(rs):
    return [dict(zip(rs.columns, fila)) for fila in rs.rows]


async def crear_solicitud(datos) -> int:
    client = await get_client()
    rs = await client.execute(
        """INSERT INTO solicitudes (contacto, telefono, email, fecha, material, estado)
           VALUES (?, ?, ?, ?, ?, 'esperando_confirmacion_whatsapp')
           RETURNING id""",
        [datos.contacto, datos.telefono, datos.email, datos.fecha, datos.material],
    )
    solicitud_id = rs.rows[0][0]
    for c in datos.cortes:
        await client.execute(
            """INSERT INTO lineas_corte
               (solicitud_id, descripcion, cantidad, alto, ancho, canto_1, canto_2, canto_3, canto_4, rotar)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                solicitud_id, c.descripcion, c.cantidad, c.alto, c.ancho,
                int(c.canto_1), int(c.canto_2), int(c.canto_3), int(c.canto_4), int(c.rotar),
            ],
        )
    return solicitud_id


async def obtener_solicitud(solicitud_id: int):
    client = await get_client()
    rs = await client.execute("SELECT * FROM solicitudes WHERE id = ?", [solicitud_id])
    filas = _rows_a_dicts(rs)
    if not filas:
        return None
    solicitud = filas[0]
    rs_lineas = await client.execute(
        "SELECT * FROM lineas_corte WHERE solicitud_id = ? ORDER BY id", [solicitud_id]
    )
    solicitud["cortes"] = _rows_a_dicts(rs_lineas)
    return solicitud


async def listar_solicitudes():
    client = await get_client()
    rs = await client.execute("SELECT * FROM solicitudes ORDER BY creado_en DESC")
    return _rows_a_dicts(rs)


async def actualizar_solicitud(solicitud_id: int, datos):
    client = await get_client()
    campos, valores = [], []
    for campo in ("contacto", "telefono", "email", "fecha", "material"):
        valor = getattr(datos, campo, None)
        if valor is not None:
            campos.append(f"{campo} = ?")
            valores.append(valor)
    if campos:
        valores.append(solicitud_id)
        await client.execute(f"UPDATE solicitudes SET {', '.join(campos)} WHERE id = ?", valores)

    if datos.cortes is not None:
        await client.execute("DELETE FROM lineas_corte WHERE solicitud_id = ?", [solicitud_id])
        for c in datos.cortes:
            await client.execute(
                """INSERT INTO lineas_corte
                   (solicitud_id, descripcion, cantidad, alto, ancho, canto_1, canto_2, canto_3, canto_4, rotar)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    solicitud_id, c.descripcion, c.cantidad, c.alto, c.ancho,
                    int(c.canto_1), int(c.canto_2), int(c.canto_3), int(c.canto_4), int(c.rotar),
                ],
            )


async def confirmar_solicitud(solicitud_id: int):
    client = await get_client()
    await client.execute(
        "UPDATE solicitudes SET estado = 'confirmada', etapa_produccion = 'por_hacer' WHERE id = ?",
        [solicitud_id],
    )


async def cancelar_solicitud(solicitud_id: int, motivo: str | None):
    client = await get_client()
    await client.execute(
        "UPDATE solicitudes SET estado = 'cancelada', motivo_cancelacion = ? WHERE id = ?",
        [motivo, solicitud_id],
    )


async def mover_etapa(solicitud_id: int, etapa: str):
    client = await get_client()
    await client.execute(
        "UPDATE solicitudes SET etapa_produccion = ? WHERE id = ?", [etapa, solicitud_id]
    )


async def eliminar_solicitud(solicitud_id: int):
    client = await get_client()
    await client.execute("DELETE FROM lineas_corte WHERE solicitud_id = ?", [solicitud_id])
    await client.execute("DELETE FROM solicitudes WHERE id = ?", [solicitud_id])
