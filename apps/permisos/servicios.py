"""Qué puede hacer una persona y dónde. Los permisos se calculan, no se guardan.

También asigna, cambia y retira roles del catálogo (HU-06): solo cierra vigencias, nunca borra.
Una persona tiene un solo rol vigente por conjunto.
"""
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.auditoria import servicios as auditoria
from apps.conjuntos.models import Conjunto
from apps.permisos.catalogo import PERMISOS_POR_ROL, PERMISOS_SENSIBLES, ROLES_DE_CONJUNTO, Rol
from apps.permisos.models import Asignacion


class RolFueraDelCatalogo(Exception):
    """El rol no es un rol de conjunto del catálogo. Los roles no se crean ni se editan (maestro §5.3)."""


class RolYaAsignado(Exception):
    """La persona ya tiene un rol vigente en el conjunto: se cambia, no se suma otro."""


MENSAJE_YA_TIENE_ROL = "Esta persona ya tiene un rol en el conjunto. Cámbialo en lugar de asignarle otro."


class MismoRol(Exception):
    """Se pidió cambiar el rol por el que ya tiene."""


class UltimaAdministracion(Exception):
    """Retirarlo dejaría el conjunto sin Administración (maestro §5.11: nunca cero gobierno)."""


def es_superusuario(persona):
    return Asignacion.objects.vigentes().filter(persona=persona, rol=Rol.SUPERUSUARIO).exists()


def conjuntos_disponibles(persona):
    """Conjuntos activos donde la persona puede operar (HU-26).

    El Superusuario gobierna la plataforma: puede elegir cualquiera. El resto, solo aquellos
    donde tiene al menos una asignación vigente; nadie ve los conjuntos de otros.
    """
    conjuntos = Conjunto.objects.filter(activo=True).order_by("nombre")
    if es_superusuario(persona):
        return conjuntos
    con_asignacion = Asignacion.objects.vigentes().filter(persona=persona).values("conjunto_id")
    return conjuntos.filter(pk__in=con_asignacion)


def puede_operar_en(persona, conjunto_id):
    return conjuntos_disponibles(persona).filter(pk=conjunto_id).exists()


def permisos_efectivos(persona, conjunto_id):
    """Unión de los permisos de sus roles vigentes en ese conjunto y de sus roles de plataforma.

    Un rol de otro conjunto no aporta nada (HU-06). Sin conjunto, solo cuentan los roles de plataforma;
    el Superusuario aporta todos los permisos del catálogo.
    """
    roles = (
        Asignacion.objects.vigentes()
        .filter(persona=persona)
        .filter(Q(conjunto_id=conjunto_id) | Q(conjunto__isnull=True))
        .values_list("rol", flat=True)
    )
    permisos = set()
    for rol in roles:
        permisos |= PERMISOS_POR_ROL[rol]
    return permisos


def tiene_permiso(persona, conjunto_id, permiso):
    return permiso in permisos_efectivos(persona, conjunto_id)


def tiene_permisos_sensibles(persona):
    """Si alguno de sus roles vigentes, en cualquier conjunto, trae un permiso sensible (HU-02).

    Se mira en todos los conjuntos y no solo en el activo: el segundo factor se pide al entrar,
    antes de elegir conjunto.
    """
    roles = Asignacion.objects.vigentes().filter(persona=persona).values_list("rol", flat=True).distinct()
    return any(PERMISOS_POR_ROL[rol] & PERMISOS_SENSIBLES for rol in roles)


def puede_crear_conjuntos(persona):
    """Si alguno de sus roles vigentes trae `conjunto.crear`, en la plataforma o en un conjunto activo.

    Crear un conjunto no es una operación dentro de uno: se hace desde el selector, antes de elegir
    ninguno. Por eso se mira en todos sus conjuntos y no solo en el activo. Un conjunto desactivado
    no cuenta: desde él no podría ni entrar.
    """
    roles = (
        Asignacion.objects.vigentes()
        .filter(persona=persona)
        .filter(Q(conjunto__isnull=True) | Q(conjunto__activo=True))
        .values_list("rol", flat=True)
        .distinct()
    )
    return any("conjunto.crear" in PERMISOS_POR_ROL[rol] for rol in roles)


# Asignar y retirar roles (HU-06)


def datos_de_la_asignacion(asignacion):
    return {
        "persona": asignacion.persona_id,
        "rol": asignacion.rol,
        "vigencia_desde": asignacion.vigencia_desde,
        "vigencia_hasta": asignacion.vigencia_hasta,
    }


