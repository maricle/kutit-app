"""Exportación de la orden de corte a PDF. Portado de Kutit Adrian
(kutit_kleba/src/kutit/pdf_export.py), sin cambios de lógica.

1. Página de cabecera: datos de la orden, tabla de cortes (código, nombre,
   medidas, cantidad) y las dos formas de facturar (metro lineal / cantidad
   de cortes), más los metros de tapacanto a pedir.
2. Una página por placa, reutilizando `visualizacion.dibujar_placa`.

Se arma con `matplotlib.backends.backend_pdf.PdfPages` para no sumar una
librería de PDF aparte.
"""

from __future__ import annotations

import io

from . import colores
from .modelos import Config, Resultado
from .resumen import agrupar_cortes_principales, cantidad_cortes, metros_lineales_canto, metros_lineales_corte
from .visualizacion import dibujar_placa

_ANCHO_MAX_NOMBRE = 22
_X0, _X1 = 0.06, 0.94


def _linea_h(ax, y: float, x0: float = _X0, x1: float = _X1, **kw) -> None:
    ax.plot([x0, x1], [y, y], color="black", linewidth=kw.pop("linewidth", 0.6), **kw)


def _tabla_cortes(ax, y0: float, resultado: Resultado) -> float:
    from matplotlib.colors import to_rgba
    from matplotlib.patches import Rectangle

    x_codigo, x_nombre, x_medidas, x_cant = _X0, 0.20, 0.52, 0.76
    columnas = (x_codigo, x_nombre, x_medidas, x_cant, _X1)
    alto_header = 0.032
    alto_fila = 0.030

    y = y0
    ax.text(_X0, y, "Cortes", fontsize=13, fontweight="bold")
    y -= 0.028

    y_top = y
    ax.add_patch(Rectangle((_X0, y_top - alto_header), _X1 - _X0, alto_header, facecolor="#EEEEEE", edgecolor="none", zorder=1))
    y_texto = y_top - alto_header * 0.68
    for x, titulo in zip(columnas[:-1], ("CÓDIGO", "NOMBRE", "MEDIDAS", "#")):
        ax.text(x + 0.008, y_texto, titulo, fontsize=9.5, fontweight="bold", zorder=2)
    y = y_top - alto_header

    grupos = agrupar_cortes_principales(resultado)
    filas_mostradas = 0
    for indice, grupo in enumerate(grupos):
        if y - alto_fila < 0.06:
            ax.text(_X0 + 0.008, y - alto_fila * 0.68, f"… y {len(grupos) - indice} corte(s) más", fontsize=8)
            y -= alto_fila
            break

        nombre = grupo.nombre
        if len(nombre) > _ANCHO_MAX_NOMBRE:
            nombre = nombre[: _ANCHO_MAX_NOMBRE - 1] + "…"

        y_texto = y - alto_fila * 0.68
        ax.add_patch(
            Rectangle(
                (x_codigo + 0.008, y_texto - 0.004), 0.014, 0.014,
                facecolor=to_rgba(grupo.color_hex, colores.ALPHA_GRUPO), edgecolor="black", linewidth=0.4, zorder=2,
            )
        )
        ax.text(x_codigo + 0.030, y_texto, grupo.codigo, fontsize=9.5, fontweight="bold", zorder=2)
        ax.text(x_nombre + 0.008, y_texto, nombre, fontsize=9.5, zorder=2)
        ax.text(x_medidas + 0.008, y_texto, f"{grupo.largo:g}x{grupo.ancho:g}", fontsize=9.5, zorder=2)
        ax.text(x_cant + 0.008, y_texto, f"{grupo.cantidad} UNI", fontsize=9.5, zorder=2)
        y -= alto_fila
        filas_mostradas += 1

    y_fin = y

    _linea_h(ax, y_top)
    _linea_h(ax, y_top - alto_header)
    for i in range(filas_mostradas):
        _linea_h(ax, y_top - alto_header - alto_fila * (i + 1), linewidth=0.4)
    for x in columnas:
        ax.plot([x, x], [y_fin, y_top], color="black", linewidth=0.6)

    return y_fin - 0.02


