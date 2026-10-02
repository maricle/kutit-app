"""Hoja de etiquetas para imprimir y pegar sobre cada pieza cortada.
Portado de Kutit Adrian (kutit_kleba/src/kutit/etiquetas_export.py) — único
cambio de fondo: genera el PDF en memoria en vez de a disco.

Una etiqueta por pieza física colocada (no por grupo/código): nombre, qué
copia es ("N° 2 de 5"), medida final y el código de su corte como
referencia rápida. Hojas A4, grilla de 3x7, con guía punteada para recortar.
"""

from __future__ import annotations

import io

from . import colores
from .modelos import PiezaColocada, Resultado

_PAGINA_ANCHO_MM = 210.0
_PAGINA_ALTO_MM = 297.0
_MARGEN_MM = 10.0
_ESPACIO_MM = 3.0
_COLUMNAS = 3
_FILAS = 7
_POR_PAGINA = _COLUMNAS * _FILAS

_ANCHO_ETIQUETA_MM = (_PAGINA_ANCHO_MM - 2 * _MARGEN_MM - (_COLUMNAS - 1) * _ESPACIO_MM) / _COLUMNAS
_ALTO_ETIQUETA_MM = (_PAGINA_ALTO_MM - 2 * _MARGEN_MM - (_FILAS - 1) * _ESPACIO_MM) / _FILAS


def _piezas_a_etiquetar(resultado: Resultado) -> list[tuple[str, PiezaColocada]]:
    codigos = colores.codigos_grupo(resultado)
    piezas: list[tuple[str, PiezaColocada]] = []
    for placa in resultado.placas:
        for pc in placa.piezas:
            clave = colores.clave_grupo(pc.pieza.nombre_base, pc.pieza.largo_final, pc.pieza.ancho_final)
            piezas.append((codigos.get(clave, "?"), pc))
    piezas.sort(key=lambda t: (t[0], t[1].pieza.nombre_base, t[1].pieza.indice_en_grupo))
    return piezas


def _dibujar_etiqueta(ax, x0: float, y0: float, codigo: str, pc: PiezaColocada, color_hex: str) -> None:
    from matplotlib.patches import Rectangle

    p = pc.pieza
    ancho, alto = _ANCHO_ETIQUETA_MM, _ALTO_ETIQUETA_MM

    ax.add_patch(
        Rectangle((x0, y0), ancho, alto, facecolor="white", edgecolor="#AAAAAA",
                   linewidth=0.6, linestyle=(0, (2, 2)))
    )

    pad = 3.0
    y = y0 + alto - pad - 4.0

    ax.text(x0 + pad, y, codigo, fontsize=15, fontweight="bold", color=color_hex, ha="left", va="top")
    ax.text(x0 + ancho - pad, y, f"N° {p.indice_en_grupo} de {p.cantidad_en_grupo}",
            fontsize=8, color="#444444", ha="right", va="top")

    y -= 8.5
    tamano_nombre = 10.5 if len(p.nombre_base) <= 16 else 8.5
    ax.text(x0 + pad, y, p.nombre_base, fontsize=tamano_nombre, fontweight="bold", ha="left", va="top", wrap=True)

    y -= 7.0
    marca_rot = " (rotada 90°)" if pc.rotada else ""
    ax.text(x0 + pad, y, f"{p.largo_final:g} x {p.ancho_final:g} mm{marca_rot}", fontsize=9, ha="left", va="top")


def generar_etiquetas_bytes(resultado: Resultado) -> bytes | None:
    """Genera la hoja de etiquetas en memoria. None si no hay piezas
    colocadas (no tiene sentido un PDF de etiquetas vacío)."""
    piezas = _piezas_a_etiquetar(resultado)
    if not piezas:
        return None

    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    colores_grupo = colores.asignar_colores_grupo(resultado)
    buffer = io.BytesIO()

    with PdfPages(buffer) as pdf:
        for inicio in range(0, len(piezas), _POR_PAGINA):
            lote = piezas[inicio: inicio + _POR_PAGINA]

            fig, ax = plt.subplots(figsize=(_PAGINA_ANCHO_MM / 25.4, _PAGINA_ALTO_MM / 25.4))
            ax.set_xlim(0, _PAGINA_ANCHO_MM)
            ax.set_ylim(0, _PAGINA_ALTO_MM)
            ax.set_aspect("equal")
            ax.axis("off")
            fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

            for indice, (codigo, pc) in enumerate(lote):
                fila, col = divmod(indice, _COLUMNAS)
                x0 = _MARGEN_MM + col * (_ANCHO_ETIQUETA_MM + _ESPACIO_MM)
                y0 = _PAGINA_ALTO_MM - _MARGEN_MM - (fila + 1) * _ALTO_ETIQUETA_MM - fila * _ESPACIO_MM
                clave = colores.clave_grupo(pc.pieza.nombre_base, pc.pieza.largo_final, pc.pieza.ancho_final)
                _dibujar_etiqueta(ax, x0, y0, codigo, pc, colores_grupo[clave])

            pdf.savefig(fig)
            plt.close(fig)

    return buffer.getvalue()
