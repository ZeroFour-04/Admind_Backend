"""Reglas del sistema: fijas en el código, siempre activas. Nadie las configura ni las apaga.

Hasta el 2026-10-06 se llamaban alfa. Hoy una regla alfa es la que Administración define para
todo el conjunto (`catalogo.py`). Las de piscina y de cobro siguen fuera: no hay datos con qué evaluarlas.
"""
from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone

from apps.areas.models import ModoDeUso
from apps.unidades.models import VinculoUnidad


@dataclass(frozen=True)
class Resultado:
    """Lo que dijo una regla sobre una solicitud. `motivo` va vacío si cumple.

    `nivel` dice de dónde sale: `sistema`, `alfa` (del conjunto) o `beta` (del área). Las del
    sistema y el aforo no tienen id; las demás llevan el de su versión (plan P10).
    """

    clave: str
    descripcion: str
    cumple: bool
    motivo: str = ""
    regla_id: object = None
    parametros: dict = field(default_factory=dict)
    nivel: str = "sistema"

    def como_dict(self):
        return {
            "id": self.regla_id,
            "tipo": self.clave,
            "nivel": self.nivel,
            "descripcion": self.descripcion,
            "parametros": self.parametros,
            "cumple": self.cumple,
            "motivo": self.motivo,
        }


def reside(solicitud):
    """Solo quien tiene vínculo vigente con `reside = true` solicita a nombre de esa unidad."""
    cumple = VinculoUnidad.objects.vigentes().filter(
        persona_id=solicitud.persona_id, unidad_id=solicitud.unidad_id, reside=True
    ).exists()
    return Resultado(
        "RESIDE",
        "Solo quien vive en el apartamento solicita a su nombre",
        cumple,
        "" if cumple else "No vives en el apartamento elegido: solo quien vive ahí puede reservar a su nombre.",
    )


def no_en_el_pasado(solicitud):
    """La franja empieza después de ahora, en la hora del conjunto (America/Bogota)."""
    inicio = timezone.make_aware(datetime.combine(solicitud.fecha, solicitud.hora_inicio))
    cumple = inicio > timezone.now()
    return Resultado("NO_EN_EL_PASADO", "No se reserva en el pasado", cumple, "" if cumple else "La franja ya empezó.")


def area_disponible(solicitud):
    area = solicitud.area
    # El modo puede cambiar mientras la solicitud está en trámite: un área con ingreso ya no se reserva.
    cumple = area.activo and not area.en_mantenimiento and area.modo_uso == ModoDeUso.RESERVA
    return Resultado(
        "AREA_DISPONIBLE",
        "El área está activa, no está en mantenimiento y se usa con reserva",
        cumple,
        "" if cumple else "Esta área no está disponible para reservas en este momento.",
    )


REGLAS_DEL_SISTEMA = [reside, no_en_el_pasado, area_disponible]
