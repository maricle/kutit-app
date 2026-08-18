from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class FilaCorte(BaseModel):
    descripcion: str = ""
    cantidad: int = 1
    alto: int = 2750
    ancho: int = 1830
    canto_1: bool = False
    canto_2: bool = False
    canto_3: bool = False
    canto_4: bool = False
    rotar: bool = True


class SolicitudCorteIn(BaseModel):
    contacto: str
    telefono: str
    email: Optional[str] = None
    fecha: Optional[str] = None
    material: str = "MDF"
    cortes: list[FilaCorte] = Field(default_factory=list)

    @field_validator("contacto", "telefono")
    @classmethod
    def no_vacio(cls, v):
        if not v or not v.strip():
            raise ValueError("campo requerido")
        return v.strip()


class SolicitudCorteUpdate(BaseModel):
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    fecha: Optional[str] = None
    material: Optional[str] = None
    cortes: Optional[list[FilaCorte]] = None


class CancelarIn(BaseModel):
    motivo: Optional[str] = None


class Etapa(str, Enum):
    por_hacer = "por_hacer"
    en_proceso = "en_proceso"
    terminado = "terminado"


class EtapaIn(BaseModel):
    etapa: Etapa
