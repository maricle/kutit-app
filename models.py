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
    espesor_canto_mm: Optional[float] = None
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
    tiene_veta: bool = False


class DistribucionIn(BaseModel):
    cortes: list[FilaCorte]
    ancho_placa: int
    largo_placa: int
    material_id: Optional[int] = None
    material_manual_id: Optional[int] = None


class MaterialManualIn(BaseModel):
    id: Optional[int] = None
    categoria: str = "material"
    nombre: str
    precio: float
    ancho: Optional[int] = None
    largo: Optional[int] = None
    habilitado: bool = True
    tiene_veta: bool = False

    @field_validator("categoria")
    @classmethod
    def categoria_valida(cls, v):
        if v not in ("material", "servicio"):
            raise ValueError("categoria debe ser 'material' o 'servicio'")
        return v


class ConfiguracionMaquinaIn(BaseModel):
    kerf_mm: float
    margen_mm: float = 0
    modo_canto: str = "agregar"
    espesor_canto_default_mm: float = 0.45
    canto_umbral_mm: float = 0

    @field_validator("modo_canto")
    @classmethod
    def modo_canto_valido(cls, v):
        if v not in ("ninguno", "descontar", "agregar"):
            raise ValueError("modo_canto debe ser 'ninguno', 'descontar' o 'agregar'")
        return v
