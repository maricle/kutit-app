"""Métricas de la orden de corte para la cabecera del PDF. Portado de Kutit
Adrian (kutit_kleba/src/kutit/resumen.py), sin cambios de lógica."""

from __future__ import annotations

from dataclasses import dataclass

from . import colores
from .modelos import PiezaColocada, Resultado


@dataclass
class GrupoCorte:
    codigo: str
    nombre: str
    largo: float
    ancho: float
    cantidad: int
    orientacion: str
    placas: list[int]
    color_nombre: str = "-"
    color_hex: str = "#CCCCCC"


def _orientacion(colocadas: list[PiezaColocada]) -> str:
    if len(colocadas) <= 1:
        return "-"
    mismo_y = len({round(pc.y, 1) for pc in colocadas}) == 1
    mismo_x = len({round(pc.x, 1) for pc in colocadas}) == 1
    if mismo_y and not mismo_x:
        return "horizontal"
    if mismo_x and not mismo_y:
        return "vertical"
    return "mixto"


def agrupar_cortes_principales(resultado: Resultado) -> list[GrupoCorte]:
    por_clave: dict[colores.ClaveGrupo, list[PiezaColocada]] = {}
    for placa in resultado.placas:
        for pc in placa.piezas:
            clave = colores.clave_grupo(pc.pieza.nombre_base, pc.pieza.largo_final, pc.pieza.ancho_final)
            por_clave.setdefault(clave, []).append(pc)

    paleta = colores.paleta_grupo(resultado)
    codigos = colores.codigos_grupo(resultado)

    grupos: list[GrupoCorte] = []
    for clave, colocadas in por_clave.items():
        nombre_base, medida_a, medida_b = clave
        largo, ancho = max(medida_a, medida_b), min(medida_a, medida_b)

        por_placa: dict[int, list[PiezaColocada]] = {}
        for pc in colocadas:
            por_placa.setdefault(pc.indice_placa, []).append(pc)

        orientaciones = {idx: _orientacion(lst) for idx, lst in por_placa.items()}
        distintas = set(orientaciones.values())
        orientacion = distintas.pop() if len(distintas) == 1 else "mixto"

        nombre_color, color_hex = paleta.get(clave, ("-", "#CCCCCC"))

        grupos.append(
            GrupoCorte(
                codigo=codigos.get(clave, "?"),
                nombre=nombre_base,
                largo=largo,
                ancho=ancho,
                cantidad=len(colocadas),
                orientacion=orientacion,
                placas=sorted(por_placa.keys()),
                color_nombre=nombre_color,
                color_hex=color_hex,
            )
        )

    grupos.sort(key=lambda g: g.codigo)
    return grupos


def metros_lineales_canto(resultado: Resultado) -> float:
    total_mm = 0.0
    for placa in resultado.placas:
        for pc in placa.piezas:
            c = pc.pieza.cantos
            largo, ancho = pc.pieza.largo_final, pc.pieza.ancho_final
            if c.l1 > 0:
                total_mm += largo
            if c.l2 > 0:
                total_mm += largo
            if c.a1 > 0:
                total_mm += ancho
            if c.a2 > 0:
                total_mm += ancho
    return total_mm / 1000.0


def metros_lineales_corte(resultado: Resultado) -> float:
    return sum(placa.longitud_cortes for placa in resultado.placas) / 1000.0


def cantidad_cortes(resultado: Resultado) -> int:
    return sum(placa.cortes for placa in resultado.placas)
