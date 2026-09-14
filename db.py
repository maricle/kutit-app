import asyncpg

import config

_pool: asyncpg.Pool | None = None

SCHEMA_SOLICITUDES = """
CREATE TABLE IF NOT EXISTS solicitudes (
    id SERIAL PRIMARY KEY,
    contacto TEXT NOT NULL,
    telefono TEXT NOT NULL,
    email TEXT,
    fecha TEXT,
    con_material INTEGER NOT NULL DEFAULT 1,
    material TEXT,
    estado TEXT NOT NULL DEFAULT 'esperando_confirmacion_whatsapp',
    etapa_produccion TEXT,
    motivo_cancelacion TEXT,
    odoo_pedido_id INTEGER,
    odoo_pedido_nombre TEXT,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

SCHEMA_LINEAS = """
CREATE TABLE IF NOT EXISTS lineas_corte (
    id SERIAL PRIMARY KEY,
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

SCHEMA_MEDIDAS_MATERIAL = """
CREATE TABLE IF NOT EXISTS medidas_material (
    odoo_id INTEGER PRIMARY KEY,
    nombre TEXT,
    ancho INTEGER,
    largo INTEGER,
    habilitado INTEGER NOT NULL DEFAULT 1
);
"""

SCHEMA_MATERIALES_MANUALES = """
CREATE TABLE IF NOT EXISTS materiales_manuales (
    id SERIAL PRIMARY KEY,
    categoria TEXT NOT NULL DEFAULT 'material',
    nombre TEXT NOT NULL,
    precio NUMERIC,
    ancho INTEGER,
    largo INTEGER,
    habilitado INTEGER NOT NULL DEFAULT 1
);
"""


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=config.DATABASE_URL)
    return _pool


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as con:
        await con.execute(SCHEMA_SOLICITUDES)
        await con.execute(SCHEMA_LINEAS)
        await con.execute(SCHEMA_MEDIDAS_MATERIAL)
        await con.execute(SCHEMA_MATERIALES_MANUALES)
        for columna in (
            "odoo_pedido_id INTEGER",
            "odoo_pedido_nombre TEXT",
            "con_material INTEGER NOT NULL DEFAULT 1",
            "material_id INTEGER",
            "material_manual_id INTEGER",
        ):
            await con.execute(f"ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS {columna}")
        await con.execute(
            "ALTER TABLE medidas_material ADD COLUMN IF NOT EXISTS habilitado INTEGER NOT NULL DEFAULT 1"
        )
        await con.execute(
            "ALTER TABLE medidas_material ADD COLUMN IF NOT EXISTS precio_manual NUMERIC"
        )
        await con.execute(
            "ALTER TABLE materiales_manuales ADD COLUMN IF NOT EXISTS categoria TEXT NOT NULL DEFAULT 'material'"
        )


async def close_db():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _rows_a_dicts(rows):
    return [dict(r) for r in rows]


async def crear_solicitud(datos) -> int:
    pool = await get_pool()
    async with pool.acquire() as con, con.transaction():
        solicitud_id = await con.fetchval(
            """INSERT INTO solicitudes
               (contacto, telefono, email, fecha, con_material, material, material_id, material_manual_id, estado)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'esperando_confirmacion_whatsapp')
               RETURNING id""",
            datos.contacto, datos.telefono, datos.email, datos.fecha,
            int(datos.con_material), datos.material, datos.material_id, datos.material_manual_id,
        )
        for c in datos.cortes:
            await con.execute(
                """INSERT INTO lineas_corte
                   (solicitud_id, descripcion, cantidad, alto, ancho, canto_1, canto_2, canto_3, canto_4, rotar)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                solicitud_id, c.descripcion, c.cantidad, c.alto, c.ancho,
                int(c.canto_1), int(c.canto_2), int(c.canto_3), int(c.canto_4), int(c.rotar),
            )
    return solicitud_id


async def obtener_solicitud(solicitud_id: int):
    pool = await get_pool()
    fila = await pool.fetchrow("SELECT * FROM solicitudes WHERE id = $1", solicitud_id)
    if not fila:
        return None
    solicitud = dict(fila)
    lineas = await pool.fetch(
        "SELECT * FROM lineas_corte WHERE solicitud_id = $1 ORDER BY id", solicitud_id
    )
    solicitud["cortes"] = _rows_a_dicts(lineas)
    return solicitud


async def listar_solicitudes():
    pool = await get_pool()
    filas = await pool.fetch("SELECT * FROM solicitudes ORDER BY creado_en DESC")
    return _rows_a_dicts(filas)


async def actualizar_solicitud(solicitud_id: int, datos):
    pool = await get_pool()
    async with pool.acquire() as con, con.transaction():
        campos, valores = [], []
        for campo in ("contacto", "telefono", "email", "fecha"):
            valor = getattr(datos, campo, None)
            if valor is not None:
                valores.append(valor)
                campos.append(f"{campo} = ${len(valores)}")
        if datos.con_material is not None:
            # material/material_id/material_manual_id sólo tienen sentido junto con
            # con_material, y a diferencia de los campos de arriba sí necesitan poder
            # limpiarse a NULL (ej. al pasar de un material de Odoo a uno manual) —
            # por eso van siempre los cuatro juntos en vez de saltear los que sean None.
            valores.append(int(datos.con_material))
            campos.append(f"con_material = ${len(valores)}")
            valores.append(datos.material)
            campos.append(f"material = ${len(valores)}")
            valores.append(datos.material_id)
            campos.append(f"material_id = ${len(valores)}")
            valores.append(datos.material_manual_id)
            campos.append(f"material_manual_id = ${len(valores)}")
        if campos:
            valores.append(solicitud_id)
            await con.execute(
                f"UPDATE solicitudes SET {', '.join(campos)} WHERE id = ${len(valores)}", *valores
            )

        if datos.cortes is not None:
            await con.execute("DELETE FROM lineas_corte WHERE solicitud_id = $1", solicitud_id)
            for c in datos.cortes:
                await con.execute(
                    """INSERT INTO lineas_corte
                       (solicitud_id, descripcion, cantidad, alto, ancho, canto_1, canto_2, canto_3, canto_4, rotar)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                    solicitud_id, c.descripcion, c.cantidad, c.alto, c.ancho,
                    int(c.canto_1), int(c.canto_2), int(c.canto_3), int(c.canto_4), int(c.rotar),
                )


