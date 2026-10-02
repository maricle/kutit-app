"""Motor de nesting real (corte guillotina) y generación de archivos de
corte (DXF/PDF/etiquetas), portado de la herramienta de consola standalone
"Kutit Adrian" (ver kutit spec/spec-optimizador-corte.md). Se usa solo desde
el panel interno — el formulario público sigue con su propio packer
simplificado en calculos.py (ver el spec para el porqué)."""

import matplotlib

# Backend sin ventana: este paquete corre en un servidor, nunca muestra una
# figura interactiva. Tiene que fijarse antes de que cualquier submódulo
# importe matplotlib.pyplot.
matplotlib.use("Agg", force=True)

from .errores import OptimizadorError  # noqa: E402,F401
from .modelos import Resultado  # noqa: E402,F401
from .servicio import (  # noqa: E402,F401
    calcular_resultado,
    generar_dxf_zip,
    generar_etiquetas_pdf,
    generar_pdf,
    resultado_a_resumen,
)