def crear_asignacion(persona, rol, conjunto_id):
    """Si otra petición le dio un rol en el mismo instante, la restricción de la base lo impide."""
    try:
        with transaction.atomic():
            return Asignacion.objects.create(persona=persona, rol=rol, conjunto_id=conjunto_id)
    except IntegrityError as error:
        if "asignacion_un_rol_por_conjunto" in str(error):
            raise RolYaAsignado() from error
        raise


def asignar_rol(actor, persona, rol, conjunto_id):
    """Le da a la persona su rol en el conjunto. Si ya tiene uno, se cambia con `cambiar_rol`."""
    if rol not in ROLES_DE_CONJUNTO:
        raise RolFueraDelCatalogo()
    if Asignacion.objects.vigentes().filter(persona=persona, conjunto_id=conjunto_id).exists():
        raise RolYaAsignado()
    with transaction.atomic():
        asignacion = crear_asignacion(persona, rol, conjunto_id)
        auditoria.registrar(
            actor, "rol.asignar", "Asignacion", asignacion.id, despues=datos_de_la_asignacion(asignacion)
        )
    return asignacion


def retirar_rol(actor, asignacion, conjunto_id):
    """Cierra la vigencia hoy (plan P5). La comprobación del último administrador y el cambio van juntos.

    Se bloquean las asignaciones vigentes de Administración del conjunto: dos retiros a la vez no
    pueden dejarlo sin gobierno. Un `.count()` no bloquearía nada; por eso se evalúa la lista.
    """
    with transaction.atomic():
        if asignacion.rol == Rol.ADMINISTRACION:
            administradores = list(
                Asignacion.objects.vigentes()
                .filter(conjunto_id=conjunto_id, rol=Rol.ADMINISTRACION)
                .select_for_update()
            )
            if len(administradores) <= 1:
                raise UltimaAdministracion()
        antes = datos_de_la_asignacion(asignacion)
        asignacion.vigencia_hasta = timezone.localdate()
        asignacion.save(update_fields=["vigencia_hasta"])
        auditoria.registrar(
            actor, "rol.retirar", "Asignacion", asignacion.id, antes=antes, despues=datos_de_la_asignacion(asignacion)
        )
    return asignacion


def cambiar_rol(actor, asignacion, rol, conjunto_id):
    """Reemplaza su rol en el conjunto por otro del catálogo: cierra el actual hoy y abre el nuevo.

    Las dos cosas van en la misma transacción: la persona nunca queda con dos roles ni sin ninguno.
    Dejar de ser Administración pasa por la misma comprobación que retirar ese rol.
    """
    if rol not in ROLES_DE_CONJUNTO:
        raise RolFueraDelCatalogo()
    if rol == asignacion.rol:
        raise MismoRol()
    with transaction.atomic():
        if asignacion.rol == Rol.ADMINISTRACION:
            administradores = list(
                Asignacion.objects.vigentes()
                .filter(conjunto_id=conjunto_id, rol=Rol.ADMINISTRACION)
                .select_for_update()
            )
            if len(administradores) <= 1:
                raise UltimaAdministracion()
        antes = datos_de_la_asignacion(asignacion)
        asignacion.vigencia_hasta = timezone.localdate()
        asignacion.save(update_fields=["vigencia_hasta"])
        nueva = crear_asignacion(asignacion.persona, rol, conjunto_id)
        auditoria.registrar(
            actor,
            "rol.cambiar",
            "Asignacion",
            nueva.id,
            antes=antes,
            despues=datos_de_la_asignacion(nueva),
            detalle={"asignacion_anterior": asignacion.id},
        )
    return nueva


def retirar_roles_del_conjunto(actor, persona, conjunto_id):
    """Cierra todas las asignaciones vigentes de una persona en el conjunto como una sola operación."""
    with transaction.atomic():
        administradores = list(
            Asignacion.objects.vigentes()
            .filter(conjunto_id=conjunto_id, rol=Rol.ADMINISTRACION)
            .select_for_update()
        )
        asignaciones = list(
            Asignacion.objects.vigentes()
            .filter(persona=persona, conjunto_id=conjunto_id)
            .select_for_update()
        )
        administraciones_a_retirar = sum(
            asignacion.rol == Rol.ADMINISTRACION for asignacion in asignaciones
        )
        if administraciones_a_retirar and len(administradores) <= administraciones_a_retirar:
            raise UltimaAdministracion()

        for asignacion in asignaciones:
            antes = datos_de_la_asignacion(asignacion)
            asignacion.vigencia_hasta = timezone.localdate()
            asignacion.save(update_fields=["vigencia_hasta"])
            auditoria.registrar(
                actor,
                "rol.retirar",
                "Asignacion",
                asignacion.id,
                antes=antes,
                despues=datos_de_la_asignacion(asignacion),
            )
    return asignaciones
