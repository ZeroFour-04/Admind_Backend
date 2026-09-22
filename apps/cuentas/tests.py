"""Pruebas de HU-01 (inicio y cierre de sesión con token) y HU-26 (selector de conjunto activo)."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos.catalogo import PERMISOS_DE_PLATAFORMA, PERMISOS_POR_ROL, Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"


@pytest.fixture
def cliente():
    return APIClient()


@pytest.fixture
def usuario():
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento="1023456789",
        nombres="Laura",
        apellidos="Gómez",
    )
    return Usuario.objects.create_user("laura@correo.com", CONTRASENA, persona)


def iniciar_sesion(cliente, correo, contrasena):
    return cliente.post("/auth/login/", {"correo": correo, "contrasena": contrasena}, format="json")


def cerrar_sesion(cliente, token=None):
    if token:
        cliente.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    return cliente.post("/auth/logout/")


# Inicio de sesión


def test_credenciales_validas_entregan_un_token(cliente, usuario):
    respuesta = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA)

    assert respuesta.status_code == 200
    assert respuesta.json()["token"]
    assert TokenDeSesion.objects.filter(usuario=usuario).count() == 1


def test_correo_se_acepta_con_mayusculas_y_espacios(cliente, usuario):
    respuesta = iniciar_sesion(cliente, "  Laura@Correo.com ", CONTRASENA)

    assert respuesta.status_code == 200


def test_la_base_guarda_la_huella_y_no_el_token(cliente, usuario):
    token = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA).json()["token"]

    assert not TokenDeSesion.objects.filter(huella=token).exists()


def test_errores_de_ingreso_no_revelan_si_el_correo_existe(cliente, usuario):
    contrasena_mala = iniciar_sesion(cliente, "laura@correo.com", "otra-clave")
    correo_inexistente = iniciar_sesion(cliente, "nadie@correo.com", CONTRASENA)

    assert contrasena_mala.status_code == correo_inexistente.status_code == 401
    assert contrasena_mala.json() == correo_inexistente.json()


def test_usuario_desactivado_no_puede_entrar(cliente, usuario):
    usuario.is_active = False
    usuario.save()

    respuesta = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA)

    assert respuesta.status_code == 401
    assert not TokenDeSesion.objects.exists()


def test_persona_desactivada_no_puede_entrar(cliente, usuario):
    Persona.objects.filter(pk=usuario.persona_id).update(activo=False)

    respuesta = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA)

    assert respuesta.status_code == 401


# Uso del token


def test_sin_token_la_api_responde_401(cliente, usuario):
    assert cerrar_sesion(cliente).status_code == 401


def test_token_inventado_responde_401(cliente, usuario):
    assert cerrar_sesion(cliente, "no-es-un-token").status_code == 401


def test_token_vencido_exige_iniciar_sesion_de_nuevo(cliente, usuario):
    token = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA).json()["token"]
    TokenDeSesion.objects.update(vence_en=timezone.now() - timedelta(minutes=1))

    assert cerrar_sesion(cliente, token).status_code == 401


def test_desactivar_al_usuario_invalida_su_token_de_inmediato(cliente, usuario):
    token = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA).json()["token"]
    usuario.is_active = False
    usuario.save()

    assert cerrar_sesion(cliente, token).status_code == 401


# Cierre de sesión


def test_cerrar_sesion_invalida_el_token_de_inmediato(cliente, usuario):
    token = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA).json()["token"]

    assert cerrar_sesion(cliente, token).status_code == 204
    assert cerrar_sesion(cliente, token).status_code == 401
    assert not TokenDeSesion.objects.exists()


# Selector de conjunto activo (HU-26)


def asignar(usuario, rol, conjunto=None):
    return Asignacion.objects.create(persona=usuario.persona, rol=rol, conjunto=conjunto)


def entrar(cliente, segundo_factor=True):
    """Inicia sesión como Laura. Por defecto da el segundo factor por verificado: su flujo real
    se prueba aparte, en test_dos_factores.py."""
    respuesta = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA)
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {respuesta.json()['token']}")
    if segundo_factor:
        TokenDeSesion.objects.filter(usuario__correo="laura@correo.com").update(dos_factores_verificado=True)
    return respuesta.json()


def elegir(cliente, conjunto_id):
    return cliente.post("/auth/conjunto-activo/", {"conjunto": str(conjunto_id)}, format="json")


def test_con_varios_conjuntos_entra_sin_conjunto_activo_y_los_ve_todos(cliente, usuario):
    for nombre in ["Torres del Río", "Mirador", "Balcones"]:
        asignar(usuario, Rol.RESIDENTE, Conjunto.objects.create(nombre=nombre))

    sesion = entrar(cliente)
    disponibles = cliente.get("/auth/conjuntos/").json()

    assert sesion["conjunto_activo"] is None
    assert [conjunto["nombre"] for conjunto in disponibles] == ["Balcones", "Mirador", "Torres del Río"]


def test_con_un_solo_conjunto_entra_directo(cliente, usuario):
    torres = Conjunto.objects.create(nombre="Torres del Río")
    asignar(usuario, Rol.ADMINISTRACION, torres)

    sesion = entrar(cliente)

    assert sesion["conjunto_activo"] == {"id": str(torres.id), "nombre": "Torres del Río", "acento": "verde"}
    assert set(sesion["permisos"]) == PERMISOS_POR_ROL[Rol.ADMINISTRACION]


def test_al_crear_usuario_se_asigna_el_rol_en_el_conjunto_activo(cliente, usuario):
    from apps.permisos.models import Asignacion

    activo = Conjunto.objects.create(nombre="Torres del Río")
    asignar(usuario, Rol.ADMINISTRACION, activo)
    entrar(cliente)

    respuesta = cliente.post(
        "/auth/usuarios/",
        {
            "tipo_documento": TipoDocumento.CC,
            "numero_documento": "1098765432",
            "nombres": "Carlos",
            "apellidos": "Pérez",
            "correo": "carlos@correo.com",
            "contrasena": CONTRASENA,
            "rol": Rol.RESIDENTE,
        },
        format="json",
    )

    assert respuesta.status_code == 201
    nuevo_usuario = Usuario.objects.get(correo="carlos@correo.com")
    asignacion = Asignacion.objects.get(persona=nuevo_usuario.persona)
    assert asignacion.rol == Rol.RESIDENTE
    assert asignacion.conjunto_id == activo.id


def test_conjunto_desactivado_o_sin_asignacion_vigente_no_aparece(cliente, usuario):
    asignar(usuario, Rol.RESIDENTE, Conjunto.objects.create(nombre="Torres del Río"))
    asignar(usuario, Rol.RESIDENTE, Conjunto.objects.create(nombre="Desactivado", activo=False))
    cerrada = asignar(usuario, Rol.RESIDENTE, Conjunto.objects.create(nombre="Rol retirado"))
    cerrada.vigencia_hasta = timezone.localdate()
    cerrada.save()

    entrar(cliente)
    disponibles = cliente.get("/auth/conjuntos/").json()

    assert [conjunto["nombre"] for conjunto in disponibles] == ["Torres del Río"]


def test_elegir_un_conjunto_sin_asignacion_responde_404(cliente, usuario):
    asignar(usuario, Rol.RESIDENTE, Conjunto.objects.create(nombre="Torres del Río"))
    ajeno = Conjunto.objects.create(nombre="Mirador")
    entrar(cliente)

    assert elegir(cliente, ajeno.id).status_code == 404


def test_al_cambiar_de_conjunto_los_permisos_son_solo_los_del_nuevo(cliente, usuario):
    torres = Conjunto.objects.create(nombre="Torres del Río")
    mirador = Conjunto.objects.create(nombre="Mirador")
    asignar(usuario, Rol.ADMINISTRACION, torres)
    asignar(usuario, Rol.RESIDENTE, mirador)
    entrar(cliente)

    en_torres = elegir(cliente, torres.id).json()
    en_mirador = elegir(cliente, mirador.id).json()

    assert "reserva.aprobar" in en_torres["permisos"]
    assert set(en_mirador["permisos"]) == PERMISOS_POR_ROL[Rol.RESIDENTE]
    assert TokenDeSesion.objects.get().conjunto_activo_id == mirador.id


def test_superusuario_entra_sin_conjunto_con_permisos_de_plataforma(cliente, usuario):
    asignar(usuario, Rol.SUPERUSUARIO)

    sesion = entrar(cliente)

    assert sesion["conjunto_activo"] is None
    assert set(sesion["permisos"]) == PERMISOS_DE_PLATAFORMA


def test_superusuario_puede_crear_usuario_en_el_conjunto_activo(cliente, usuario):
    activo = Conjunto.objects.create(nombre="Torres del Río")
    asignar(usuario, Rol.SUPERUSUARIO)
    entrar(cliente)
    elegir(cliente, activo.id)

    respuesta = cliente.post(
        "/auth/usuarios/",
        {
            "tipo_documento": TipoDocumento.CC,
            "numero_documento": "1098765432",
            "nombres": "Carlos",
            "apellidos": "Pérez",
            "correo": "carlos@correo.com",
            "contrasena": CONTRASENA,
            "rol": Rol.RESIDENTE,
        },
        format="json",
    )

    assert respuesta.status_code == 201


# Usuarios del conjunto activo (HU-04, HU-05)


def datos_de_usuario(**cambios):
    datos = {
        "tipo_documento": TipoDocumento.CC,
        "numero_documento": "1098765432",
        "nombres": "Carlos",
        "apellidos": "Pérez",
        "correo": "carlos@correo.com",
        "contrasena": CONTRASENA,
        "rol": Rol.RESIDENTE,
    }
    return {**datos, **cambios}


def test_crear_usuario_con_un_documento_que_ya_existe_responde_400_y_no_duplica(cliente, usuario):
    activo = Conjunto.objects.create(nombre="Torres del Río")
    asignar(usuario, Rol.ADMINISTRACION, activo)
    entrar(cliente)

    # 1.023.456.789 es el documento de Laura escrito con puntos.
    respuesta = cliente.post("/auth/usuarios/", datos_de_usuario(numero_documento="1.023.456.789"), format="json")

    assert respuesta.status_code == 400
    assert "numero_documento" in respuesta.json()
    assert Persona.objects.count() == 1


def test_crear_usuario_sin_conjunto_activo_responde_403(cliente, usuario):
    asignar(usuario, Rol.SUPERUSUARIO)
    entrar(cliente)

    respuesta = cliente.post("/auth/usuarios/", datos_de_usuario(), format="json")

    assert respuesta.status_code == 403
    assert not Usuario.objects.filter(correo="carlos@correo.com").exists()


def test_la_lista_de_usuarios_solo_trae_los_del_conjunto_activo_con_sus_roles_ahi(cliente, usuario):
    torres = Conjunto.objects.create(nombre="Torres del Río")
    mirador = Conjunto.objects.create(nombre="Mirador")
    asignar(usuario, Rol.ADMINISTRACION, torres)
    asignar(usuario, Rol.RESIDENTE, mirador)
    entrar(cliente)
    elegir(cliente, mirador.id)
    Usuario.objects.create_user(
        "vecino@correo.com",
        CONTRASENA,
        Persona.objects.create(tipo_documento=TipoDocumento.CC, numero_documento="55555", nombres="Ana", apellidos="Ruiz"),
    )
    Asignacion.objects.create(persona=Usuario.objects.get(correo="vecino@correo.com").persona, rol=Rol.RESIDENTE, conjunto=mirador)
    elegir(cliente, torres.id)

    respuesta = cliente.get("/auth/usuarios/")

    assert respuesta.status_code == 200
    assert [u["correo"] for u in respuesta.json()] == ["laura@correo.com"]
    assert respuesta.json()[0]["roles"] == ["Administración"]


def test_residente_no_puede_gestionar_usuarios(cliente, usuario):
    asignar(usuario, Rol.RESIDENTE, Conjunto.objects.create(nombre="Torres del Río"))
    entrar(cliente)

    assert cliente.get("/auth/usuarios/").status_code == 403
    assert cliente.post("/auth/usuarios/", datos_de_usuario(), format="json").status_code == 403


# Recuperación de contraseña (HU-01)


def pedir_enlace(cliente, correo="laura@correo.com"):
    return cliente.post("/auth/recuperar/", {"correo": correo}, format="json")


def enlace_del_correo(bandeja):
    enlace = next(linea for linea in bandeja[-1].body.splitlines() if "/restablecer-contrasena/" in linea)
    uid, token = enlace.rstrip("/").split("/")[-2:]
    return uid, token


def restablecer(cliente, uid, token, contrasena="otra-clave-larga-2026"):
    return cliente.post(
        "/auth/recuperar/confirmar/", {"uid": uid, "token": token, "contrasena": contrasena}, format="json"
    )


def test_quien_olvido_la_contrasena_recibe_un_enlace_por_correo(cliente, usuario, mailoutbox):
    respuesta = pedir_enlace(cliente)

    assert respuesta.status_code == 202
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["laura@correo.com"]
    assert "/restablecer-contrasena/" in mailoutbox[0].body


def test_pedir_enlace_no_revela_si_el_correo_existe(cliente, usuario, mailoutbox):
    existe = pedir_enlace(cliente)
    no_existe = pedir_enlace(cliente, "nadie@correo.com")

    assert existe.status_code == no_existe.status_code == 202
    assert existe.json() == no_existe.json()
    assert len(mailoutbox) == 1


def test_cuenta_desactivada_no_recibe_enlace(cliente, usuario, mailoutbox):
    usuario.is_active = False
    usuario.save()

    assert pedir_enlace(cliente).status_code == 202
    assert mailoutbox == []


def test_con_el_enlace_cambia_la_contrasena_y_cierra_las_sesiones_abiertas(cliente, usuario, mailoutbox):
    entrar(cliente)
    pedir_enlace(cliente)
    uid, token = enlace_del_correo(mailoutbox)

    respuesta = restablecer(APIClient(), uid, token)

    assert respuesta.status_code == 204
    assert not TokenDeSesion.objects.exists()
    assert iniciar_sesion(APIClient(), "laura@correo.com", "otra-clave-larga-2026").status_code == 200
    assert iniciar_sesion(APIClient(), "laura@correo.com", CONTRASENA).status_code == 401


def test_el_enlace_sirve_una_sola_vez(cliente, usuario, mailoutbox):
    pedir_enlace(cliente)
    uid, token = enlace_del_correo(mailoutbox)
    restablecer(cliente, uid, token)

    otra_vez = restablecer(cliente, uid, token, "una-tercera-clave-2026")

    assert otra_vez.status_code == 400
    assert iniciar_sesion(APIClient(), "laura@correo.com", "otra-clave-larga-2026").status_code == 200


def test_el_enlace_vencido_no_sirve(cliente, usuario, mailoutbox, settings):
    pedir_enlace(cliente)
    uid, token = enlace_del_correo(mailoutbox)
    settings.PASSWORD_RESET_TIMEOUT = -1

    assert restablecer(cliente, uid, token).status_code == 400


def test_enlace_inventado_no_sirve(cliente, usuario):
    assert restablecer(cliente, "no-es-un-uid", "no-es-un-token").status_code == 400


def test_la_contrasena_nueva_debe_cumplir_las_reglas(cliente, usuario, mailoutbox):
    pedir_enlace(cliente)
    uid, token = enlace_del_correo(mailoutbox)

    respuesta = restablecer(cliente, uid, token, "123")

    assert respuesta.status_code == 400
    assert "contrasena" in respuesta.json()
    # El enlace sigue sirviendo: la contraseña no cambió.
    assert restablecer(cliente, uid, token).status_code == 204
