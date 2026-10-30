"""Prueba del intruso por endpoint y prueba transversal de rutas (maestro §5.4, HU-05, HU-26)."""
import uuid
from datetime import time, timedelta

import pytest
from django.urls import URLResolver, get_resolver, reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.views import APIView

from apps.anuncios.models import Anuncio, FotoDeAnuncio
from apps.auditoria.models import Registro
from apps.casos.models import Caso, FotoDeCaso
from apps.citas.models import Cita, EstadoCita, HorarioDeAtencion
from apps.areas.models import Area as AreaComun
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.documentos.models import Documento
from apps.ingresos.models import Ingreso
from apps.infracciones.models import RegistroDeInfraccion
from apps.notificaciones.models import Notificacion
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.reglas.models import Regla
from apps.reservas.models import Campana, ComprobanteDePago, EstadoSolicitud, Solicitud
from apps.unidades.models import Agrupacion, TipoVinculo, Unidad, VinculoUnidad
from apps.pagos.models import Comprobante, PagoDeAdministracion
from apps.parqueaderos.models import AsignacionParqueadero, Parqueadero
from apps.visitantes.models import Visitante
from tests.aislamiento.models import Area

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"


def crear_usuario(correo, *roles):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres="Laura",
        apellidos="Gómez",
    )
    for rol, conjunto in roles:
        Asignacion.objects.create(persona=persona, rol=rol, conjunto=conjunto)
    return Usuario.objects.create_user(correo, CONTRASENA, persona)


