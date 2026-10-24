"""Planificador recursivo de una placa: busca la mejor MEZCLA de tipos de
pieza, no solo "la próxima pieza de la cola". Portado sin cambios de lógica
de Kutit Adrian (kutit_kleba/src/kutit/planificador.py — ver kutit spec/
spec-optimizador-corte.md).

El problema del empaquetador voraz (ver el bucle simple en
:mod:`optimizador.empaquetador`) es que decide pieza por pieza, en un orden
fijo, y en cada paso elige el hueco donde esa pieza deja menos sobrante
(BSSF). Esa regla es miope: una pieza larga y angosta cuya altura casi
iguala la de la placa SIEMPRE va a puntuar mejor que una pieza cuadrada, así
que el voraz la sigue metiendo mientras entre una más — aunque eso termine
dejando una franja demasiado angosta para ningún otro tipo de pieza. El
resultado es que una placa queda llena de un solo tipo y el resto recién se
empieza a combinar en la placa siguiente.

Acá se resuelve distinto: para cada sub-rectángulo a llenar, se prueban
explícitamente **bloques rectangulares** de cada tipo de pieza disponible
— no solo "la cantidad máxima que entra", sino cada cantidad intermedia
razonable (1, 2, 3... columnas) — y se recursa sobre lo que sobra de cada
bloque con los tipos restantes. Así el algoritmo puede descubrir que
reservar 7 columnas de un tipo (en vez de las 10 que entrarían) deja lugar
para 6 piezas de otro tipo, si eso llena mejor la placa en total.

Es una búsqueda combinatoria, memoizada por (ancho, alto, cantidades
restantes) y acotada por un presupuesto de nodos explorados: para
catálogos con muchos tipos de pieza distintos y cantidades grandes, el
espacio de búsqueda se corta y el resto de esa placa lo completa el
empaquetador voraz simple (ver :mod:`optimizador.empaquetador`), que nunca
falla.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

EPS = 1e-6

#: Nodos recursivos explorados como máximo por placa. Es barato por nodo,
#: así que este número se alcanza solo con catálogos realmente grandes.
PRESUPUESTO_NODOS_POR_PLACA = 60_000

#: A partir de cuántas columnas/filas candidatas se muestrea en vez de
#: probar todas (para no explotar con piezas muy chicas respecto de la
#: placa, donde entrarían cientos).
MAX_K_EXHAUSTIVO = 24


@dataclass
class Tipo:
    """Un tipo de pieza intercambiable: misma medida de corte (ya con el
    kerf sumado) y la misma regla de rotación."""

    indice: int
    w: float  # largo_corte + kerf
    h: float  # ancho_corte + kerf
    rota: bool
    cantidad: int


@dataclass(frozen=True)
class Colocacion:
    """Una pieza del plan, en coordenadas absolutas dentro de la placa
    (origen (0,0) en la esquina inferior izquierda), ya con el kerf sumado."""

    tipo: int
    x: float
    y: float
    w: float
    h: float
    rotada: bool


class _Presupuesto:
    """Cuenta nodos explorados; cuando se agota, cortar la búsqueda ahí."""

    __slots__ = ("restante",)

    def __init__(self, maximo: int) -> None:
        self.restante = maximo

    def consumir(self) -> bool:
        if self.restante <= 0:
            return False
        self.restante -= 1
        return True


def _orientaciones(t: Tipo, w_max: float, h_max: float) -> list[tuple[float, float, bool]]:
    """(pw, ph, rotada) de este tipo que entran en (w_max, h_max)."""
    candidatos = [(t.w, t.h, False)]
    if t.rota and abs(t.w - t.h) > EPS:
        candidatos.append((t.h, t.w, True))
    return [(pw, ph, r) for pw, ph, r in candidatos if pw <= w_max + EPS and ph <= h_max + EPS]


def _rango_k(k_max: int) -> list[int]:
    """Candidatos de "cuántas columnas/filas dedicar" a probar.

    Si son pocos, se prueban todos. Si son muchos (piezas muy chicas
    respecto del hueco), se muestrea: todos los valores chicos —donde más
    importa la diferencia— más una muestra gruesa hasta el máximo.
    """
    if k_max <= MAX_K_EXHAUSTIVO:
        return list(range(1, k_max + 1))
    chicos = list(range(1, MAX_K_EXHAUSTIVO + 1))
    paso = max(1, k_max // 20)
    gruesos = list(range(MAX_K_EXHAUSTIVO + 1, k_max + 1, paso))
    if k_max not in gruesos:
        gruesos.append(k_max)
    return sorted(set(chicos + gruesos))


def _con_cantidad(tipos: tuple[Tipo, ...], indice: int, nueva_cantidad: int) -> tuple[Tipo, ...]:
    return tuple(
        Tipo(t.indice, t.w, t.h, t.rota, nueva_cantidad) if i == indice else t
        for i, t in enumerate(tipos)
    )


def _restar_uso(tipos: tuple[Tipo, ...], plan: list[Colocacion]) -> tuple[Tipo, ...]:
    """Devuelve `tipos` con las cantidades usadas en `plan` descontadas."""
    if not plan:
        return tipos
    usados = Counter(c.tipo for c in plan)
    return tuple(
        Tipo(t.indice, t.w, t.h, t.rota, t.cantidad - usados.get(t.indice, 0)) for t in tipos
    )


def _clave_cache(w: float, h: float, tipos: tuple[Tipo, ...]) -> tuple:
    return (round(w, 1), round(h, 1), tuple(t.cantidad for t in tipos))


def _bloque_columnas(
    w: float, h: float, tipos: tuple[Tipo, ...], idx: int, pw: float, ph: float, rotada: bool,
    cache: dict, presupuesto: _Presupuesto,
) -> tuple[float, list[Colocacion]]:
    """Prueba reservar k columnas de ancho `pw` (apiladas de a `filas` en
    alto) para el tipo `idx`, para cada k razonable, y recursa sobre el
    sobrante. Devuelve la mejor variante encontrada."""
    t = tipos[idx]
    nx_max = int((w + EPS) // pw)
    ny_max = int((h + EPS) // ph)
    if nx_max <= 0 or ny_max <= 0:
        return 0.0, []

    mejor_area, mejor_plan = 0.0, []
    for k in _rango_k(nx_max):
        filas = min(ny_max, t.cantidad // k)
        if filas <= 0:
            continue
        cantidad = k * filas

        bloque: list[Colocacion] = []
        restante = cantidad
        for col in range(k):
            en_esta_col = min(filas, restante)
            for fila in range(en_esta_col):
                bloque.append(Colocacion(idx, col * pw, fila * ph, pw, ph, rotada))
            restante -= en_esta_col

        ancho_usado = k * pw
        alto_usado = filas * ph
        tipos_tras_bloque = _con_cantidad(tipos, idx, t.cantidad - cantidad)

        area_r1, plan_r1 = _mejor_relleno(
            w - ancho_usado, h, tipos_tras_bloque, cache, presupuesto
        )
        tipos_tras_r1 = _restar_uso(tipos_tras_bloque, plan_r1)
        plan_r1_abs = [
            Colocacion(c.tipo, c.x + ancho_usado, c.y, c.w, c.h, c.rotada) for c in plan_r1
        ]

        area_r2, plan_r2 = _mejor_relleno(
            ancho_usado, h - alto_usado, tipos_tras_r1, cache, presupuesto
        )
        plan_r2_abs = [
            Colocacion(c.tipo, c.x, c.y + alto_usado, c.w, c.h, c.rotada) for c in plan_r2
        ]

        area_total = cantidad * pw * ph + area_r1 + area_r2
        if area_total > mejor_area + EPS:
            mejor_area = area_total
            mejor_plan = bloque + plan_r1_abs + plan_r2_abs

    return mejor_area, mejor_plan


def _bloque_filas(
    w: float, h: float, tipos: tuple[Tipo, ...], idx: int, pw: float, ph: float, rotada: bool,
    cache: dict, presupuesto: _Presupuesto,
) -> tuple[float, list[Colocacion]]:
    """Igual que :func:`_bloque_columnas`, pero reservando k FILAS de alto
    `ph` (apiladas de a `columnas` a lo ancho) en vez de columnas."""
    t = tipos[idx]
    nx_max = int((w + EPS) // pw)
    ny_max = int((h + EPS) // ph)
    if nx_max <= 0 or ny_max <= 0:
        return 0.0, []

    mejor_area, mejor_plan = 0.0, []
    for k in _rango_k(ny_max):
        columnas = min(nx_max, t.cantidad // k)
        if columnas <= 0:
            continue
        cantidad = k * columnas

        bloque: list[Colocacion] = []
        restante = cantidad
        for fila in range(k):
            en_esta_fila = min(columnas, restante)
            for col in range(en_esta_fila):
                bloque.append(Colocacion(idx, col * pw, fila * ph, pw, ph, rotada))
            restante -= en_esta_fila

        alto_usado = k * ph
        ancho_usado = columnas * pw
        tipos_tras_bloque = _con_cantidad(tipos, idx, t.cantidad - cantidad)

        # Resto 1: franja de arriba, ancho completo.
        area_r1, plan_r1 = _mejor_relleno(
            w, h - alto_usado, tipos_tras_bloque, cache, presupuesto
        )
        tipos_tras_r1 = _restar_uso(tipos_tras_bloque, plan_r1)
        plan_r1_abs = [
            Colocacion(c.tipo, c.x, c.y + alto_usado, c.w, c.h, c.rotada) for c in plan_r1
        ]

        # Resto 2: franja a la derecha del bloque, solo dentro del alto usado.
        area_r2, plan_r2 = _mejor_relleno(
            w - ancho_usado, alto_usado, tipos_tras_r1, cache, presupuesto
        )
        plan_r2_abs = [
            Colocacion(c.tipo, c.x + ancho_usado, c.y, c.w, c.h, c.rotada) for c in plan_r2
        ]

        area_total = cantidad * pw * ph + area_r1 + area_r2
        if area_total > mejor_area + EPS:
            mejor_area = area_total
            mejor_plan = bloque + plan_r1_abs + plan_r2_abs

    return mejor_area, mejor_plan


def _mejor_relleno(
    w: float, h: float, tipos: tuple[Tipo, ...], cache: dict, presupuesto: _Presupuesto
) -> tuple[float, list[Colocacion]]:
    if w <= EPS or h <= EPS or all(t.cantidad <= 0 for t in tipos):
        return 0.0, []

    clave = _clave_cache(w, h, tipos)
    encontrado = cache.get(clave)
    if encontrado is not None:
        return encontrado

    if not presupuesto.consumir():
        # Presupuesto agotado: no seguimos explorando esta rama. El
        # optimizador completa lo que falte con el empaquetador voraz.
        return 0.0, []

    mejor_area, mejor_plan = 0.0, []
    for idx, t in enumerate(tipos):
        if t.cantidad <= 0:
            continue
        for pw, ph, rotada in _orientaciones(t, w, h):
            area_c, plan_c = _bloque_columnas(w, h, tipos, idx, pw, ph, rotada, cache, presupuesto)
            if area_c > mejor_area + EPS:
                mejor_area, mejor_plan = area_c, plan_c

            area_f, plan_f = _bloque_filas(w, h, tipos, idx, pw, ph, rotada, cache, presupuesto)
            if area_f > mejor_area + EPS:
                mejor_area, mejor_plan = area_f, plan_f

    cache[clave] = (mejor_area, mejor_plan)
    return mejor_area, mejor_plan


def planificar_placa(w: float, h: float, tipos: list[Tipo]) -> tuple[float, list[Colocacion]]:
    """Mejor plan encontrado para llenar una placa ``w x h`` con estos tipos.

    Devuelve ``(área_usada, plan)``; ``plan`` es la lista de colocaciones en
    un orden tal que reproducirlas, en ese orden, sobre un
    :class:`optimizador.empaquetador._Guillotine` vacío (llamando
    ``.colocar(x, y, w, h)`` para cada una) reconstruye exactamente esos
    cortes guillotina.
    """
    cache: dict = {}
    presupuesto = _Presupuesto(PRESUPUESTO_NODOS_POR_PLACA)
    return _mejor_relleno(w, h, tuple(tipos), cache, presupuesto)
