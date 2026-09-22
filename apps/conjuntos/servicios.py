"""Asistente de creación de conjuntos (HU-03). No sabe nada de HTTP: eso es de las vistas.

El asistente guarda cada paso apenas se completa, así que un conjunto a medio configurar ya
existe en la base, pero no queda operativo hasta cumplir todos los requisitos.
"""
from dataclasses import asdict, dataclass

from django.db import transaction

from apps.conjuntos.models import Conjunto
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.permisos.servicios import es_superusuario


class ConjuntoIncompleto(Exception):
    """El conjunto no cumple los mínimos para quedar operativo."""

    def __init__(self, faltantes):
        super().__init__(faltantes)
        self.faltantes = faltantes


@dataclass(frozen=True)
class Requisito:
    clave: str
    descripcion: str
    cumplido: bool
    # Falso mientras el módulo que lo cumple no esté construido.
    disponible: bool = True

    def como_dict(self):
        return asdict(self)


def crear_conjunto(persona, nombre, direccion="", acento=None):
    """Paso 1 del asistente: los datos básicos. El conjunto nace activo y no operativo.

    Quien lo crea desde un rol de conjunto queda como su Administración: así el conjunto no nace
    sin gobierno y quien lo creó puede terminar el asistente. El Superusuario no, porque no opera
    dentro de los conjuntos (maestro §5.3): le asigna un administrador en el paso 2.
    """
    datos = {"nombre": nombre, "direccion": direccion}
    if acento:
        datos["acento"] = acento
    with transaction.atomic():
        conjunto = Conjunto.objects.create(**datos)
        if not es_superusuario(persona):
            Asignacion.objects.create(persona=persona, rol=Rol.ADMINISTRACION, conjunto=conjunto)
    return conjunto


def editar_datos(conjunto, **datos):
    for campo, valor in datos.items():
        setattr(conjunto, campo, valor)
    conjunto.save(update_fields=list(datos))
    return conjunto


def administradores(conjunto):
    """Personas con rol Administración vigente en el conjunto."""
    return (
        Asignacion.objects.vigentes()
        .filter(conjunto=conjunto, rol=Rol.ADMINISTRACION)
        .select_related("persona")
        .order_by("persona__apellidos", "persona__nombres")
    )


def requisitos_para_operar(conjunto):
    """Lo que el maestro §3.1 exige antes de dejar operativo un conjunto.

    Áreas, reglamento y reglas beta todavía no tienen módulo (HU-09, HU-33, HU-10). Mientras no
    existan cuentan como no cumplidos, así que ningún conjunto puede quedar operativo: el
    invariante se mantiene aunque el asistente esté incompleto.
    """
    return [
        Requisito(
            "datos_basicos",
            "Datos básicos: nombre y dirección",
            bool(conjunto.nombre.strip() and conjunto.direccion.strip()),
        ),
        Requisito(
            "administracion",
            "Al menos una persona con rol Administración",
            administradores(conjunto).exists(),
        ),
        Requisito("areas", "Catálogo de áreas comunes", False, disponible=False),
        Requisito("reglamento", "Reglamento cargado", False, disponible=False),
        Requisito("reglas_beta", "Reglas beta de reserva", False, disponible=False),
    ]


def activar(conjunto):
    faltantes = [requisito for requisito in requisitos_para_operar(conjunto) if not requisito.cumplido]
    if faltantes:
        raise ConjuntoIncompleto(faltantes)
    conjunto.operativo = True
    conjunto.save(update_fields=["operativo"])
    return conjunto
