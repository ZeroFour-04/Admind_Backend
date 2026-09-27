"""Reglas alfa: en código, siempre activas; el administrador no las desactiva (maestro §5.10, HU-13).

«La mora solo aplica a áreas no esenciales» vive en `REQUIERE_PAZ_Y_SALVO` y en la validación del
catálogo. Las alfas de piscina (acompañante de menores, salvavidas) y de cobro quedan fuera: todavía
no hay datos con qué evaluarlas.
"""
from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone

from apps.unidades.models import VinculoUnidad


@dataclass(frozen=True)
class Resultado:
    """Lo que dijo una regla, alfa o beta, sobre una solicitud. `motivo` va vacío si cumple.

    Las alfas no tienen id ni parámetros; las beta llevan los de su versión (plan P10).
    """

    clave: str
    descripcion: str
    cumple: bool
    motivo: str = ""
    regla_id: object = None
    parametros: dict = field(default_factory=dict)

    def como_dict(self):
        return {
            "id": self.regla_id,
            "tipo": self.clave,
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
    cumple = area.activo and not area.en_mantenimiento
    return Resultado(
        "AREA_DISPONIBLE",
        "El área está activa y no está en mantenimiento",
        cumple,
        "" if cumple else "Esta área no está disponible para reservas en este momento.",
    )


ALFAS = [reside, no_en_el_pasado, area_disponible]