def cliente_para(correo):
    """Sesión con el segundo factor dado por verificado: su flujo se prueba en cuentas (HU-02)."""
    cliente = APIClient()
    respuesta = cliente.post("/auth/login/", {"correo": correo, "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {respuesta.json()['token']}")
    TokenDeSesion.objects.filter(usuario__correo=correo).update(dos_factores_verificado=True)
    return cliente


def crear_area(conjunto, nombre):
    with usar_conjunto(conjunto.id):
        return Area.objects.create(nombre=nombre)


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río")


@pytest.fixture
def mirador():
    return Conjunto.objects.create(nombre="Mirador")


@pytest.fixture
def intruso(torres):
    """Administración en Torres del Río y nada en Mirador. Con un solo conjunto, entra directo."""
    crear_usuario("admin@torres.com", (Rol.ADMINISTRACION, torres))
    return cliente_para("admin@torres.com")


# Registro de la prueba del intruso. Toda ruta con datos de un conjunto se agrega aquí;
# si no, falla test_toda_ruta_de_la_api_esta_cubierta.


def detalle_de_area(otro_conjunto):
    return reverse("pruebas-area-detalle", kwargs={"pk": crear_area(otro_conjunto, "Piscina").pk})


def listado_de_areas(otro_conjunto):
    return reverse("pruebas-areas"), str(crear_area(otro_conjunto, "Piscina").pk)


def listado_de_visitantes(otro_conjunto):
    with usar_conjunto(otro_conjunto.id):
        unidad = Unidad.objects.create(nombre="Torre 1 – 101")
        visitante = Visitante.objects.create(nombre="María Pérez", cedula="123456789", unidad=unidad)
    return reverse("visitantes"), str(visitante.pk)


def usuario_de(otro_conjunto):
    correo = f"vecino{Usuario.objects.count()}@otro.com"
    return crear_usuario(correo, (Rol.RESIDENTE, otro_conjunto))


def detalle_de_usuario(otro_conjunto):
    return reverse("usuario-detalle", kwargs={"usuario_id": usuario_de(otro_conjunto).pk})


def asignar_rol_en(otro_conjunto):
    usuario = usuario_de(otro_conjunto)

    def intacto():
        return list(Asignacion.objects.filter(persona=usuario.persona).values_list("rol", flat=True)) == ["residente"]

    return "post", reverse("usuario-roles", kwargs={"usuario_id": usuario.pk}), intacto


def retirar_rol_en(otro_conjunto):
    usuario = usuario_de(otro_conjunto)
    asignacion = Asignacion.objects.get(persona=usuario.persona)

    def intacto():
        return Asignacion.objects.get(pk=asignacion.pk).vigencia_hasta is None

    url = reverse("usuario-rol-retirar", kwargs={"usuario_id": usuario.pk, "asignacion_id": asignacion.pk})
    return "post", url, intacto


def cambiar_rol_en(otro_conjunto):
    usuario = usuario_de(otro_conjunto)
    asignacion = Asignacion.objects.get(persona=usuario.persona)

    def intacto():
        roles = Asignacion.objects.filter(persona=usuario.persona).values_list("rol", "vigencia_hasta")
        return list(roles) == [("residente", None)]

    url = reverse("usuario-rol-cambiar", kwargs={"usuario_id": usuario.pk, "asignacion_id": asignacion.pk})
    return "post", url, intacto


def nada_escrito_en(otro_conjunto, persona):
    """Ni una asignación nueva para la persona ni un registro de auditoría en el otro conjunto."""
    with usar_conjunto(otro_conjunto.id):
        sin_registros = not Registro.objects.exists()
    return sin_registros and Asignacion.objects.filter(persona=persona).count() == 1


def buscar_persona_en(otro_conjunto):
    persona = usuario_de(otro_conjunto).persona
    return "post", reverse("persona-buscar"), lambda: nada_escrito_en(otro_conjunto, persona)


def vincular_persona_en(otro_conjunto):
    persona = usuario_de(otro_conjunto).persona
    return "post", reverse("persona-vincular"), lambda: nada_escrito_en(otro_conjunto, persona)


def listado_de_usuarios(otro_conjunto):
    return reverse("usuarios"), str(usuario_de(otro_conjunto).pk)


def resumen_del_conjunto(otro_conjunto):
    return reverse("conjunto-actual"), str(otro_conjunto.pk)


def activar_conjunto(otro_conjunto):
    def intacto():
        return not Conjunto.objects.get(pk=otro_conjunto.pk).operativo

    return "post", reverse("conjunto-activar"), intacto


def identidad_del_conjunto(otro_conjunto):
    return reverse("conjunto-identidad"), str(otro_conjunto.pk)


def logo_del_conjunto(otro_conjunto):
    def intacto():
        return Conjunto.objects.get(pk=otro_conjunto.pk).logo_huella == ""

    return "put", reverse("conjunto-logo"), intacto


def reglamento_de(otro_conjunto):
    persona = usuario_de(otro_conjunto).persona
    with usar_conjunto(otro_conjunto.id):
        return Documento.objects.create(
            tipo="reglamento",
            contenido=b"%PDF-1.7 ajeno",
            nombre="ajeno.pdf",
            peso=14,
            huella="b" * 64,
            subido_por=persona,
        )


def datos_del_reglamento(otro_conjunto):
    return reverse("documento", kwargs={"tipo": "reglamento"}), reglamento_de(otro_conjunto).huella


def lista_de_documentos(otro_conjunto):
    return reverse("documentos"), reglamento_de(otro_conjunto).huella


def versiones_del_reglamento(otro_conjunto):
    return reverse("documento-versiones", kwargs={"tipo": "reglamento"}), str(reglamento_de(otro_conjunto).pk)


def subir_reglamento_en(otro_conjunto):
    reglamento_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return Documento.objects.count() == 1

    return "put", reverse("documento", kwargs={"tipo": "reglamento"}), intacto


def archivo_del_reglamento(otro_conjunto):
    reglamento_de(otro_conjunto)
    return reverse("documento-archivo", kwargs={"tipo": "reglamento"})


def archivo_de_una_version_ajena(otro_conjunto):
    ajeno = reglamento_de(otro_conjunto)
    return reverse("documento-version-archivo", kwargs={"tipo": "reglamento", "version_id": ajeno.pk})


def unidad_de(otro_conjunto):
    with usar_conjunto(otro_conjunto.id):
        return Unidad.objects.create(nombre=f"Torre 9 – {Unidad.objects.count() + 101}")


def listado_de_unidades(otro_conjunto):
    return reverse("unidades"), str(unidad_de(otro_conjunto).pk)


def detalle_de_unidad(otro_conjunto):
    return reverse("unidad-detalle", kwargs={"unidad_id": unidad_de(otro_conjunto).pk})


def listado_de_agrupaciones(otro_conjunto):
    with usar_conjunto(otro_conjunto.id):
        agrupacion = Agrupacion.objects.create(
            etiqueta="Torre", nombre="9", clave="torre 9", tipo_vivienda="apartamento", orden=1
        )
    return reverse("agrupaciones"), str(agrupacion.pk)


def estructura_en(nombre_de_ruta):
    def accion(otro_conjunto):
        with usar_conjunto(otro_conjunto.id):
            antes = Unidad.objects.count()

        def intacto():
            with usar_conjunto(otro_conjunto.id):
                return Unidad.objects.count() == antes

        return "post", reverse(nombre_de_ruta), intacto

    return accion


def registrar_vinculo_en(otro_conjunto):
    unidad = unidad_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return not VinculoUnidad.objects.filter(unidad=unidad).exists()

    return "post", reverse("unidad-vinculos", kwargs={"unidad_id": unidad.pk}), intacto


def cerrar_vinculo_en(otro_conjunto):
    unidad = unidad_de(otro_conjunto)
    persona = usuario_de(otro_conjunto).persona
    with usar_conjunto(otro_conjunto.id):
        vinculo = VinculoUnidad.objects.create(persona=persona, unidad=unidad, tipo=TipoVinculo.PROPIETARIO, reside=True)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return VinculoUnidad.objects.get(pk=vinculo.pk).vigencia_hasta is None

    url = reverse("vinculo-cerrar", kwargs={"unidad_id": unidad.pk, "vinculo_id": vinculo.pk})
    return "post", url, intacto


def anuncio_de(otro_conjunto):
    autor = usuario_de(otro_conjunto).persona
    with usar_conjunto(otro_conjunto.id):
        return Anuncio.objects.create(titulo="Corte de agua", cuerpo="Jueves", alcance="conjunto", autor=autor)


def detalle_de_anuncio(otro_conjunto):
    return reverse("anuncio-detalle", kwargs={"anuncio_id": anuncio_de(otro_conjunto).pk})


def foto_de_anuncio(otro_conjunto):
    anuncio = anuncio_de(otro_conjunto)
    with usar_conjunto(otro_conjunto.id):
        foto = FotoDeAnuncio.objects.create(anuncio=anuncio, contenido=b"\x89PNG\r\n\x1a\n", tipo="image/png", orden=0)
    return reverse("anuncio-foto", kwargs={"anuncio_id": anuncio.pk, "foto_id": foto.pk})


def listado_de_anuncios(otro_conjunto):
    return reverse("anuncios"), str(anuncio_de(otro_conjunto).pk)


def listado_de_notificaciones(otro_conjunto):
    """Un aviso del otro conjunto para la misma persona: tampoco aparece en su bandeja."""
    intruso = Usuario.objects.get(correo="admin@torres.com").persona
    with usar_conjunto(otro_conjunto.id):
        notificacion = Notificacion.objects.create(
            persona=intruso, titulo="Ajeno", cuerpo="", origen="anuncio", referencia=uuid.uuid4()
        )
    return reverse("notificaciones"), str(notificacion.pk)


def area_comun_de(otro_conjunto):
    with usar_conjunto(otro_conjunto.id):
        return AreaComun.objects.create(
            nombre=f"Salón {AreaComun.objects.count() + 1}",
            hora_apertura=time(8),
            hora_cierre=time(20),
            duracion_franja_minutos=120,
            aforo_maximo=50,
        )


def regla_de(otro_conjunto):
    area = area_comun_de(otro_conjunto)
    autor = usuario_de(otro_conjunto).persona
    with usar_conjunto(otro_conjunto.id):
        return Regla.objects.create(
            area=area, tipo="CUPO_POR_UNIDAD", parametros={"reservas": 2, "dias": 30}, creada_por=autor
        )


def detalle_de_regla(otro_conjunto):
    return reverse("regla-detalle", kwargs={"regla_id": regla_de(otro_conjunto).pk})


def listado_de_reglas(otro_conjunto):
    return reverse("reglas"), str(regla_de(otro_conjunto).pk)


def catalogo_de_reglas(otro_conjunto):
    return reverse("reglas-catalogo"), str(regla_de(otro_conjunto).pk)


def retirar_regla_en(otro_conjunto):
    regla = regla_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return Regla.objects.get(pk=regla.pk).vigencia_hasta is None

    return "post", reverse("regla-retirar", kwargs={"regla_id": regla.pk}), intacto


def solicitud_de(otro_conjunto):
    area = area_comun_de(otro_conjunto)
    persona = usuario_de(otro_conjunto).persona
    with usar_conjunto(otro_conjunto.id):
        return Solicitud.objects.create(
            area=area,
            persona=persona,
            fecha=timezone.localdate() + timedelta(days=1),
            hora_inicio=time(8),
            hora_fin=time(10),
            bloqueo_vence_en=timezone.now() + timedelta(minutes=3),
        )


def franjas_de_area_ajena(otro_conjunto):
    manana = timezone.localdate() + timedelta(days=1)
    return f"{reverse('franjas')}?area={area_comun_de(otro_conjunto).pk}&fecha={manana}"


def detalle_de_solicitud(otro_conjunto):
    return reverse("solicitud-detalle", kwargs={"solicitud_id": solicitud_de(otro_conjunto).pk})


def listado_de_solicitudes(otro_conjunto):
    return reverse("solicitudes"), str(solicitud_de(otro_conjunto).pk)


def liberar_solicitud_en(otro_conjunto):
    solicitud = solicitud_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return Solicitud.objects.get(pk=solicitud.pk).estado == "EN_SOLICITUD"

    return "post", reverse("solicitud-liberar", kwargs={"solicitud_id": solicitud.pk}), intacto


def enviar_solicitud_en(otro_conjunto):
    solicitud = solicitud_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return Solicitud.objects.get(pk=solicitud.pk).estado == "EN_SOLICITUD"

    return "post", reverse("solicitud-enviar", kwargs={"solicitud_id": solicitud.pk}), intacto


def solicitud_apartada_de(otro_conjunto):
    """Una solicitud apartada del otro conjunto: la que Administración podría declarar como pagada."""
    solicitud = solicitud_de(otro_conjunto)
    unidad = unidad_de(otro_conjunto)
    with usar_conjunto(otro_conjunto.id):
        Solicitud.objects.filter(pk=solicitud.pk).update(estado=EstadoSolicitud.APARTADA, unidad=unidad)
    return solicitud


def pago_intacto_en(otro_conjunto, solicitud):
    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return Solicitud.objects.get(pk=solicitud.pk).pago_declarado_por_id is None

    return intacto


def declarar_pago_en(otro_conjunto):
    solicitud = solicitud_apartada_de(otro_conjunto)
    url = reverse("solicitud-pago", kwargs={"solicitud_id": solicitud.pk})
    return "post", url, pago_intacto_en(otro_conjunto, solicitud)


def retirar_pago_en(otro_conjunto):
    solicitud = solicitud_apartada_de(otro_conjunto)
    declarante = usuario_de(otro_conjunto).persona
    with usar_conjunto(otro_conjunto.id):
        Solicitud.objects.filter(pk=solicitud.pk).update(
            pago_declarado_por=declarante, pago_declarado_en=timezone.now()
        )

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return Solicitud.objects.get(pk=solicitud.pk).pago_declarado_por_id is not None

    return "post", reverse("solicitud-pago-retirar", kwargs={"solicitud_id": solicitud.pk}), intacto


def subir_comprobante_en(otro_conjunto):
    solicitud = solicitud_apartada_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return not ComprobanteDePago.objects.filter(solicitud=solicitud).exists()

    return "post", reverse("solicitud-comprobantes", kwargs={"solicitud_id": solicitud.pk}), intacto


def comprobante_de_otro_conjunto(otro_conjunto):
    solicitud = solicitud_apartada_de(otro_conjunto)
    persona = usuario_de(otro_conjunto).persona
    with usar_conjunto(otro_conjunto.id):
        comprobante = ComprobanteDePago.objects.create(
            solicitud=solicitud,
            contenido=b"%PDF-1.7 ajeno",
            tipo="application/pdf",
            nombre="ajeno.pdf",
            peso=14,
            huella="c" * 64,
            subido_por=persona,
        )
    return reverse("solicitud-comprobante", kwargs={"comprobante_id": comprobante.pk})


def ingreso_de(otro_conjunto):
    with usar_conjunto(otro_conjunto.id):
        area = AreaComun.objects.create(
            nombre="Gimnasio",
            modo_uso="ingreso",
            hora_apertura=time(5),
            hora_cierre=time(22),
            duracion_franja_minutos=None,
            permanencia_maxima_minutos=60,
            aforo_maximo=5,
        )
        persona = Persona.objects.create(
            tipo_documento=TipoDocumento.CC,
            numero_documento=str(Persona.objects.count() + 1023456789),
            nombres="Ana",
            apellidos="Ajena",
        )
        unidad = Unidad.objects.create(nombre="Casa 1")
        entrada = timezone.now()
        return Ingreso.objects.create(
            area=area,
            persona=persona,
            unidad=unidad,
            entrada_en=entrada,
            salida_prevista_en=entrada + timedelta(hours=1),
            registrado_por=persona,
        )


def listado_de_ingresos(otro_conjunto):
    return reverse("ingresos"), str(ingreso_de(otro_conjunto).pk)


def zonas_con_ingreso(otro_conjunto):
    return reverse("ingresos-zonas"), str(ingreso_de(otro_conjunto).area_id)


def buscar_residente_en(otro_conjunto):
    ingreso = ingreso_de(otro_conjunto)
    with usar_conjunto(otro_conjunto.id):
        total = Ingreso.objects.count()

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return Ingreso.objects.count() == total and Ingreso.objects.get(pk=ingreso.pk).estado == "ADENTRO"

    return "post", reverse("ingreso-residentes-buscar"), intacto


def salida_en(otro_conjunto):
    ingreso = ingreso_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return Ingreso.objects.get(pk=ingreso.pk).estado == "ADENTRO"

    return "post", reverse("ingreso-salida", kwargs={"ingreso_id": ingreso.pk}), intacto


def detalle_de_area_comun(otro_conjunto):
    return reverse("area-detalle", kwargs={"area_id": area_comun_de(otro_conjunto).pk})


def listado_de_areas_comunes(otro_conjunto):
    return reverse("areas"), str(area_comun_de(otro_conjunto).pk)


def pago_de(otro_conjunto):
    """Una vivienda del otro conjunto con el pago del mes reportado, con su comprobante."""
    unidad = unidad_de(otro_conjunto)
    persona = usuario_de(otro_conjunto).persona
    with usar_conjunto(otro_conjunto.id):
        pago = PagoDeAdministracion.objects.create(
            unidad=unidad, periodo=timezone.localdate().replace(day=1), reportado_por=persona, reportado_en=timezone.now()
        )
        comprobante = Comprobante.objects.create(
            pago=pago,
            contenido=b"%PDF-1.7 ajeno",
            tipo="application/pdf",
            nombre="ajeno.pdf",
            peso=14,
            huella="d" * 64,
            subido_por=persona,
        )
    return unidad, pago, comprobante


def tabla_de_pagos(otro_conjunto):
    unidad, _, _ = pago_de(otro_conjunto)
    return reverse("pagos-administracion"), str(unidad.pk)


def pagos_mios(otro_conjunto):
    unidad, _, _ = pago_de(otro_conjunto)
    return reverse("pagos-mios"), str(unidad.pk)


def comprobante_de_pago_ajeno(otro_conjunto):
    _, _, comprobante = pago_de(otro_conjunto)
    return reverse("pago-comprobante", kwargs={"comprobante_id": comprobante.pk})


def confirmar_pago_en(otro_conjunto):
    unidad, pago, _ = pago_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return PagoDeAdministracion.objects.get(pk=pago.pk).confirmado_por_id is None

    periodo = timezone.localdate().strftime("%Y-%m")
    return "post", reverse("pago-confirmacion", kwargs={"unidad_id": unidad.pk, "periodo": periodo}), intacto


def reportar_pago_en(otro_conjunto):
    unidad, pago, _ = pago_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return Comprobante.objects.filter(pago=pago).count() == 1

    return "post", reverse("pago-reportes"), intacto


def infraccion_de(otro_conjunto):
    persona = usuario_de(otro_conjunto).persona
    unidad = unidad_de(otro_conjunto)
    with usar_conjunto(otro_conjunto.id):
        return RegistroDeInfraccion.objects.create(
            unidad=unidad,
            descripcion_hecho="Hecho de otro conjunto",
            fecha_hecho=timezone.localdate(),
            registrado_por=persona,
            fecha_notificacion=timezone.now(),
        )


def detalle_de_infraccion(otro_conjunto):
    return reverse("infraccion-detalle", kwargs={"registro_id": infraccion_de(otro_conjunto).pk})


def listado_de_infracciones(otro_conjunto):
    return reverse("infracciones"), str(infraccion_de(otro_conjunto).pk)


def cerrar_infraccion_en(otro_conjunto):
    registro = infraccion_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return RegistroDeInfraccion.objects.get(pk=registro.pk).cierre_fecha is None

    return "post", reverse("infraccion-cierre", kwargs={"registro_id": registro.pk}), intacto


def anular_infraccion_en(otro_conjunto):
    registro = infraccion_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return not RegistroDeInfraccion.objects.get(pk=registro.pk).anulado

    return "post", reverse("infraccion-anulacion", kwargs={"registro_id": registro.pk}), intacto


def parqueadero_de(otro_conjunto):
    creador = usuario_de(otro_conjunto).persona
    with usar_conjunto(otro_conjunto.id):
        return Parqueadero.objects.create(
            codigo=f"V-{Parqueadero.objects.count() + 1:02d}", tipo="visitantes", creado_por=creador
        )


def listado_de_parqueaderos(otro_conjunto):
    return reverse("parqueaderos"), str(parqueadero_de(otro_conjunto).pk)


def parqueadero_de_residentes_de(otro_conjunto):
    """Un puesto de residentes asignado a una vivienda del otro conjunto."""
    creador = usuario_de(otro_conjunto).persona
    unidad = unidad_de(otro_conjunto)
    with usar_conjunto(otro_conjunto.id):
        puesto = Parqueadero.objects.create(
            codigo=f"R-{Parqueadero.objects.count() + 1:02d}", tipo="residentes", creado_por=creador
        )
        AsignacionParqueadero.objects.create(parqueadero=puesto, unidad=unidad, registrado_por=creador)
    return puesto, unidad


def historial_de_parqueadero(otro_conjunto):
    return reverse("parqueadero-asignaciones", kwargs={"parqueadero_id": parqueadero_de_residentes_de(otro_conjunto)[0].pk})


def mis_parqueaderos(otro_conjunto):
    puesto, _ = parqueadero_de_residentes_de(otro_conjunto)
    return reverse("parqueaderos-mios"), str(puesto.pk)


def asignar_parqueadero_en(otro_conjunto):
    puesto, unidad = parqueadero_de_residentes_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return AsignacionParqueadero.objects.filter(parqueadero=puesto, vigencia_hasta__isnull=True).count() == 1

    return "post", reverse("parqueadero-asignacion", kwargs={"parqueadero_id": puesto.pk}), intacto


def liberar_parqueadero_en(otro_conjunto):
    puesto, _ = parqueadero_de_residentes_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return AsignacionParqueadero.objects.filter(parqueadero=puesto, vigencia_hasta__isnull=True).count() == 1

    return "post", reverse("parqueadero-liberacion", kwargs={"parqueadero_id": puesto.pk}), intacto


def desactivar_parqueadero_en(otro_conjunto):
    parqueadero = parqueadero_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return Parqueadero.objects.get(pk=parqueadero.pk).activo

    return "post", reverse("parqueadero-desactivar", kwargs={"parqueadero_id": parqueadero.pk}), intacto


def salida_de_visitante_en(otro_conjunto):
    unidad = unidad_de(otro_conjunto)
    with usar_conjunto(otro_conjunto.id):
        visitante = Visitante.objects.create(nombre="María Pérez", cedula="123456789", unidad=unidad)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return Visitante.objects.get(pk=visitante.pk).hora_salida is None

    return "post", reverse("visitante-salida", kwargs={"visitante_id": visitante.pk}), intacto


def desactivar_area_comun(otro_conjunto):
    area = area_comun_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return AreaComun.objects.get(pk=area.pk).activo

    return "post", reverse("area-desactivar", kwargs={"area_id": area.pk}), intacto


def listado_de_la_bandeja(otro_conjunto):
    return reverse("solicitudes-bandeja"), str(solicitud_apartada_de(otro_conjunto).pk)


def solicitudes_de_area_ajena(otro_conjunto):
    return reverse("solicitudes-area", kwargs={"area_id": area_comun_de(otro_conjunto).pk})


def cerrar_solicitud_en(nombre_de_ruta):
    """Decidir o descartar una solicitud apartada de otro conjunto: tiene que seguir apartada."""

    def accion(otro_conjunto):
        solicitud = solicitud_apartada_de(otro_conjunto)

        def intacto():
            with usar_conjunto(otro_conjunto.id):
                return Solicitud.objects.get(pk=solicitud.pk).estado == EstadoSolicitud.APARTADA

        return "post", reverse(nombre_de_ruta, kwargs={"solicitud_id": solicitud.pk}), intacto

    return accion


def marcar_campana_en(otro_conjunto):
    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return not Campana.objects.exists()

    return "post", reverse("campanas"), intacto


def retirar_usuario_en(otro_conjunto):
    usuario = usuario_de(otro_conjunto)

    def intacto():
        roles = Asignacion.objects.filter(persona=usuario.persona).values_list("rol", "vigencia_hasta")
        return list(roles) == [("residente", None)]

    return "post", reverse("usuario-eliminar", kwargs={"usuario_id": usuario.pk}), intacto


def caso_de(otro_conjunto):
    autor = usuario_de(otro_conjunto).persona
    with usar_conjunto(otro_conjunto.id):
        return Caso.objects.create(titulo="Fuga de agua", cuerpo="Hay una fuga en el pasillo.", autor=autor)


def detalle_de_caso(otro_conjunto):
    return reverse("caso-detalle", kwargs={"caso_id": caso_de(otro_conjunto).pk})


def foto_de_caso(otro_conjunto):
    caso = caso_de(otro_conjunto)
    with usar_conjunto(otro_conjunto.id):
        foto = FotoDeCaso.objects.create(caso=caso, contenido=b"\x89PNG\r\n\x1a\n", tipo="image/png")
    return reverse("caso-foto", kwargs={"caso_id": caso.pk, "foto_id": foto.pk})


def listado_de_casos(otro_conjunto):
    return reverse("casos"), str(caso_de(otro_conjunto).pk)


def listado_de_horario(otro_conjunto):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres="Ana",
        apellidos="Ajena",
    )
    with usar_conjunto(otro_conjunto.id):
        horario = HorarioDeAtencion.objects.create(
            dias=[{"dia": 0, "activo": False}],
            actualizado_por=persona,
        )
    return reverse("cita-horario"), str(horario.id)


