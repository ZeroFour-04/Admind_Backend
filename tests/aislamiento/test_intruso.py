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
from apps.areas.models import Area as AreaComun
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.documentos.models import Reglamento
from apps.ingresos.models import Ingreso
from apps.notificaciones.models import Notificacion
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.reglas.models import Regla
from apps.reservas.models import Solicitud
from apps.unidades.models import Agrupacion, TipoVinculo, Unidad, VinculoUnidad
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
        return Reglamento.objects.create(
            contenido=b"%PDF-1.7 ajeno", nombre="ajeno.pdf", peso=14, huella="b" * 64, subido_por=persona
        )


def datos_del_reglamento(otro_conjunto):
    return reverse("reglamento"), reglamento_de(otro_conjunto).huella


def subir_reglamento_en(otro_conjunto):
    reglamento_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return Reglamento.objects.count() == 1

    return "put", reverse("reglamento"), intacto


def archivo_del_reglamento(otro_conjunto):
    reglamento_de(otro_conjunto)
    return reverse("reglamento-archivo")


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


def desactivar_area_comun(otro_conjunto):
    area = area_comun_de(otro_conjunto)

    def intacto():
        with usar_conjunto(otro_conjunto.id):
            return AreaComun.objects.get(pk=area.pk).activo

    return "post", reverse("area-desactivar", kwargs={"area_id": area.pk}), intacto


DETALLES = {
    "pruebas-area-detalle": detalle_de_area,
    "usuario-detalle": detalle_de_usuario,
    "anuncio-detalle": detalle_de_anuncio,
    "anuncio-foto": foto_de_anuncio,
    "area-detalle": detalle_de_area_comun,
    "unidad-detalle": detalle_de_unidad,
    "regla-detalle": detalle_de_regla,
    "franjas": franjas_de_area_ajena,
    "solicitud-detalle": detalle_de_solicitud,
    "reglamento-archivo": archivo_del_reglamento,
}
LISTADOS = {
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
    "ingresos": listado_de_ingresos,
    "ingresos-zonas": zonas_con_ingreso,
    "reglamento": datos_del_reglamento,
}
# Rutas de conjunto sin identificador ni listado: actúan sobre el conjunto activo.
ACCIONES = {
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
    "reglamento": subir_reglamento_en,
    "ingreso-residentes-buscar": buscar_residente_en,
    "ingreso-salida": salida_en,
}
RUTAS_SIN_CONJUNTO = {
    "iniciar-sesion",
    "cerrar-sesion",
    "conjuntos-disponibles",
    "conjunto-activo",
    # El Superusuario crea conjuntos sin tener uno activo (HU-03).
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
