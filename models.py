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
    con_material: bool = True
    material: Optional[str] = "MDF"
    material_id: Optional[int] = None
    material_manual_id: Optional[int] = None
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
    con_material: Optional[bool] = None
    material: Optional[str] = None
    material_id: Optional[int] = None
    material_manual_id: Optional[int] = None
    cortes: Optional[list[FilaCorte]] = None


class CancelarIn(BaseModel):
    motivo: Optional[str] = None


class Etapa(str, Enum):
    por_hacer = "por_hacer"
    en_proceso = "en_proceso"
    terminado = "terminado"


class EtapaIn(BaseModel):
    etapa: Etapa


class MedidaMaterialIn(BaseModel):
    odoo_id: int
    nombre: str
    ancho: Optional[int] = None
    largo: Optional[int] = None
    habilitado: bool = True
    precio_manual: Optional[float] = None


class MaterialManualIn(BaseModel):
    id: Optional[int] = None
    categoria: str = "material"
    nombre: str
    precio: float
    ancho: Optional[int] = None
    largo: Optional[int] = None
    habilitado: bool = True

    @field_validator("categoria")
    @classmethod
    def categoria_valida(cls, v):
        if v not in ("material", "servicio"):
            raise ValueError("categoria debe ser 'material' o 'servicio'")
        return v
