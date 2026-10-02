"""Ajuste de medidas según el modo de canto. Portado de Kutit Adrian
(kutit_kleba/src/kutit/cantos.py), sin cambios de lógica.

``descontar``: la medida pedida es la medida terminada -> corte = pedido -
espesor de los cantos de ese eje, final = pedido.
``agregar``: la medida pedida es la de corte -> corte = pedido,
final = pedido + espesor de los cantos de ese eje.
``ninguno``: el canto se dibuja pero no toca ninguna medida (default de
kutit-app — no cambia ningún número que el cliente ya ve).

Qué canto afecta a qué eje: cantos l1/l2 (lados que miden `largo`) afectan
el eje ancho; cantos a1/a2 (lados que miden `ancho`) afectan el eje largo.
"""

from __future__ import annotations

from .errores import ErrorPiezaInvalida
from .modelos import Cantos, ModoCanto, Pieza


def _suma_filtrada(espesores: tuple[float, ...], umbral: float) -> float:
    return sum(e for e in espesores if e > 0 and e >= umbral)


def aplicar_modo_canto(pieza: Pieza, modo: ModoCanto, umbral: float = 0.0) -> Pieza:
    """Completa `largo_corte/ancho_corte` y `largo_final/ancho_final`.
    Modifica la pieza in-place y la devuelve, para poder encadenar."""
    cantos: Cantos = pieza.cantos

    delta_largo = _suma_filtrada((cantos.a1, cantos.a2), umbral)
    delta_ancho = _suma_filtrada((cantos.l1, cantos.l2), umbral)

    if modo is ModoCanto.DESCONTAR:
        pieza.largo_corte = pieza.largo_pedido - delta_largo
        pieza.ancho_corte = pieza.ancho_pedido - delta_ancho
        pieza.largo_final = pieza.largo_pedido
        pieza.ancho_final = pieza.ancho_pedido

    elif modo is ModoCanto.AGREGAR:
        pieza.largo_corte = pieza.largo_pedido
        pieza.ancho_corte = pieza.ancho_pedido
        pieza.largo_final = pieza.largo_pedido + delta_largo
        pieza.ancho_final = pieza.ancho_pedido + delta_ancho

    else:  # ModoCanto.NINGUNO
        pieza.largo_corte = pieza.largo_pedido
        pieza.ancho_corte = pieza.ancho_pedido
        pieza.largo_final = pieza.largo_pedido
        pieza.ancho_final = pieza.ancho_pedido

    if pieza.largo_corte <= 0 or pieza.ancho_corte <= 0:
        raise ErrorPiezaInvalida(
            f"Fila {pieza.fila_csv} ({pieza.descripcion}): al descontar el canto la "
            f"medida de corte queda inválida "
            f"({pieza.largo_corte:g} x {pieza.ancho_corte:g} mm)."
        )

    return pieza


def aplicar_modo_canto_a_todas(piezas: list[Pieza], modo: ModoCanto, umbral: float = 0.0) -> list[Pieza]:
    for pieza in piezas:
        aplicar_modo_canto(pieza, modo, umbral)
    return piezas