def listado_de_citas(otro_conjunto, nombre_ruta):
    residente = usuario_de(otro_conjunto).persona
    fecha = timezone.localdate() + timedelta(days=7)
    with usar_conjunto(otro_conjunto.id):
        cita = Cita.objects.create(
            conjunto=otro_conjunto,
            persona=residente,
            fecha=fecha,
            hora_inicio=time(8),
            hora_fin=time(10),
            estado=EstadoCita.AGENDADA,
            vence_en=timezone.now() + timedelta(days=7),
        )
    ruta = reverse(nombre_ruta)
    if nombre_ruta == "cita-agenda":
        ruta = f"{ruta}?fecha={fecha.isoformat()}"
    return ruta, str(cita.pk)


def mover_caso_en(nombre_de_ruta):
    """Cualquier transición sobre un caso de otro conjunto: tiene que quedar como estaba."""

    def accion(otro_conjunto):
        caso = caso_de(otro_conjunto)

        def intacto():
            with usar_conjunto(otro_conjunto.id):
                guardado = Caso.objects.get(pk=caso.pk)
            return (guardado.estado, guardado.prioridad) == ("ABIERTO", "NORMAL")

        return "post", reverse(nombre_de_ruta, kwargs={"caso_id": caso.pk}), intacto

    return accion


