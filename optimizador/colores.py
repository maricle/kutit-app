"""Paleta de colores y códigos del plano de corte, compartidos por PDF, DXF
y la hoja de etiquetas. Portado de Kutit Adrian
(kutit_kleba/src/kutit/colores.py), sin cambios de lógica.

* Piezas: se agrupan por nombre + tamaño final (sin importar rotación).
  Cada grupo recibe un código de una letra (A, B, C...) y un color básico
  con 50% de transparencia, en el mismo orden (más piezas primero).
* Cantos: color fijo según espesor, siempre 100% opaco: 0.45 mm -> azul,
  2 mm -> rojo, otro espesor -> verde.
* Sobrantes: sombreado con líneas diagonales grises sobre blanco.
"""

from __future__ import annotations

import string

from .modelos import PiezaColocada

ClaveGrupo = tuple[str, float, float]

PALETA_GRUPOS: tuple[tuple[str, str], ...] = (
    ("Celeste", "#29B6F6"),
    ("Rosa", "#F06292"),
    ("Naranja", "#FFA726"),
    ("Verde", "#66BB6A"),
)
ALPHA_GRUPO = 0.5

COLORES_CANTO: dict[float, str] = {
    0.45: "#0000FF",
    2.0: "#FF0000",
}
COLOR_CANTO_OTRO = "#008000"
ALPHA_CANTO = 1.0

COLOR_SOBRANTE = "#9E9E9E"
HATCH_SOBRANTE = "////"


def color_de_canto(espesor: float) -> str:
    for referencia, color in COLORES_CANTO.items():
        if abs(espesor - referencia) < 0.01:
            return color
    return COLOR_CANTO_OTRO


def clave_grupo(nombre_base: str, largo_final: float, ancho_final: float) -> ClaveGrupo:
    return (nombre_base, *sorted((round(largo_final, 1), round(ancho_final, 1))))


def _conteo_por_grupo(resultado) -> dict[ClaveGrupo, int]:
    conteo: dict[ClaveGrupo, int] = {}
    for placa in resultado.placas:
        for pc in placa.piezas:
            clave = clave_grupo(pc.pieza.nombre_base, pc.pieza.largo_final, pc.pieza.ancho_final)
            conteo[clave] = conteo.get(clave, 0) + 1
    return conteo


def conteo_grupo(resultado) -> dict[ClaveGrupo, int]:
    return _conteo_por_grupo(resultado)


def _claves_ordenadas(resultado) -> list[ClaveGrupo]:
    conteo = _conteo_por_grupo(resultado)
    return sorted(conteo, key=lambda k: (-conteo[k], k))


def paleta_grupo(resultado) -> dict[ClaveGrupo, tuple[str, str]]:
    claves = _claves_ordenadas(resultado)
    return {clave: PALETA_GRUPOS[i % len(PALETA_GRUPOS)] for i, clave in enumerate(claves)}


def asignar_colores_grupo(resultado) -> dict[ClaveGrupo, str]:
    return {clave: color for clave, (_nombre, color) in paleta_grupo(resultado).items()}


def _codigo_excel(indice: int) -> str:
    letras = string.ascii_uppercase
    n = indice + 1
    codigo = ""
    while n > 0:
        n, resto = divmod(n - 1, 26)
        codigo = letras[resto] + codigo
    return codigo


def codigos_grupo(resultado) -> dict[ClaveGrupo, str]:
    claves = _claves_ordenadas(resultado)
    return {clave: _codigo_excel(i) for i, clave in enumerate(claves)}


def lados_con_canto(pc: PiezaColocada) -> list[tuple[str, float]]:
    """Mapea los cantos de una pieza colocada a los lados del dibujo,
    ya proyectados según la rotación aplicada."""
    c = pc.pieza.cantos
    if not pc.rotada:
        mapeo = {"abajo": c.l1, "arriba": c.l2, "izquierda": c.a1, "derecha": c.a2}
    else:
        mapeo = {"izquierda": c.l1, "derecha": c.l2, "abajo": c.a1, "arriba": c.a2}
    return [(lado, esp) for lado, esp in mapeo.items() if esp > 0]


def texto_codigo_pieza(pc: PiezaColocada, codigo: str, cantidad_grupo: int) -> str:
    texto = f"{codigo} #{cantidad_grupo} {pc.pieza.largo_final:g}x{pc.pieza.ancho_final:g}"
    if pc.rotada:
        texto += " ↻"
    return texto
