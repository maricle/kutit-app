import base64

import anthropic
from pydantic import BaseModel, Field

import config


class ExtraccionError(Exception):
    pass


class PiezaExtraida(BaseModel):
    descripcion: str = ""
    cantidad: int = 1
    alto: int = 0
    ancho: int = 0
    canto_1: bool = False
    canto_2: bool = False
    canto_3: bool = False
    canto_4: bool = False


class ExtraccionPiezas(BaseModel):
    piezas: list[PiezaExtraida] = Field(default_factory=list)


PROMPT = """Esta imagen es un pedido de corte de placas (madera, MDF, melamina, acrílico, etc.) \
que un cliente le envió a una carpintería/CNC, como foto de un papel escrito a mano, una captura \
de WhatsApp o un plano. Extraé cada pieza distinta como una fila con:

- descripcion: qué es la pieza (ej. "estante", "tapa", "lateral").
- cantidad: cuántas piezas iguales.
- alto: la medida del lado "largo" en milímetros.
- ancho: la medida del lado "ancho" en milímetros.
- canto_1 / canto_2: si lleva tapacanto en cada uno de los dos lados largos.
- canto_3 / canto_4: si lleva tapacanto en cada uno de los dos lados anchos.

Si las medidas están en cm o metros, convertilas a milímetros. Si una medida o cantidad \
no está clara, usá tu mejor estimación según el contexto. Si no hay cantos indicados en \
absoluto, dejalos todos en false. Si la imagen no tiene ninguna pieza reconocible, devolvé \
una lista vacía."""


def extraer_piezas(imagen_bytes: bytes, media_type: str) -> list[dict]:
    if not config.ANTHROPIC_API_KEY:
        raise ExtraccionError("Falta configurar ANTHROPIC_API_KEY")

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    imagen_b64 = base64.standard_b64encode(imagen_bytes).decode("utf-8")

    try:
        response = client.messages.parse(
            model="claude-opus-5",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": imagen_b64},
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }],
            output_format=ExtraccionPiezas,
        )
    except anthropic.APIError as exc:
        raise ExtraccionError(str(exc)) from exc

    resultado = response.parsed_output
    if resultado is None:
        raise ExtraccionError("No se pudo interpretar la respuesta del modelo")
    return [p.model_dump() for p in resultado.piezas]