DETALLES = {
    "solicitudes-area": solicitudes_de_area_ajena,
    "caso-detalle": detalle_de_caso,
    "caso-foto": foto_de_caso,
    "pruebas-area-detalle": detalle_de_area,
    "usuario-detalle": detalle_de_usuario,
    "anuncio-detalle": detalle_de_anuncio,
    "anuncio-foto": foto_de_anuncio,
    "area-detalle": detalle_de_area_comun,
    "unidad-detalle": detalle_de_unidad,
    "regla-detalle": detalle_de_regla,
    "franjas": franjas_de_area_ajena,
    "solicitud-detalle": detalle_de_solicitud,
    "documento-archivo": archivo_del_reglamento,
    "documento-version-archivo": archivo_de_una_version_ajena,
    "solicitud-comprobante": comprobante_de_otro_conjunto,
    "pago-comprobante": comprobante_de_pago_ajeno,
    "parqueadero-asignaciones": historial_de_parqueadero,
    "infraccion-detalle": detalle_de_infraccion,
}
LISTADOS = {
    "solicitudes-bandeja": listado_de_la_bandeja,
    "casos": listado_de_casos,
    "cita-horario": listado_de_horario,
    "cita-agenda": lambda conjunto: listado_de_citas(conjunto, "cita-agenda"),
    "cita-bandeja": lambda conjunto: listado_de_citas(conjunto, "cita-bandeja"),
    "pruebas-areas": listado_de_areas,
    "usuarios": listado_de_usuarios,
    "conjunto-actual": resumen_del_conjunto,
    "conjunto-identidad": identidad_del_conjunto,
    "unidades": listado_de_unidades,
    "agrupaciones": listado_de_agrupaciones,
    "anuncios": listado_de_anuncios,
    "notificaciones": listado_de_notificaciones,
    "areas": listado_de_areas_comunes,
    "reglas": listado_de_reglas,
    "reglas-catalogo": catalogo_de_reglas,
    "solicitudes": listado_de_solicitudes,
    "visitantes": listado_de_visitantes,
    "parqueaderos": listado_de_parqueaderos,
    "parqueaderos-mios": mis_parqueaderos,
    "infracciones": listado_de_infracciones,
    "pagos-administracion": tabla_de_pagos,
    "pagos-mios": pagos_mios,
    "ingresos": listado_de_ingresos,
    "ingresos-zonas": zonas_con_ingreso,
    "documento": datos_del_reglamento,
    "documentos": lista_de_documentos,
    "documento-versiones": versiones_del_reglamento,
}
# Rutas de conjunto sin identificador ni listado: actúan sobre el conjunto activo.
ACCIONES = {
    "solicitud-decision": cerrar_solicitud_en("solicitud-decision"),
    "solicitud-descarte": cerrar_solicitud_en("solicitud-descarte"),
    "campanas": marcar_campana_en,
    "usuario-eliminar": retirar_usuario_en,
    "caso-tomar": mover_caso_en("caso-tomar"),
    "caso-prioridad": mover_caso_en("caso-prioridad"),
    "caso-redirigir": mover_caso_en("caso-redirigir"),
    "caso-descartar": mover_caso_en("caso-descartar"),
    "caso-responder": mover_caso_en("caso-responder"),
    "caso-rechazar": mover_caso_en("caso-rechazar"),
    "conjunto-activar": activar_conjunto,
    "conjunto-logo": logo_del_conjunto,
    "area-desactivar": desactivar_area_comun,
    "unidad-vinculos": registrar_vinculo_en,
    "vinculo-cerrar": cerrar_vinculo_en,
    "estructura-previsualizar": estructura_en("estructura-previsualizar"),
    "estructura-generar": estructura_en("estructura-generar"),
    "usuario-roles": asignar_rol_en,
    "usuario-rol-cambiar": cambiar_rol_en,
    "usuario-rol-retirar": retirar_rol_en,
    "persona-buscar": buscar_persona_en,
    "persona-vincular": vincular_persona_en,
    "regla-retirar": retirar_regla_en,
    "solicitud-liberar": liberar_solicitud_en,
    "solicitud-enviar": enviar_solicitud_en,
    "solicitud-pago": declarar_pago_en,
    "solicitud-pago-retirar": retirar_pago_en,
    "solicitud-comprobantes": subir_comprobante_en,
    "documento": subir_reglamento_en,
    "ingreso-residentes-buscar": buscar_residente_en,
    "ingreso-salida": salida_en,
    "parqueadero-desactivar": desactivar_parqueadero_en,
    "parqueadero-asignacion": asignar_parqueadero_en,
    "parqueadero-liberacion": liberar_parqueadero_en,
    "infraccion-cierre": cerrar_infraccion_en,
    "infraccion-anulacion": anular_infraccion_en,
    "pago-confirmacion": confirmar_pago_en,
    "pago-reportes": reportar_pago_en,
    "visitante-salida": salida_de_visitante_en,
}
RUTAS_SIN_CONJUNTO = {
    "iniciar-sesion",
    "cerrar-sesion",
    "conjuntos-disponibles",
    "conjunto-activo",
    # El perfil es de quien pregunta: no recibe ningún identificador de otro conjunto.
    "usuario-perfil",
    # El Superusuario crea conjuntos sin tener uno activo (HU-03).
    # El Superusuario crea a otro sin conjunto (HU-06).
    "superusuarios",
    "conjunto-crear",
    # El selector muestra logos de conjuntos que no son el activo; se revisa el acceso a cada uno (HU-21).
    "conjunto-logo-imagen",
    "recuperar-contrasena",
    "restablecer-contrasena",
    "dos-factores-configurar",
    "dos-factores-activar",
    "dos-factores-verificar",
    "dos-factores-restablecer",
    "dos-factores-restablecer-confirmar",
}