def _tabla_metricas(ax, y0: float, resultado: Resultado) -> float:
    filas = (
        ("Metros Lineales", f"{metros_lineales_corte(resultado):.2f}", "mts"),
        ("Cantidad de Cortes", f"{cantidad_cortes(resultado)}", "Unidades"),
        ("Metros de Tapacantos", f"{metros_lineales_canto(resultado):.2f}", "mts"),
    )
    x_label, x_valor, x_unidad = _X0, 0.42, 0.56
    columnas = (x_label, x_valor, x_unidad, 0.70)
    alto_fila = 0.032

    y = y0
    for etiqueta, valor, unidad in filas:
        y_texto = y - alto_fila * 0.68
        ax.text(x_label + 0.008, y_texto, etiqueta, fontsize=10, fontweight="bold")
        ax.text(x_valor + 0.008, y_texto, valor, fontsize=10, ha="right")
        ax.text(x_unidad + 0.008, y_texto, unidad, fontsize=10)
        y -= alto_fila

    for i in range(len(filas) + 1):
        _linea_h(ax, y0 - alto_fila * i, x0=x_label, x1=columnas[-1], linewidth=0.4)
    for x in columnas:
        ax.plot([x, x], [y, y0], color="black", linewidth=0.4)

    nota_y = y - 0.02
    ax.text(
        _X0, nota_y,
        "Las dos primeras filas son las dos formas de facturar el corte: por metro "
        "lineal cortado, o por cantidad de cortes.",
        fontsize=7.5, color="#555555", style="italic",
    )
    return nota_y - 0.03


def _pagina_cabecera(fig, resultado: Resultado, config: Config) -> None:
    ax = fig.add_axes((0, 0, 1, 1))
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    ax.text(0.5, 0.965, "ORDEN DE CORTE", ha="center", fontsize=22, fontweight="bold")
    ax.text(0.5, 0.935, "Kutit · optimizador de corte de placas", ha="center", fontsize=10, color="#555555")
    _linea_h(ax, 0.91, linewidth=0.8)

    datos = [
        ("Número de orden", config.numero_orden),
        ("Cliente", config.cliente),
        ("Fecha", config.fecha),
        ("Placas usadas", f"{resultado.placas_usadas}"),
        ("Piezas colocadas", f"{resultado.piezas_colocadas} / {resultado.total_piezas}"),
        ("Aprovechamiento global", f"{resultado.aprovechamiento_global:.1f} %"),
    ]

    y = 0.86
    paso = 0.032
    for etiqueta, valor in datos:
        ax.text(0.06, y, f"{etiqueta}:", fontsize=11, fontweight="bold")
        ax.text(0.42, y, str(valor), fontsize=11)
        y -= paso

    y = _tabla_cortes(ax, y - 0.02, resultado)
    y = _tabla_metricas(ax, y, resultado)

    ax.text(
        _X0, max(y, 0.02),
        "Cantos: azul = 0.45 mm · rojo = 2 mm (siempre opacos). Relleno de pieza: color por "
        "corte, al 50% de transparencia. Sobrante: líneas diagonales grises sobre blanco.",
        fontsize=7.5, color="#555555",
    )


def generar_pdf_bytes(resultado: Resultado, config: Config) -> bytes:
    """Genera el PDF de la orden de corte en memoria y devuelve los bytes."""
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    colores_grupo = colores.asignar_colores_grupo(resultado)
    buffer = io.BytesIO()

    with PdfPages(buffer) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        _pagina_cabecera(fig, resultado, config)
        pdf.savefig(fig)
        plt.close(fig)

        for placa in resultado.placas:
            ancho_fig = 11.69
            alto_fig = max(6.0, ancho_fig * (placa.ancho / placa.largo) + 1.3)
            fig, ax = plt.subplots(figsize=(ancho_fig, alto_fig))
            dibujar_placa(ax, placa, resultado, colores_grupo)
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

    return buffer.getvalue()
