"""Dibujo de una placa con matplotlib. Portado de Kutit Adrian
(kutit_kleba/src/kutit/visualizacion.py), recortado a solo `dibujar_placa`
(la usa `pdf_export.py` para la página de cada placa) — se saca
`generar_figura`/`_leyenda`, que generaban un PNG suelto con ventana
interactiva (`plt.show()`), pensado para uso de escritorio; acá no se
genera PNG, solo el PDF y el DXF.

* Cada pieza es un rectángulo con una etiqueta compacta ("A #4 764x190"):
  el código del corte, cuántas copias hay en total, y su medida final (con
  "↻" si quedó rotada). Relleno de color según su corte, al 50% opacidad.
* Los cantos se dibujan como líneas de color encima del borde
  correspondiente, siempre 100% opacas, respetando la rotación.
* El título muestra número de placa, medidas, piezas, cortes y
  aprovechamiento.
"""

from __future__ import annotations

from . import colores
from .modelos import PiezaColocada, Placa, Resultado

COLOR_PLACA = "white"
COLOR_BORDE_PLACA = "black"
COLOR_BORDE_PIEZA = "black"
ANCHO_LINEA_CANTO = 3.0


def _dibujar_cantos(ax, pc: PiezaColocada) -> None:
    x0, y0 = pc.x, pc.y
    x1, y1 = pc.x + pc.ancho_x, pc.y + pc.alto_y

    coordenadas = {
        "abajo": ((x0, x1), (y0, y0)),
        "arriba": ((x0, x1), (y1, y1)),
        "izquierda": ((x0, x0), (y0, y1)),
        "derecha": ((x1, x1), (y0, y1)),
    }

    for lado, espesor in colores.lados_con_canto(pc):
        xs, ys = coordenadas[lado]
        ax.plot(
            xs, ys,
            color=colores.color_de_canto(espesor),
            alpha=colores.ALPHA_CANTO,
            linewidth=ANCHO_LINEA_CANTO,
            solid_capstyle="butt",
            zorder=5,
        )


def _dibujar_etiqueta(ax, pc: PiezaColocada, placa: Placa, codigo: str, cantidad_grupo: int) -> None:
    cx = pc.x + pc.ancho_x / 2
    cy = pc.y + pc.alto_y / 2
    lado_menor = min(pc.ancho_x, pc.alto_y)
    lado_mayor = max(pc.ancho_x, pc.alto_y)

    if lado_menor < 14 or lado_mayor < 28:
        return

    texto = colores.texto_codigo_pieza(pc, codigo, cantidad_grupo)
    tamano = max(4.0, min(7.0, lado_menor / placa.ancho * 35))
    rotacion_texto = 90 if pc.alto_y > pc.ancho_x * 1.6 else 0

    ax.text(
        cx, cy, texto,
        ha="center", va="center", fontsize=tamano, fontweight="bold",
        rotation=rotacion_texto, zorder=6,
    )


def dibujar_placa(ax, placa: Placa, resultado: Resultado, colores_grupo: dict[colores.ClaveGrupo, str]) -> None:
    """Dibuja una placa completa con todas sus piezas en el eje dado."""
    from matplotlib.colors import to_rgba
    from matplotlib.patches import Rectangle

    config = resultado.config
    codigos_grupo = colores.codigos_grupo(resultado)
    conteo = colores.conteo_grupo(resultado)

    ax.add_patch(
        Rectangle((0, 0), placa.largo, placa.ancho, facecolor=COLOR_PLACA, edgecolor=COLOR_BORDE_PLACA,
                   linewidth=1.6, zorder=1)
    )

    if config.margen > 0:
        ax.add_patch(
            Rectangle(
                (config.margen, config.margen), config.largo_util, config.ancho_util,
                facecolor="none", edgecolor="#9E9E9E", linewidth=0.8, linestyle="--", zorder=2,
            )
        )

    for sobrante in placa.sobrantes:
        ax.add_patch(
            Rectangle(
                (sobrante.x, sobrante.y), sobrante.ancho_x, sobrante.alto_y,
                facecolor="white", edgecolor=colores.COLOR_SOBRANTE, hatch=colores.HATCH_SOBRANTE,
                linewidth=0.0, zorder=2,
            )
        )

    for pc in placa.piezas:
        clave = colores.clave_grupo(pc.pieza.nombre_base, pc.pieza.largo_final, pc.pieza.ancho_final)
        color_relleno = to_rgba(colores_grupo[clave], colores.ALPHA_GRUPO)
        ax.add_patch(
            Rectangle((pc.x, pc.y), pc.ancho_x, pc.alto_y, facecolor=color_relleno,
                       edgecolor=COLOR_BORDE_PIEZA, linewidth=1.0, zorder=3)
        )
        _dibujar_cantos(ax, pc)
        _dibujar_etiqueta(ax, pc, placa, codigos_grupo[clave], conteo[clave])

    margen_vista = max(placa.largo, placa.ancho) * 0.03
    ax.set_xlim(-margen_vista, placa.largo + margen_vista)
    ax.set_ylim(-margen_vista, placa.ancho + margen_vista)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    # "Cortes" (pasadas de sierra) no se muestra acá a propósito: es
    # terminología técnica de taller, no hace falta en el título de la
    # imagen — el PDF interno ya lo tiene en su tabla de métricas
    # (resumen.py), y el motor simplificado del formulario público (que
    # también reusa este dibujo, ver calculos.generar_previews_png) ni
    # siquiera lo calcula.
    ax.set_title(
        f"Placa {placa.indice}  ·  {placa.largo:g} x {placa.ancho:g} mm  ·  "
        f"{len(placa.piezas)} piezas  ·  "
        f"aprovechamiento {placa.aprovechamiento:.1f}%",
        fontsize=11, pad=8,
    )
