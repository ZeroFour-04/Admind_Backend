"""Pruebas de HU-06: asignar y retirar roles del catálogo en el conjunto activo.

Dos criterios ya tienen prueba en `apps/permisos/tests.py`: un rol del conjunto A no da permisos
en B (`test_rol_de_un_conjunto_no_da_permisos_en_otro`); el Superusuario, en cambio, tiene todos
los permisos del catálogo en cualquier conjunto.
"""
import threading

import pytest
from django.db import connection
from django.urls import URLResolver, get_resolver
from rest_framework.test import APIClient

from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos import servicios
from apps.permisos.catalogo import PERMISOS_POR_ROL, Rol
from apps.permisos.models import Asignacion
from apps.permisos.servicios import permisos_efectivos
from apps.personas.models import Persona, TipoDocumento

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"


def crear_usuario(correo, rol, conjunto, nombres="Laura"):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres=nombres,
        apellidos="Gómez",
    )
    Asignacion.objects.create(persona=persona, rol=rol, conjunto=conjunto)
    return Usuario.objects.create_user(correo, CONTRASENA, persona)


def cliente_para(correo):
    """Sesión con el segundo factor dado por verificado: su flujo se prueba en cuentas."""
    cliente = APIClient()
    respuesta = cliente.post("/auth/login/", {"correo": correo, "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {respuesta.json()['token']}")
    TokenDeSesion.objects.filter(usuario__correo=correo).update(dos_factores_verificado=True)
    return cliente


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río")


@pytest.fixture
def admin_usuario(torres):
    return crear_usuario("admin@torres.com", Rol.ADMINISTRACION, torres, "Andrés")


@pytest.fixture
def admin(admin_usuario):
    return cliente_para("admin@torres.com")


@pytest.fixture
def vecino(torres):
    return crear_usuario("vecino@torres.com", Rol.RESIDENTE, torres, "Pedro")


def asignar(cliente, usuario, rol):
    return cliente.post(f"/auth/usuarios/{usuario.id}/roles/", {"rol": rol}, format="json")


def retirar(cliente, usuario, asignacion):
    return cliente.post(f"/auth/usuarios/{usuario.id}/roles/{asignacion.id}/retirar/")


def asignacion_de(usuario, rol):
    return Asignacion.objects.get(persona=usuario.persona, rol=rol, vigencia_hasta__isnull=True)


# Criterios de aceptación


def test_asignar_un_rol_suma_los_permisos_de_todos_sus_roles(admin, vecino, torres):
    respuesta = asignar(admin, vecino, "consejo")

    assert respuesta.status_code == 200
    assert sorted(a["rol"] for a in respuesta.json()["asignaciones"]) == ["consejo", "residente"]
    esperados = PERMISOS_POR_ROL[Rol.RESIDENTE] | PERMISOS_POR_ROL[Rol.CONSEJO]
    assert permisos_efectivos(vecino.persona, torres.id) == esperados


def nombres_de_rutas(patrones):
    for patron in patrones:
        if isinstance(patron, URLResolver):
            yield from nombres_de_rutas(patron.url_patterns)
        elif patron.name:
            yield patron.name


def test_no_existe_crear_ni_editar_roles(admin, vecino):
    de_roles = {nombre for nombre in nombres_de_rutas(get_resolver().url_patterns) if {"rol", "roles"} & set(nombre.split("-"))}

    # Solo asignar un rol del catálogo a un usuario y retirarlo; ninguna ruta crea ni edita roles.
    assert de_roles == {"usuario-roles", "usuario-rol-retirar"}
    assert asignar(admin, vecino, "operador").status_code == 400
    assert asignar(admin, vecino, "superusuario").status_code == 400
    assert not Asignacion.objects.filter(persona=vecino.persona, rol__in=["operador", "superusuario"]).exists()


def test_retirar_el_rol_al_ultimo_de_administracion_falla(admin, admin_usuario):
    unica = asignacion_de(admin_usuario, Rol.ADMINISTRACION)

    respuesta = retirar(admin, admin_usuario, unica)

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "El conjunto no puede quedar sin Administración."
    unica.refresh_from_db()
    assert unica.vigencia_hasta is None


def test_con_dos_administradores_se_retira_uno(admin, admin_usuario, torres):
    otra = crear_usuario("admin2@torres.com", Rol.ADMINISTRACION, torres, "Sofía")

    respuesta = retirar(admin, otra, asignacion_de(otra, Rol.ADMINISTRACION))

    assert respuesta.status_code == 200
    assert respuesta.json()["asignaciones"] == []
    assert retirar(admin, admin_usuario, asignacion_de(admin_usuario, Rol.ADMINISTRACION)).status_code == 409


def test_asignar_y_retirar_quedan_en_la_auditoria(admin, admin_usuario, vecino, torres):
    asignar(admin, vecino, "consejo")
    retirar(admin, vecino, asignacion_de(vecino, Rol.CONSEJO))

    with usar_conjunto(torres.id):
        registros = list(Registro.objects.order_by("creado_en"))
    assert [(r.accion, r.actor_id) for r in registros] == [
        ("rol.asignar", admin_usuario.persona_id),
        ("rol.retirar", admin_usuario.persona_id),
    ]
    assert registros[0].despues["rol"] == "consejo"
    assert registros[1].antes["vigencia_hasta"] is None
    assert registros[1].despues["vigencia_hasta"] is not None


# Reglas de la asignación


def test_retirar_quita_los_permisos_de_inmediato(admin, vecino, torres):
    asignar(admin, vecino, "consejo")

    retirar(admin, vecino, asignacion_de(vecino, Rol.CONSEJO))

    assert permisos_efectivos(vecino.persona, torres.id) == PERMISOS_POR_ROL[Rol.RESIDENTE]


def test_asignar_un_rol_ya_vigente_responde_409(admin, vecino):
    respuesta = asignar(admin, vecino, "residente")

    assert respuesta.status_code == 409
    assert Asignacion.objects.filter(persona=vecino.persona).count() == 1


def test_sin_rol_asignar_no_se_asigna_ni_se_retira(torres, vecino, admin_usuario):
    residente = cliente_para("vecino@torres.com")

    assert asignar(residente, vecino, "consejo").status_code == 403
    assert retirar(residente, admin_usuario, asignacion_de(admin_usuario, Rol.ADMINISTRACION)).status_code == 403


def test_una_asignacion_de_otra_persona_no_se_retira_por_este_usuario(admin, admin_usuario, vecino):
    respuesta = retirar(admin, vecino, asignacion_de(admin_usuario, Rol.ADMINISTRACION))

    assert respuesta.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_dos_retiros_a_la_vez_no_dejan_el_conjunto_sin_administracion():
    torres = Conjunto.objects.create(nombre="Torres del Río")
    uno = crear_usuario("a1@torres.com", Rol.ADMINISTRACION, torres, "Uno")
    dos = crear_usuario("a2@torres.com", Rol.ADMINISTRACION, torres, "Dos")
    asignaciones = [asignacion_de(uno, Rol.ADMINISTRACION), asignacion_de(dos, Rol.ADMINISTRACION)]
    barrera = threading.Barrier(2)
    resultados = []

    def retirar_en_paralelo(asignacion, actor):
        try:
            with usar_conjunto(torres.id):
                barrera.wait()
                try:
                    servicios.retirar_rol(actor, asignacion, torres.id)
                    resultados.append("retirado")
                except servicios.UltimaAdministracion:
                    resultados.append("ultima")
        finally:
            connection.close()

    hilos = [
        threading.Thread(target=retirar_en_paralelo, args=(asignaciones[0], dos.persona)),
        threading.Thread(target=retirar_en_paralelo, args=(asignaciones[1], uno.persona)),
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(resultados) == ["retirado", "ultima"]
    assert Asignacion.objects.vigentes().filter(conjunto=torres, rol=Rol.ADMINISTRACION).count() == 1
