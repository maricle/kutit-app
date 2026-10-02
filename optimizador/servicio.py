"""Punto de entrada único del paquete `optimizador`: arma la `Config` a
partir de los parámetros configurables de kutit-app, corre el empaquetador
y genera las descargas (PDF, DXF, etiquetas). Ver kutit spec/
spec-optimizador-corte.md para el porqué de cada default."""

from __future__ import annotations

import io
import zipfile

import config
from .adaptador import piezas_desde_cortes
from .cantos import aplicar_modo_canto_a_todas
from .dxf_export import generar_dxf_bytes_por_placa
from .empaquetador import optimizar
from .etiquetas_export import generar_etiquetas_bytes
from .modelos import Config as OptimizadorConfig, ModoCanto, ModoPlaca, Resultado
from .pdf_export import generar_pdf_bytes


def _config_desde_ajustes(ancho_placa: int, largo_placa: int, numero_orden: str, cliente: str, fecha: str) -> OptimizadorConfig:
    return OptimizadorConfig(
        placa_largo=float(largo_placa),
        placa_ancho=float(ancho_placa),
        kerf=config.OPTIMIZADOR_KERF_MM,
        margen=config.OPTIMIZADOR_MARGEN_MM,
        modo_placa=ModoPlaca(config.OPTIMIZADOR_MODO_PLACA),
        modo_canto=ModoCanto(config.OPTIMIZADOR_MODO_CANTO),
        espesor_canto=config.OPTIMIZADOR_ESPESOR_CANTO_MM,
        canto_umbral=config.OPTIMIZADOR_CANTO_UMBRAL_MM,
        numero_orden=numero_orden,
        cliente=cliente,
        fecha=fecha,
    )


def calcular_resultado(
    cortes: list[dict],
    ancho_placa: int,
    largo_placa: int,
    numero_orden: str = "-",
    cliente: str = "-",
    fecha: str = "-",
) -> Resultado:
    """Corre el nesting real (empaquetador guillotina de Kutit Adrian)
    sobre los cortes dados. Lanza `optimizador.errores.OptimizadorError` (o
    una subclase) si algo no es válido."""
    cfg = _config_desde_ajustes(ancho_placa, largo_placa, numero_orden, cliente, fecha)
    piezas = piezas_desde_cortes(cortes, cfg.espesor_canto)
    aplicar_modo_canto_a_todas(piezas, cfg.modo_canto, cfg.canto_umbral)
    return optimizar(piezas, cfg)


def resultado_a_resumen(resultado: Resultado) -> dict:
    """Convierte un Resultado al mismo formato JSON que ya devuelve
    POST /distribucion (ver spec del formulario público), para poder
    reusar el mismo código de dibujo SVG en el panel interno."""
    from .resumen import metros_lineales_canto, metros_lineales_corte

    placas = []
    for placa in resultado.placas:
        placas.append({
            "ancho": placa.ancho,
            "largo": placa.largo,
            "piezas": [
                {
                    "etiqueta": pc.pieza.descripcion,
                    "x": pc.x, "y": pc.y,
                    "ancho": pc.ancho_x, "alto": pc.alto_y,
                    "rotada": pc.rotada,
                }
                for pc in placa.piezas
            ],
            "aprovechamiento": round(placa.aprovechamiento, 1),
            "sobrante": round(100 - placa.aprovechamiento, 1),
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
