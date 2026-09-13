import math


def metros_corte(cortes) -> float:
    return sum(c["cantidad"] * 2 * (c["alto"] + c["ancho"]) for c in cortes) / 1000


def metros_canto(cortes) -> float:
    return sum(
        c["cantidad"] * (
            (c["alto"] if c["canto_1"] else 0) + (c["alto"] if c["canto_2"] else 0)
            + (c["ancho"] if c["canto_3"] else 0) + (c["ancho"] if c["canto_4"] else 0)
        )
        for c in cortes
    ) / 1000


def cantidad_placas(cortes, ancho_placa: int, largo_placa: int) -> int:
    area_piezas = sum(c["cantidad"] * c["alto"] * c["ancho"] for c in cortes)
    area_placa = ancho_placa * largo_placa
    return math.ceil(area_piezas / area_placa) if area_placa else 0
