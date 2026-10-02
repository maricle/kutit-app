"""Algoritmo de optimización de corte (nesting 2D, multi-placa). Portado de
Kutit Adrian (kutit_kleba/src/kutit/optimizador.py), sin cambios de lógica
— solo renombrado el archivo (de `optimizador.py` a `empaquetador.py`) para
no chocar con el nombre del paquete.

Empaquetador guillotina con heurística Best Short Side Fit (BSSF): cada
corte que se traza es una línea recta que atraviesa de lado a lado el
sub-rectángulo que se está dividiendo — lo único ejecutable en una sierra
escuadradora real (a diferencia de un empaquetador tipo MaxRects, que puede
dejar huecos en L imposibles de cortar).

1. La placa arranca como un único rectángulo libre.
2. Para cada pieza se busca, entre todos los rectángulos libres de todas
   las placas abiertas, el hueco donde "sobra menos" (BSSF).
3. Al colocarla, el sobrante se separa con hasta dos cortes rectos.
4. Los huecos libres contiguos que podrían fusionarse en uno más grande se
   fusionan (si no, el guillotina fragmenta el sobrante de más).
5. Si una pieza no entra en ninguna placa abierta, se abre una placa nueva.

Kerf: en vez de restar el corte de sierra a mano, se empaqueta cada pieza
como `medida + kerf` dentro de una placa de `medida + kerf`.

Orden de entrada: se prueban cinco ordenamientos (área, lado mayor, largo,
ancho, perímetro) y se queda el mejor resultado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable

from .errores import ErrorConfiguracion, ErrorPiezaDemasiadoGrande
from .modelos import Config, ModoPlaca, Pieza, PiezaColocada, Placa, Resultado, Sobrante

EPS = 1e-6


@dataclass
class _Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h


class _Guillotine:
    def __init__(self, ancho_x: float, alto_y: float) -> None:
        self.ancho_x = ancho_x
        self.alto_y = alto_y
        self.libres: list[_Rect] = [_Rect(0.0, 0.0, ancho_x, alto_y)]
        self.cortes = 0
        self.longitud_cortes = 0.0

    def buscar(
        self, w: float, h: float, permitir_rotacion: bool
    ) -> tuple[tuple[float, float, float, float, bool] | None, float, float]:
        mejor: tuple[float, float, float, float, bool] | None = None
        mejor_corto = math.inf
        mejor_largo = math.inf

        candidatos: list[tuple[float, float, bool]] = [(w, h, False)]
        if permitir_rotacion and abs(w - h) > EPS:
            candidatos.append((h, w, True))

        for libre in self.libres:
            for cw, ch, rotada in candidatos:
                if cw > libre.w + EPS or ch > libre.h + EPS:
                    continue
                sobra_x = libre.w - cw
                sobra_y = libre.h - ch
                corto = min(sobra_x, sobra_y)
                largo = max(sobra_x, sobra_y)
                if corto < mejor_corto - EPS or (
                    abs(corto - mejor_corto) <= EPS and largo < mejor_largo - EPS
                ):
                    mejor = (libre.x, libre.y, cw, ch, rotada)
                    mejor_corto, mejor_largo = corto, largo

        return mejor, mejor_corto, mejor_largo

    def colocar(self, x: float, y: float, w: float, h: float) -> None:
        idx = self._indice_libre(x, y, w, h)
        libre = self.libres.pop(idx)
        self._dividir_y_registrar_cortes(libre, w, h)
        self._fusionar_libres()

    def _indice_libre(self, x: float, y: float, w: float, h: float) -> int:
        for i, r in enumerate(self.libres):
            if abs(r.x - x) < EPS and abs(r.y - y) < EPS and w <= r.w + EPS and h <= r.h + EPS:
                return i
        raise AssertionError("No se encontró el rectángulo libre a dividir (bug interno).")

    def _dividir_y_registrar_cortes(self, libre: _Rect, w: float, h: float) -> None:
        sobra_ancho = libre.w - w
        sobra_alto = libre.h - h
        horizontal = sobra_ancho <= sobra_alto

        nuevos: list[_Rect] = []
        if horizontal:
            if sobra_alto > EPS:
                nuevos.append(_Rect(libre.x, libre.y + h, libre.w, sobra_alto))
                self.cortes += 1
                self.longitud_cortes += libre.w
            if sobra_ancho > EPS:
                nuevos.append(_Rect(libre.x + w, libre.y, sobra_ancho, h))
                self.cortes += 1
                self.longitud_cortes += h
        else:
            if sobra_ancho > EPS:
                nuevos.append(_Rect(libre.x + w, libre.y, sobra_ancho, libre.h))
                self.cortes += 1
                self.longitud_cortes += libre.h
            if sobra_alto > EPS:
                nuevos.append(_Rect(libre.x, libre.y + h, w, sobra_alto))
                self.cortes += 1
                self.longitud_cortes += w

        self.libres.extend(r for r in nuevos if r.w > EPS and r.h > EPS)

    def _fusionar_libres(self) -> None:
        cambiado = True
        while cambiado:
            cambiado = False
            for i, a in enumerate(self.libres):
                for j in range(i + 1, len(self.libres)):
                    b = self.libres[j]
                    fusion = self._fusionar_par(a, b)
                    if fusion is not None:
                        self.libres = [r for k, r in enumerate(self.libres) if k not in (i, j)]
                        self.libres.append(fusion)
                        cambiado = True
                        break
                if cambiado:
                    break

    @staticmethod
    def _fusionar_par(a: _Rect, b: _Rect) -> _Rect | None:
        if abs(a.y - b.y) < EPS and abs(a.h - b.h) < EPS:
            if abs(a.x2 - b.x) < EPS:
                return _Rect(a.x, a.y, a.w + b.w, a.h)
            if abs(b.x2 - a.x) < EPS:
                return _Rect(b.x, b.y, a.w + b.w, a.h)
        if abs(a.x - b.x) < EPS and abs(a.w - b.w) < EPS:
            if abs(a.y2 - b.y) < EPS:
                return _Rect(a.x, a.y, a.w, a.h + b.h)
            if abs(b.y2 - a.y) < EPS:
                return _Rect(b.x, b.y, a.w, a.h + b.h)
        return None


def puede_rotar(pieza: Pieza, modo_placa: ModoPlaca) -> bool:
    if modo_placa is ModoPlaca.LISA:
        return True
    return bool(pieza.rotar)


def validar_config(config: Config) -> None:
    if config.placa_largo <= 0 or config.placa_ancho <= 0:
        raise ErrorConfiguracion(
            f"Las medidas de la placa deben ser positivas ({config.placa_largo:g} x {config.placa_ancho:g})."
        )
    if config.kerf < 0:
        raise ErrorConfiguracion(f"El kerf no puede ser negativo ({config.kerf:g}).")
    if config.margen < 0:
        raise ErrorConfiguracion(f"El margen no puede ser negativo ({config.margen:g}).")
    if config.largo_util <= 0 or config.ancho_util <= 0:
        raise ErrorConfiguracion(
            f"El margen de {config.margen:g} mm se come toda la placa "
            f"(queda {config.largo_util:g} x {config.ancho_util:g} mm)."
        )


def validar_piezas_entran(piezas: Iterable[Pieza], config: Config) -> None:
    problemas: list[str] = []
    L, A = config.largo_util, config.ancho_util

    for pieza in piezas:
        l, a = pieza.largo_corte, pieza.ancho_corte
        entra_normal = l <= L + EPS and a <= A + EPS
        entra_rotada = a <= L + EPS and l <= A + EPS
        rota = puede_rotar(pieza, config.modo_placa)

        if entra_normal or (entra_rotada and rota):
            continue

        detalle = f"  - Fila {pieza.fila_csv} · {pieza.descripcion}: {l:g} x {a:g} mm (corte)"
        if entra_rotada and not rota:
            detalle += " -> entraría rotada, pero la placa tiene dibujo y la pieza no está marcada con rotar=true."
        else:
            detalle += f" -> no entra en la placa útil de {L:g} x {A:g} mm."
        problemas.append(detalle)

    if problemas:
        raise ErrorPiezaDemasiadoGrande("Hay piezas que no entran en la placa:\n" + "\n".join(problemas))


def _sobrantes_de(contenedor: "_Guillotine", config: Config) -> list[Sobrante]:
    sobrantes: list[Sobrante] = []
    for libre in contenedor.libres:
        x2 = min(libre.x + libre.w, config.largo_util)
        y2 = min(libre.y + libre.h, config.ancho_util)
        w = x2 - libre.x
        h = y2 - libre.y
        if w > EPS and h > EPS:
            sobrantes.append(Sobrante(x=libre.x + config.margen, y=libre.y + config.margen, ancho_x=w, alto_y=h))
    return sobrantes


def _empaquetar(piezas: list[Pieza], config: Config) -> Resultado:
    kerf = config.kerf
    bin_x = config.largo_util + kerf
    bin_y = config.ancho_util + kerf

    contenedores: list[_Guillotine] = []
    placas: list[Placa] = []
    no_colocadas: list[Pieza] = []

    for pieza in piezas:
        w = pieza.largo_corte + kerf
        h = pieza.ancho_corte + kerf
        rota = puede_rotar(pieza, config.modo_placa)

        mejor_idx = -1
        mejor_pos = None
        mejor_corto = math.inf
        mejor_largo = math.inf

        for idx, contenedor in enumerate(contenedores):
            pos, corto, largo = contenedor.buscar(w, h, rota)
            if pos is None:
                continue
            if corto < mejor_corto - EPS or (abs(corto - mejor_corto) <= EPS and largo < mejor_largo - EPS):
                mejor_idx, mejor_pos = idx, pos
                mejor_corto, mejor_largo = corto, largo

        if mejor_pos is None:
            contenedor = _Guillotine(bin_x, bin_y)
            pos, _, _ = contenedor.buscar(w, h, rota)
            if pos is None:
                no_colocadas.append(pieza)
                continue
            contenedores.append(contenedor)
            placas.append(Placa(indice=len(placas) + 1, largo=config.placa_largo, ancho=config.placa_ancho))
            mejor_idx, mejor_pos = len(contenedores) - 1, pos

        x, y, w_usado, h_usado, rotada = mejor_pos
        contenedores[mejor_idx].colocar(x, y, w_usado, h_usado)

        placas[mejor_idx].piezas.append(
            PiezaColocada(
                pieza=pieza,
                indice_placa=mejor_idx + 1,
                x=x + config.margen,
                y=y + config.margen,
                ancho_x=w_usado - kerf,
                alto_y=h_usado - kerf,
                rotada=rotada,
            )
        )

    for contenedor, placa in zip(contenedores, placas):
        placa.cortes = contenedor.cortes
        placa.longitud_cortes = contenedor.longitud_cortes
        placa.sobrantes = _sobrantes_de(contenedor, config)

    return Resultado(placas=placas, no_colocadas=no_colocadas, total_piezas=len(piezas), config=config)


_ORDENES: tuple[tuple[str, Callable[[Pieza], float]], ...] = (
    ("área", lambda p: p.area_corte),
    ("lado mayor", lambda p: max(p.largo_corte, p.ancho_corte)),
    ("largo", lambda p: p.largo_corte),
    ("ancho", lambda p: p.ancho_corte),
    ("perímetro", lambda p: p.largo_corte + p.ancho_corte),
)


def _puntaje(resultado: Resultado) -> tuple:
    ultima = resultado.placas[-1].aprovechamiento if resultado.placas else 0.0
    total_cortes = sum(p.cortes for p in resultado.placas)
    return (len(resultado.placas), len(resultado.no_colocadas), ultima, total_cortes)


def optimizar(piezas: list[Pieza], config: Config) -> Resultado:
    """Optimiza el corte y devuelve el mejor resultado encontrado. Las
    piezas deben venir con largo_corte/ancho_corte ya calculados (ver
    optimizador.cantos)."""
    validar_config(config)
    validar_piezas_entran(piezas, config)

    mejor: Resultado | None = None
    for _nombre, clave in _ORDENES:
        ordenadas = sorted(piezas, key=clave, reverse=True)
        candidato = _empaquetar(ordenadas, config)
        if mejor is None or _puntaje(candidato) < _puntaje(mejor):
            mejor = candidato

    assert mejor is not None
    return mejor