@pytest.mark.parametrize("ruta", sorted(DETALLES))
def test_intruso_pide_por_id_un_recurso_de_otro_conjunto_y_recibe_404(ruta, intruso, mirador):
    url = DETALLES[ruta](mirador)

    assert intruso.get(url).status_code == 404


@pytest.mark.parametrize("ruta", sorted(LISTADOS))
def test_listado_no_trae_datos_de_otro_conjunto(ruta, intruso, mirador):
    url, id_ajeno = LISTADOS[ruta](mirador)

    respuesta = intruso.get(url)

    assert respuesta.status_code == 200
    assert id_ajeno not in respuesta.content.decode()


@pytest.mark.parametrize("ruta", sorted(ACCIONES))
def test_accion_no_acepta_otro_conjunto_y_no_lo_toca(ruta, intruso, mirador):
    metodo, url, intacto = ACCIONES[ruta](mirador)

    respuesta = getattr(intruso, metodo)(url, {"conjunto": str(mirador.id)}, format="json")

    assert respuesta.status_code == 400
    assert intacto()


def test_conjunto_en_la_url_se_rechaza(intruso, mirador):
    respuesta = intruso.get(reverse("pruebas-areas"), {"conjunto_id": str(mirador.id)})

    assert respuesta.status_code == 400


