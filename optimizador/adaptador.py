"""Adapta los cortes de una solicitud (dicts con descripcion/cantidad/alto/
ancho/canto_1..4/rotar, el mismo formato que usa el resto de kutit-app) al
modelo `Pieza` del optimizador. Reemplaza a `lector_csv.leer_piezas` de
Kutit Adrian, que leía de un archivo — acá no hay archivo, los cortes ya
están en la base.

Mapeo de canto: canto_1→l1, canto_2→l2, canto_3→a1, canto_4→a2 (ver el
docstring de `optimizador/modelos.py` para la justificación del mapeo de
ejes)."""

from __future__ import annotations

from .modelos import Cantos, Pieza


def piezas_desde_cortes(cortes: list[dict], espesor_canto: float) -> list[Pieza]:
    total_por_nombre: dict[str, int] = {}
    for c in cortes:
        nombre = (c["descripcion"] or "Pieza").strip() or "Pieza"
        total_por_nombre[nombre] = total_por_nombre.get(nombre, 0) + int(c["cantidad"])

    contador_por_nombre: dict[str, int] = {}
    piezas: list[Pieza] = []
    fila_csv = 0
    for c in cortes:
        fila_csv += 1
        nombre = (c["descripcion"] or "Pieza").strip() or "Pieza"
        cantos = Cantos(
            l1=espesor_canto if c.get("canto_1") else 0.0,
            l2=espesor_canto if c.get("canto_2") else 0.0,
            a1=espesor_canto if c.get("canto_3") else 0.0,
            a2=espesor_canto if c.get("canto_4") else 0.0,
        )
        for _ in range(int(c["cantidad"])):
            contador_por_nombre[nombre] = contador_por_nombre.get(nombre, 0) + 1
            indice = contador_por_nombre[nombre]
            piezas.append(
                Pieza(
                    id=f"{fila_csv}-{indice}",
                    descripcion=f"{nombre} {indice}" if total_por_nombre[nombre] > 1 else nombre,
                    largo_pedido=float(c["alto"]),
                    ancho_pedido=float(c["ancho"]),
                    cantos=cantos,
                    rotar=bool(c.get("rotar", True)),
                    fila_csv=fila_csv,
                    nombre_base=nombre,
                    indice_en_grupo=indice,
                    cantidad_en_grupo=total_por_nombre[nombre],
                )
            )
    return piezas
