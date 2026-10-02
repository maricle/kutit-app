"""Punto de entrada único del paquete `optimizador`: arma la `Config` a
partir de los parámetros configurables de kutit-app, corre el empaquetador
y genera las descargas (PDF, DXF, etiquetas). Ver kutit spec/
spec-optimizador-corte.md para el porqué de cada default."""

from __future__ import annotations

import io
import zipfile

import base64

from . import colores
from .adaptador import piezas_desde_cortes
from .cantos import aplicar_modo_canto_a_todas
from .dxf_export import generar_dxf_bytes_por_placa
from .empaquetador import optimizar
from .etiquetas_export import generar_etiquetas_bytes
from .modelos import Config as OptimizadorConfig, ModoCanto, ModoPlaca, Resultado
from .pdf_export import generar_pdf_bytes
from .visualizacion import dibujar_placa


def calcular_resultado(
    cortes: list[dict],
    ancho_placa: int,
    largo_placa: int,
    kerf_mm: float,
    margen_mm: float,
    modo_canto: str,
    espesor_canto_mm: float,
    canto_umbral_mm: float,
    tiene_veta: bool,
    numero_orden: str = "-",
    cliente: str = "-",
    fecha: str = "-",
) -> Resultado:
    """Corre el nesting real (empaquetador guillotina de Kutit Adrian) sobre
    los cortes dados. Todos los parámetros de máquina/canto/veta vienen
    resueltos por el llamador (ver main.py: combina Configuración de
    máquina + espesor de canto de la solicitud + veta del material elegido
    — ver kutit spec/spec-optimizador-corte.md). Lanza
    `optimizador.errores.OptimizadorError` (o una subclase) si algo no es
    válido."""
    cfg = OptimizadorConfig(
        placa_largo=float(largo_placa),
        placa_ancho=float(ancho_placa),
        kerf=kerf_mm,
        margen=margen_mm,
        modo_placa=ModoPlaca.DIBUJO if tiene_veta else ModoPlaca.LISA,
        modo_canto=ModoCanto(modo_canto),
        espesor_canto=espesor_canto_mm,
        canto_umbral=canto_umbral_mm,
        numero_orden=numero_orden,
        cliente=cliente,
        fecha=fecha,
    )
    piezas = piezas_desde_cortes(cortes, cfg.espesor_canto)
    aplicar_modo_canto_a_todas(piezas, cfg.modo_canto, cfg.canto_umbral)
    return optimizar(piezas, cfg)


def _preview_png_base64(placa, resultado: Resultado, colores_grupo: dict) -> str:
    """Dibuja una placa con matplotlib (mismo código que usa el PDF: color
    por grupo de tamaño, cantos de color, sobrante rayado) y la devuelve
    como PNG en base64, lista para un <img src="data:image/png;base64,...">."""
    import matplotlib.pyplot as plt

    ancho_fig = 9.0
    alto_fig = max(3.0, ancho_fig * (placa.ancho / placa.largo))
    fig, ax = plt.subplots(figsize=(ancho_fig, alto_fig))
    dibujar_placa(ax, placa, resultado, colores_grupo)
    fig.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=130, facecolor="white")
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def resultado_a_resumen(resultado: Resultado) -> dict:
    """Convierte un Resultado a JSON para el panel interno: los datos
    numéricos de cada placa más una vista previa PNG ya coloreada por
    grupo de tamaño (ver _preview_png_base64) — no un dibujo aparte en el
    frontend, para no duplicar la lógica de colores/leyenda que ya usan el
    PDF y el DXF."""
    from .resumen import metros_lineales_canto, metros_lineales_corte

    colores_grupo = colores.asignar_colores_grupo(resultado)

    placas = []
    for placa in resultado.placas:
        placas.append({
            "ancho": placa.ancho,
            "largo": placa.largo,
            "piezas": len(placa.piezas),
            "aprovechamiento": round(placa.aprovechamiento, 1),
            "sobrante": round(100 - placa.aprovechamiento, 1),
            "imagen_base64": _preview_png_base64(placa, resultado, colores_grupo),
        })

    return {
        "num_placas": resultado.placas_usadas,
        "placas": placas,
        "total_piezas": resultado.total_piezas,
        "aprovechamiento": round(resultado.aprovechamiento_global, 1),
        "sobrante": round(100 - resultado.aprovechamiento_global, 1),
        "metros_corte": round(metros_lineales_corte(resultado), 2),
        "metros_canto": round(metros_lineales_canto(resultado), 2),
    }


def generar_pdf(resultado: Resultado) -> bytes:
    return generar_pdf_bytes(resultado, resultado.config)


def generar_etiquetas_pdf(resultado: Resultado) -> bytes | None:
    return generar_etiquetas_bytes(resultado)


def generar_dxf_zip(resultado: Resultado) -> bytes:
    """Zipea los DXF de todas las placas en un solo archivo descargable."""
    archivos = generar_dxf_bytes_por_placa(resultado)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre, contenido in archivos:
            zf.writestr(nombre, contenido)
    return buffer.getvalue()