def test_conjunto_en_el_cuerpo_se_rechaza(intruso, mirador):
    respuesta = intruso.post(
        reverse("pruebas-areas"), {"nombre": "Piscina", "conjunto": str(mirador.id)}, format="json"
    )

    assert respuesta.status_code == 400
    with usar_conjunto(mirador.id):
        assert not Area.objects.exists()


def test_crear_por_la_api_escribe_en_el_conjunto_activo(intruso, torres):
    respuesta = intruso.post(reverse("pruebas-areas"), {"nombre": "Salón comunal"}, format="json")

    assert respuesta.status_code == 201
    with usar_conjunto(torres.id):
        assert Area.objects.filter(nombre="Salón comunal").exists()


def test_sin_conjunto_activo_no_se_entra_a_datos_de_un_conjunto(torres, mirador):
    crear_usuario("laura@correo.com", (Rol.RESIDENTE, torres), (Rol.RESIDENTE, mirador))
    cliente = cliente_para("laura@correo.com")

    assert cliente.get(reverse("pruebas-areas")).status_code == 403


def test_al_retirar_el_rol_pierde_el_conjunto_activo_de_inmediato(intruso):
    Asignacion.objects.update(vigencia_hasta=timezone.localdate())

    assert intruso.get(reverse("pruebas-areas")).status_code == 403


