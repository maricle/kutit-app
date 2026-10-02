"""Estructuras de datos del dominio. Portado de Kutit Adrian
(kutit_kleba/src/kutit/modelos.py), recortando los campos de `Config` que
solo tenían sentido para un programa de consola (rutas de archivo, flags de
"mostrar ventana", etc.) — acá los archivos se generan en memoria/temporal
por request, no se guardan en disco de forma persistente.

Sistema de coordenadas usado en todo el paquete
------------------------------------------------
La placa se dibuja como un rectángulo en el plano XY::

    Y (ancho de placa, 1830 mm)
    ^
    |  +--------------------------------+
    |  |                                |
    |  |            PLACA               |
    |  |                                |
    |  +--------------------------------+
    +-------------------------------------> X (largo de placa, 2750 mm)

El eje **X** corre a lo largo de la veta / dibujo de la placa (2750 mm).
Por eso una pieza "sin rotar" (0°) apoya su `largo` sobre X, que es lo que
hay que respetar cuando la placa tiene dibujo.

Nomenclatura de los lados de una pieza
----------------------------------------
Una pieza tiene dos lados que miden `largo` y dos que miden `ancho`::

           l2  (lado de longitud `largo`)
        +-------------+
    a1  |             |  a2      (lados de longitud `ancho`)
        +-------------+
           l1  (lado de longitud `largo`)

Un canto pegado sobre un lado sobresale perpendicularmente a ese lado:

* canto en `l1` / `l2`  -> agrega espesor sobre el eje **ancho**.
* canto en `a1` / `a2`  -> agrega espesor sobre el eje **largo**.

Mapeo con los campos `canto_1..4` que usa el resto de kutit-app (ver
`optimizador/adaptador.py`): `canto_1→l1, canto_2→l2, canto_3→a1, canto_4→a2`
— mismo eje que ya usa `calculos.metros_canto` (canto_1/2 suman `alto`,
canto_3/4 suman `ancho`, y `alto`(kutit-app) ≡ `largo`(acá)).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ModoPlaca(str, Enum):
    """Cómo se puede orientar una pieza dentro de la placa."""

    #: Placa sin veta: cualquier pieza puede rotarse 90° libremente.
    LISA = "lisa"
    #: Placa con dibujo/veta: solo rotan las piezas marcadas con `rotar = true`.
    DIBUJO = "dibujo"


class ModoCanto(str, Enum):
    """Qué hacer con el espesor del canto respecto de la medida pedida."""

    #: La medida pedida es la medida FINAL: se descuenta el canto del corte.
    DESCONTAR = "descontar"
    #: La medida pedida es la medida de CORTE: el canto se suma encima.
    AGREGAR = "agregar"
    #: El canto se dibuja pero no altera ninguna medida.
    NINGUNO = "ninguno"


@dataclass(frozen=True)
class Cantos:
    """Espesores de canto (en mm) de cada lado de la pieza, en orientación 0°.

    Un valor ``0.0`` significa "ese lado va sin canto".
    """

    l1: float = 0.0
    l2: float = 0.0
    a1: float = 0.0
    a2: float = 0.0

    @property
    def suma_sobre_ancho(self) -> float:
        return self.l1 + self.l2

    @property
    def suma_sobre_largo(self) -> float:
        return self.a1 + self.a2

    @property
    def tiene_alguno(self) -> bool:
        return any(v > 0 for v in (self.l1, self.l2, self.a1, self.a2))

    def espesores_usados(self) -> set[float]:
        return {v for v in (self.l1, self.l2, self.a1, self.a2) if v > 0}


@dataclass
class Pieza:
    """Una pieza individual a cortar (ya expandida por cantidad)."""

    id: str
    descripcion: str
    largo_pedido: float
    ancho_pedido: float
    cantos: Cantos
    rotar: bool
    fila_csv: int

    largo_corte: float = 0.0
    ancho_corte: float = 0.0
    largo_final: float = 0.0
    ancho_final: float = 0.0

    nombre_base: str = ""
    indice_en_grupo: int = 1
    cantidad_en_grupo: int = 1

    @property
    def area_corte(self) -> float:
        return self.largo_corte * self.ancho_corte


@dataclass
class PiezaColocada:
    """Una pieza ya ubicada en una placa concreta."""

    pieza: Pieza
    indice_placa: int
    x: float
    y: float
    ancho_x: float
    alto_y: float
    rotada: bool

    @property
    def area(self) -> float:
        return self.ancho_x * self.alto_y

    @property
    def rotacion_grados(self) -> int:
        return 90 if self.rotada else 0

    @property
    def etiqueta(self) -> str:
        p = self.pieza
        texto = f"{p.descripcion}\n{p.largo_final:g} x {p.ancho_final:g}"
        if self.rotada:
            texto += "\n(rot 90°)"
        return texto


@dataclass
class Sobrante:
    """Un retazo de material que sobra en una placa."""

    x: float
    y: float
    ancho_x: float
    alto_y: float

    @property
    def area(self) -> float:
        return self.ancho_x * self.alto_y


@dataclass
class Placa:
    """Una placa con sus piezas colocadas."""

    indice: int
    largo: float
    ancho: float
    piezas: list[PiezaColocada] = field(default_factory=list)
    sobrantes: list[Sobrante] = field(default_factory=list)
    cortes: int = 0
    longitud_cortes: float = 0.0

    @property
    def area(self) -> float:
        return self.largo * self.ancho

    @property
    def area_usada(self) -> float:
        return sum(pc.area for pc in self.piezas)

    @property
    def aprovechamiento(self) -> float:
        return (self.area_usada / self.area * 100.0) if self.area else 0.0


@dataclass
class Config:
    """Parámetros geométricos de una corrida del optimizador (sin nada de
    archivo/consola — eso vive en `optimizador/servicio.py`)."""

    placa_largo: float = 2750.0  # eje X, dirección de la veta
    placa_ancho: float = 1830.0  # eje Y
    kerf: float = 4.0
    margen: float = 0.0
    modo_placa: ModoPlaca = ModoPlaca.LISA
    modo_canto: ModoCanto = ModoCanto.NINGUNO
    espesor_canto: float = 0.45
    canto_umbral: float = 0.0

    # -- datos de la orden, solo para la cabecera del PDF --------------
    numero_orden: str = "-"
    cliente: str = "-"
    fecha: str = "-"

    @property
    def largo_util(self) -> float:
        return self.placa_largo - 2 * self.margen

    @property
    def ancho_util(self) -> float:
        return self.placa_ancho - 2 * self.margen


@dataclass
class Resultado:
    """Resultado completo de una optimización."""

    placas: list[Placa]
    no_colocadas: list[Pieza]
    total_piezas: int
    config: Config

    @property
    def placas_usadas(self) -> int:
        return len(self.placas)

    @property
    def piezas_colocadas(self) -> int:
        return sum(len(p.piezas) for p in self.placas)

    @property
    def aprovechamiento_global(self) -> float:
        area_total = sum(p.area for p in self.placas)
        if not area_total:
            return 0.0
        return sum(p.area_usada for p in self.placas) / area_total * 100.0
