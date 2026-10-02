"""Exportación del plano de corte a DXF, en milímetros, uno por placa.
Portado de Kutit Adrian (kutit_kleba/src/kutit/dxf_export.py) — único cambio
de fondo: genera los DXF en memoria (`generar_dxf_bytes_por_placa`) en vez
de escribirlos a disco, porque acá se descargan por HTTP, no se guardan.

Cada DXF contiene: el contorno de la placa (capa PLACA), el contorno de
cada pieza con su etiqueta de código y su descripción individual (capas
PIEZAS/TEXTO), y una línea por lado con canto en la capa que corresponde a
su espesor (CANTO_045 azul, CANTO_2 rojo, CANTO_OTRO verde) — es el archivo
que se importa en la sierra/CNC.
"""

from __future__ import annotations

import io

import ezdxf
from ezdxf.enums import TextEntityAlignment

from . import colores
from .modelos import Placa, Resultado

CAPA_PLACA = "PLACA"
CAPA_PIEZAS = "PIEZAS"
CAPA_TEXTO = "TEXTO"
CAPA_CANTO_045 = "CANTO_045"
CAPA_CANTO_2 = "CANTO_2"
CAPA_CANTO_OTRO = "CANTO_OTRO"


def _color_truecolor(hex_color: str) -> int:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return ezdxf.colors.rgb2int((r, g, b))


def _capa_de_canto(espesor: float) -> str:
    if abs(espesor - 0.45) < 0.01:
        return CAPA_CANTO_045
    if abs(espesor - 2.0) < 0.01:
        return CAPA_CANTO_2
    return CAPA_CANTO_OTRO


def _crear_documento() -> ezdxf.document.Drawing:
    doc = ezdxf.new(dxfversion="R2010")
    doc.units = ezdxf.units.MM
    doc.header["$INSUNITS"] = ezdxf.units.MM

    doc.layers.add(CAPA_PLACA, color=7)
    doc.layers.add(CAPA_PIEZAS, color=7)
    doc.layers.add(CAPA_TEXTO, color=7)
    doc.layers.add(CAPA_CANTO_045, dxfattribs={"true_color": _color_truecolor(colores.COLORES_CANTO[0.45])})
    doc.layers.add(CAPA_CANTO_2, dxfattribs={"true_color": _color_truecolor(colores.COLORES_CANTO[2.0])})
    doc.layers.add(CAPA_CANTO_OTRO, dxfattribs={"true_color": _color_truecolor(colores.COLOR_CANTO_OTRO)})
    return doc


def _dibujar_placa_dxf(
    doc: ezdxf.document.Drawing,
    placa: Placa,
    codigos_grupo: dict[colores.ClaveGrupo, str],
    conteo_grupo: dict[colores.ClaveGrupo, int],
) -> None:
    msp = doc.modelspace()

    msp.add_lwpolyline(
        [(0, 0), (placa.largo, 0), (placa.largo, placa.ancho), (0, placa.ancho)],
        close=True, dxfattribs={"layer": CAPA_PLACA},
    )

    coordenadas_lado = {
        "abajo": lambda x0, y0, x1, y1: ((x0, y0), (x1, y0)),
        "arriba": lambda x0, y0, x1, y1: ((x0, y1), (x1, y1)),
        "izquierda": lambda x0, y0, x1, y1: ((x0, y0), (x0, y1)),
        "derecha": lambda x0, y0, x1, y1: ((x1, y0), (x1, y1)),
    }

    for pc in placa.piezas:
        x0, y0 = pc.x, pc.y
        x1, y1 = pc.x + pc.ancho_x, pc.y + pc.alto_y

        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": CAPA_PIEZAS})

        p = pc.pieza
        clave = colores.clave_grupo(p.nombre_base, p.largo_final, p.ancho_final)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        alto_texto = max(5.0, min(pc.ancho_x, pc.alto_y) * 0.14)

        texto_codigo = colores.texto_codigo_pieza(pc, codigos_grupo[clave], conteo_grupo[clave])
        entidad_codigo = msp.add_text(texto_codigo, dxfattribs={"layer": CAPA_TEXTO, "height": alto_texto})
        entidad_codigo.set_placement((cx, cy + alto_texto * 0.7), align=TextEntityAlignment.MIDDLE_CENTER)

        entidad_nombre = msp.add_text(p.descripcion, dxfattribs={"layer": CAPA_TEXTO, "height": alto_texto * 0.6})
        entidad_nombre.set_placement((cx, cy - alto_texto * 0.9), align=TextEntityAlignment.MIDDLE_CENTER)

        for lado, espesor in colores.lados_con_canto(pc):
            p1, p2 = coordenadas_lado[lado](x0, y0, x1, y1)
            msp.add_line(p1, p2, dxfattribs={"layer": _capa_de_canto(espesor)})


def generar_dxf_bytes_por_placa(resultado: Resultado) -> list[tuple[str, bytes]]:
    """Genera un DXF por placa en memoria. Devuelve una lista de
    (nombre_de_archivo, bytes), en orden de placa."""
    codigos_grupo = colores.codigos_grupo(resultado)
    conteo_grupo = colores.conteo_grupo(resultado)

    archivos: list[tuple[str, bytes]] = []
    for placa in resultado.placas:
        doc = _crear_documento()
        _dibujar_placa_dxf(doc, placa, codigos_grupo, conteo_grupo)
        buffer = io.StringIO()
        doc.write(buffer)
        archivos.append((f"placa{placa.indice}.dxf", buffer.getvalue().encode("utf-8")))
    return archivos