def test_al_cambiar_de_conjunto_activo_solo_ve_los_datos_del_nuevo(torres, mirador):
    crear_usuario("laura@correo.com", (Rol.ADMINISTRACION, torres), (Rol.RESIDENTE, mirador))
    crear_area(torres, "Salón comunal")
    crear_area(mirador, "Piscina")
    cliente = cliente_para("laura@correo.com")

    cliente.post("/auth/conjunto-activo/", {"conjunto": str(torres.id)}, format="json")
    en_torres = [area["nombre"] for area in cliente.get(reverse("pruebas-areas")).json()]
    cliente.post("/auth/conjunto-activo/", {"conjunto": str(mirador.id)}, format="json")
    en_mirador = [area["nombre"] for area in cliente.get(reverse("pruebas-areas")).json()]

    assert en_torres == ["Salón comunal"]
    assert en_mirador == ["Piscina"]


# Prueba transversal de rutas


def rutas_de_la_api(patrones):
    for patron in patrones:
        if isinstance(patron, URLResolver):
            yield from rutas_de_la_api(patron.url_patterns)
        elif hasattr(patron.callback, "cls"):  # solo las vistas de DRF
            yield patron.name, patron.callback.cls


def rutas_sin_cubrir(rutas):
    con_prueba_del_intruso = set(DETALLES) | set(LISTADOS) | set(ACCIONES)
    faltantes = []
    for nombre, vista in rutas:
        if issubclass(vista, VistaDeConjunto):
            if nombre not in con_prueba_del_intruso:
                faltantes.append(nombre)
        elif nombre not in RUTAS_SIN_CONJUNTO:
            faltantes.append(nombre)
    return faltantes


def test_toda_ruta_de_la_api_esta_cubierta():
    assert rutas_sin_cubrir(rutas_de_la_api(get_resolver().url_patterns)) == []


def test_la_revision_detecta_una_ruta_nueva_sin_cubrir():
    class VistaNuevaDeConjunto(VistaDeConjunto):
        pass

    class VistaNuevaSinBase(APIView):
        pass

    rutas = [("ruta-nueva-de-conjunto", VistaNuevaDeConjunto), ("ruta-nueva-sin-base", VistaNuevaSinBase)]

    assert rutas_sin_cubrir(rutas) == ["ruta-nueva-de-conjunto", "ruta-nueva-sin-base"]