async def confirmar_solicitud(solicitud_id: int):
    pool = await get_pool()
    await pool.execute(
        "UPDATE solicitudes SET estado = 'confirmada', etapa_produccion = 'por_hacer' WHERE id = $1",
        solicitud_id,
    )


async def cancelar_solicitud(solicitud_id: int, motivo: str | None):
    pool = await get_pool()
    await pool.execute(
        "UPDATE solicitudes SET estado = 'cancelada', motivo_cancelacion = $1 WHERE id = $2",
        motivo, solicitud_id,
    )


async def mover_etapa(solicitud_id: int, etapa: str):
    pool = await get_pool()
    await pool.execute("UPDATE solicitudes SET etapa_produccion = $1 WHERE id = $2", etapa, solicitud_id)


async def eliminar_solicitud(solicitud_id: int):
    pool = await get_pool()
    async with pool.acquire() as con, con.transaction():
        await con.execute("DELETE FROM lineas_corte WHERE solicitud_id = $1", solicitud_id)
        await con.execute("DELETE FROM solicitudes WHERE id = $1", solicitud_id)


async def guardar_odoo_pedido(solicitud_id: int, odoo_pedido_id: int, odoo_pedido_nombre: str):
    pool = await get_pool()
    await pool.execute(
        "UPDATE solicitudes SET odoo_pedido_id = $1, odoo_pedido_nombre = $2 WHERE id = $3",
        odoo_pedido_id, odoo_pedido_nombre, solicitud_id,
    )


async def listar_medidas_materiales():
    pool = await get_pool()
    filas = await pool.fetch("SELECT * FROM medidas_material")
    return {f["odoo_id"]: dict(f) for f in filas}


async def obtener_medida_material(odoo_id: int):
    pool = await get_pool()
    fila = await pool.fetchrow("SELECT * FROM medidas_material WHERE odoo_id = $1", odoo_id)
    return dict(fila) if fila else None


async def eliminar_medida_material(odoo_id: int):
    pool = await get_pool()
    await pool.execute("DELETE FROM medidas_material WHERE odoo_id = $1", odoo_id)


async def guardar_medida_material(
    odoo_id: int,
    nombre: str,
    ancho: int | None,
    largo: int | None,
    habilitado: bool,
    precio_manual: float | None = None,
):
    pool = await get_pool()
    await pool.execute(
        """INSERT INTO medidas_material (odoo_id, nombre, ancho, largo, habilitado, precio_manual)
           VALUES ($1, $2, $3, $4, $5, $6)
           ON CONFLICT (odoo_id) DO UPDATE SET nombre = $2, ancho = $3, largo = $4, habilitado = $5, precio_manual = $6""",
        odoo_id, nombre, ancho, largo, int(habilitado), precio_manual,
    )


async def listar_materiales_manuales():
    pool = await get_pool()
    filas = await pool.fetch("SELECT * FROM materiales_manuales ORDER BY id")
    return _rows_a_dicts(filas)


async def obtener_material_manual(material_id: int):
    pool = await get_pool()
    fila = await pool.fetchrow("SELECT * FROM materiales_manuales WHERE id = $1", material_id)
    return dict(fila) if fila else None


async def guardar_material_manual(
    material_id: int | None,
    categoria: str,
    nombre: str,
    precio: float,
    ancho: int | None,
    largo: int | None,
    habilitado: bool,
) -> int:
    pool = await get_pool()
    if material_id is None:
        return await pool.fetchval(
            """INSERT INTO materiales_manuales (categoria, nombre, precio, ancho, largo, habilitado)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
            categoria, nombre, precio, ancho, largo, int(habilitado),
        )
    await pool.execute(
        """UPDATE materiales_manuales
           SET categoria = $2, nombre = $3, precio = $4, ancho = $5, largo = $6, habilitado = $7
           WHERE id = $1""",
        material_id, categoria, nombre, precio, ancho, largo, int(habilitado),
    )
    return material_id


async def eliminar_material_manual(material_id: int):
    pool = await get_pool()
    await pool.execute("DELETE FROM materiales_manuales WHERE id = $1", material_id)
