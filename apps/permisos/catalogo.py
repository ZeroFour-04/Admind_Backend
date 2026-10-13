"""Catálogo fijo de roles y permisos (maestro §5.3).

No se edita desde la interfaz ni desde la API: un cambio se hace aquí y se despliega.
El reparto de permisos por rol es provisional hasta validarlo con un administrador real (maestro §11.4).
"""
from django.db import models


class Rol(models.TextChoices):
    SUPERUSUARIO = "superusuario", "Superusuario"
    ADMINISTRACION = "administracion", "Administración"
    SECRETARIA = "secretaria", "Secretaría"
    VIGILANCIA = "vigilancia", "Vigilancia"
    RESIDENTE = "residente", "Residente"


ROLES_DE_PLATAFORMA = frozenset({Rol.SUPERUSUARIO.value})
ROLES_DE_CONJUNTO = frozenset(Rol.values) - ROLES_DE_PLATAFORMA


PERMISOS_DE_PLATAFORMA = frozenset({
    "conjunto.crear", "conjunto.activar", "gobierno.restaurar",
    "auditoria_tecnica.ver", "registro.anular", "sistema.operar",
    "usuario.gestionar",
})

PERMISOS = PERMISOS_DE_PLATAFORMA | frozenset({
    "conjunto.editar", "conjunto.branding",
    "persona.buscar", "persona.vincular",
    "regla.ver", "regla.configurar",
    "area.ver", "area.gestionar",
    "reserva.solicitar", "reserva.ver_todas", "reserva.aprobar", "reserva.rechazar", "reserva.cancelar_ajena",
    "reserva.declarar_pago",
    "usuario.gestionar", "rol.asignar", "vinculo.gestionar",
    "visitante.registrar", "visitante.ver_historico",
    "ingreso.registrar", "ingreso.ver_historico",
    "caso.crear", "caso.ver_todos", "caso.responder", "caso.gestionar",
    "solicitud.bandeja_ver", "solicitud.priorizar", "solicitud.rechazar_formal",
    "infraccion.registrar", "infraccion.ver", "infraccion.cerrar",
    "anuncio.publicar", "anuncio.dirigir",
    "cita.agendar_propia", "cita.gestionar_horario", "cita.ver_todas",
    "documento.subir", "documento.ver", "documento.descargar",
    "importacion.ejecutar", "respaldo.generar", "auditoria.ver",
    "parqueadero.ver", "parqueadero.asignar", "parqueadero.gestionar",
    "pago.ver", "pago.confirmar", "pago.reportar",
})

# Exigen segundo factor (HU-02).
PERMISOS_SENSIBLES = PERMISOS_DE_PLATAFORMA | frozenset({
    "visitante.ver_historico", "ingreso.ver_historico", "documento.descargar", "respaldo.generar",
    "usuario.gestionar", "rol.asignar", "auditoria.ver",
    "persona.buscar", "persona.vincular",
    "infraccion.registrar", "infraccion.ver", "infraccion.cerrar",
    "solicitud.bandeja_ver",
    # Muestra quién vive en cada vivienda y sus comprobantes de pago (HU-35, D5 a).
    "pago.ver",
})

PERMISOS_POR_ROL = {
    Rol.SUPERUSUARIO: PERMISOS,
    Rol.ADMINISTRACION: frozenset({
        "conjunto.crear", "conjunto.activar",
        "conjunto.editar", "conjunto.branding",
        "persona.buscar", "persona.vincular",
        "regla.ver", "regla.configurar",
        "area.ver", "area.gestionar",
        "reserva.ver_todas", "reserva.aprobar", "reserva.rechazar", "reserva.cancelar_ajena",
        "reserva.declarar_pago",
        "usuario.gestionar", "rol.asignar", "vinculo.gestionar",
        "visitante.ver_historico", "ingreso.ver_historico",
        "caso.ver_todos", "caso.responder",
        "solicitud.bandeja_ver", "solicitud.priorizar",
        "infraccion.registrar", "infraccion.ver", "infraccion.cerrar",
        "anuncio.publicar", "anuncio.dirigir",
        "cita.gestionar_horario", "cita.ver_todas",
        "documento.subir", "documento.ver", "documento.descargar",
        "importacion.ejecutar", "respaldo.generar", "auditoria.ver",
        "parqueadero.ver", "parqueadero.asignar", "parqueadero.gestionar",
        "pago.ver", "pago.confirmar",
    }),
    # Clasifica y no decide el fondo: no aprueba reservas ni responde casos. Descarta por causal formal
    # (`solicitud.rechazar_formal`) y redirige los casos al administrador (`caso.gestionar`).
    Rol.SECRETARIA: frozenset({
        "area.ver", "reserva.ver_todas",
        "solicitud.bandeja_ver", "solicitud.priorizar", "solicitud.rechazar_formal",
        "anuncio.publicar", "anuncio.dirigir", "caso.ver_todos", "caso.gestionar",
        "pago.ver",
    }),
    Rol.VIGILANCIA: frozenset({
        "visitante.registrar", "reserva.ver_todas", "ingreso.registrar",
    }),
    Rol.RESIDENTE: frozenset({
        "area.ver", "reserva.solicitar", "caso.crear", "cita.agendar_propia", "documento.ver",
        "pago.reportar",
    }),
}
