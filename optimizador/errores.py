"""Excepciones propias del optimizador.

Todas heredan de :class:`OptimizadorError` para poder capturarlas en un
solo ``except`` y devolver un mensaje claro al llamador en vez de un
traceback. Portado de Kutit Adrian (kutit_kleba/src/kutit/errores.py).
"""


class OptimizadorError(Exception):
    """Error base del optimizador."""


class ErrorPiezaInvalida(OptimizadorError):
    """Una pieza tiene medidas negativas, cero o incoherentes."""


class ErrorPiezaDemasiadoGrande(OptimizadorError):
    """Una pieza no entra en la placa ni siquiera rotada."""


class ErrorConfiguracion(OptimizadorError):
    """Parámetros de ejecución inconsistentes (placa, kerf, margen...)."""
