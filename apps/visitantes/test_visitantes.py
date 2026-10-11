"""Pruebas de registro y consulta de visitantes."""

import pytest
from datetime import datetime, timedelta
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.parqueaderos.models import Parqueadero
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.unidades.models import Unidad
from apps.visitantes import servicios
from apps.visitantes.models import Visitante

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"


def crear_usuario(correo, conjunto, rol):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=f"1{Persona.objects.count() + 1023456789}",
        nombres="Camila",
        apellidos="Ríos",
    )
    Asignacion.objects.create(persona=persona, rol=rol, conjunto=conjunto)
    Usuario.objects.create_user(correo, CONTRASENA, persona)


def cliente_para(correo):
    cliente = APIClient()
    respuesta = cliente.post("/auth/login/", {"correo": correo, "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {respuesta.json()['token']}")
    TokenDeSesion.objects.filter(usuario__correo=correo).update(dos_factores_verificado=True)
    return cliente


@pytest.fixture
def datos():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    with usar_conjunto(conjunto.id):
        unidad = Unidad.objects.create(nombre="Torre 1 – 101")
    return conjunto, unidad


def test_vigilancia_registra_y_consulta_visitantes_del_conjunto(datos):
    conjunto, unidad = datos
    crear_usuario("vigilancia@torres.com", conjunto, Rol.VIGILANCIA)
    vigilancia = cliente_para("vigilancia@torres.com")

    respuesta = vigilancia.post(
        "/visitantes/",
        {
            "nombre": "María Pérez",
            "cedula": "123456789",
            "ingresa_con_vehiculo": True,
            "placa_vehiculo": "ABC123",
            "tipo_vehiculo": "Auto",
            "apartamento_visitado": str(unidad.id),
        },
        format="json",
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["apartamento_visitado"] == unidad.nombre
    hora_entrada = datetime.fromisoformat(respuesta.json()["hora_entrada"])
    assert hora_entrada.utcoffset() == timedelta(hours=-5)
    with usar_conjunto(conjunto.id):
        assert Visitante.objects.filter(cedula="123456789").exists()
    listado = vigilancia.get("/visitantes/")
    assert listado.status_code == 200
    assert listado.json()[0]["nombre"] == "María Pérez"
    assert listado.json()[0]["placa_vehiculo"] == "ABC123"
    assert listado.json()[0]["tipo_vehiculo"] == "Auto"


def test_vigilancia_registra_visitante_sin_vehiculo(datos):
    conjunto, unidad = datos
    crear_usuario("vigilancia@torres.com", conjunto, Rol.VIGILANCIA)
    vigilancia = cliente_para("vigilancia@torres.com")

    respuesta = vigilancia.post(
        "/visitantes/",
        {
            "nombre": "María Pérez",
            "cedula": "123456789",
            "ingresa_con_vehiculo": False,
            "apartamento_visitado": str(unidad.id),
        },
        format="json",
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["placa_vehiculo"] == ""
    assert respuesta.json()["tipo_vehiculo"] == ""


def test_vigilancia_no_puede_registrar_vehiculo_sin_placa_y_tipo(datos):
    conjunto, unidad = datos
    crear_usuario("vigilancia@torres.com", conjunto, Rol.VIGILANCIA)
    vigilancia = cliente_para("vigilancia@torres.com")

    respuesta = vigilancia.post(
        "/visitantes/",
        {
            "nombre": "María Pérez",
            "cedula": "123456789",
            "ingresa_con_vehiculo": True,
            "apartamento_visitado": str(unidad.id),
        },
        format="json",
    )

    assert respuesta.status_code == 400
    assert "placa_vehiculo" in respuesta.json()
    assert "tipo_vehiculo" in respuesta.json()


def test_vigilancia_puede_consultar_unidades_para_el_formulario(datos):
    conjunto, unidad = datos
    crear_usuario("vigilancia@torres.com", conjunto, Rol.VIGILANCIA)
    vigilancia = cliente_para("vigilancia@torres.com")

    respuesta = vigilancia.get("/unidades/")

    assert respuesta.status_code == 200
    assert respuesta.json()[0]["nombre"] == unidad.nombre


def test_no_se_puede_registrar_una_visita_a_unidad_de_otro_conjunto(datos):
    conjunto, _ = datos
    otro_conjunto = Conjunto.objects.create(nombre="Mirador")
    with usar_conjunto(otro_conjunto.id):
        unidad_ajena = Unidad.objects.create(nombre="Torre 2 – 202")
    crear_usuario("vigilancia@torres.com", conjunto, Rol.VIGILANCIA)
    vigilancia = cliente_para("vigilancia@torres.com")

    respuesta = vigilancia.post(
        "/visitantes/",
        {
            "nombre": "María Pérez",
            "cedula": "123456789",
            "apartamento_visitado": str(unidad_ajena.id),
        },
        format="json",
    )

    assert respuesta.status_code == 404
    with usar_conjunto(conjunto.id):
        assert Visitante.objects.count() == 0


def test_personas_sin_permiso_no_pueden_consultar_visitantes(datos):
    conjunto, _ = datos
    crear_usuario("residente@torres.com", conjunto, Rol.RESIDENTE)
    residente = cliente_para("residente@torres.com")

    respuesta = residente.get("/visitantes/")

    assert respuesta.status_code == 403


# La salida, la capa de servicio y la auditoría (HU-27, plan de parqueadero de visitantes F2)


@pytest.fixture
def vigilancia(datos):
    conjunto, _ = datos
    crear_usuario("vigilancia@torres.com", conjunto, Rol.VIGILANCIA)
    return cliente_para("vigilancia@torres.com")


@pytest.fixture
def administracion(datos):
    conjunto, _ = datos
    crear_usuario("admin@torres.com", conjunto, Rol.ADMINISTRACION)
    return cliente_para("admin@torres.com")


def visita(cliente, unidad, parqueadero=None, con_vehiculo=True, placa="ABC123", tipo="Auto"):
    datos = {
        "nombre": "María Pérez",
        "cedula": "123456789",
        "ingresa_con_vehiculo": con_vehiculo,
        "apartamento_visitado": str(unidad.id),
    }
    if con_vehiculo:
        datos.update(placa_vehiculo=placa, tipo_vehiculo=tipo)
    if parqueadero is not None:
        datos["parqueadero"] = str(parqueadero)
    return cliente.post("/visitantes/", datos, format="json")


def salida(cliente, visitante_id):
    return cliente.post(f"/visitantes/{visitante_id}/salida/")


def persona_de(correo):
    return Usuario.objects.get(correo=correo).persona


def test_la_salida_guarda_la_hora_y_quien_la_registro(datos, vigilancia):
    conjunto, unidad = datos
    visitante = visita(vigilancia, unidad).json()
    assert visitante["hora_salida"] is None
    antes = timezone.now()

    respuesta = salida(vigilancia, visitante["id"])

    assert respuesta.status_code == 200
    assert datetime.fromisoformat(respuesta.json()["hora_salida"]) >= antes
    with usar_conjunto(conjunto.id):
        guardada = Visitante.objects.get(pk=visitante["id"])
    assert guardada.salida_registrada_por == persona_de("vigilancia@torres.com")
    assert guardada.hora_salida >= guardada.hora_entrada


def test_registrar_la_salida_dos_veces_responde_409(datos, vigilancia):
    _, unidad = datos
    visitante = visita(vigilancia, unidad).json()
    assert salida(vigilancia, visitante["id"]).status_code == 200

    repetida = salida(vigilancia, visitante["id"])

    assert repetida.status_code == 409
    assert repetida.json() == {"detail": "Este visitante ya salió."}


def test_la_salida_de_una_visita_sin_vehiculo_tambien_se_registra(datos, vigilancia):
    _, unidad = datos
    visitante = visita(vigilancia, unidad, con_vehiculo=False).json()

    assert salida(vigilancia, visitante["id"]).status_code == 200


def test_un_administrador_con_historico_no_registra_visitas_ni_salidas(datos, vigilancia, administracion):
    conjunto, unidad = datos
    visitante = visita(vigilancia, unidad).json()

    registro = visita(administracion, unidad)
    registro_de_salida = salida(administracion, visitante["id"])
    historial = administracion.get("/visitantes/")

    assert registro.status_code == 403
    assert registro_de_salida.status_code == 403
    assert historial.status_code == 200
    with usar_conjunto(conjunto.id):
        assert Visitante.objects.get(pk=visitante["id"]).hora_salida is None
        assert Visitante.objects.count() == 1


def test_solo_vigilancia_lo_exige_el_servicio_y_no_solo_la_vista(datos):
    """La regla está en `servicios`: cualquier entrada que llegue ahí la cumple."""
    conjunto, unidad = datos
    crear_usuario("admin@torres.com", conjunto, Rol.ADMINISTRACION)
    administrador = persona_de("admin@torres.com")
    with usar_conjunto(conjunto.id):
        with pytest.raises(servicios.SoloVigilancia):
            servicios.registrar_ingreso(
                administrador,
                conjunto.id,
                nombre="María",
                cedula="1",
                placa_vehiculo="",
                tipo_vehiculo="",
                unidad_id=unidad.id,
            )
        assert Visitante.objects.count() == 0


def test_el_registro_y_la_salida_quedan_en_la_auditoria_con_su_actor(datos, vigilancia):
    conjunto, unidad = datos
    visitante = visita(vigilancia, unidad).json()
    salida(vigilancia, visitante["id"])
    vigilante = persona_de("vigilancia@torres.com")

    with usar_conjunto(conjunto.id):
        entrada = Registro.objects.get(accion="visitante.registrar", entidad_id=visitante["id"])
        retiro = Registro.objects.get(accion="visitante.salida", entidad_id=visitante["id"])

    assert entrada.actor == vigilante and retiro.actor == vigilante
    assert entrada.despues == {"unidad": str(unidad.id), "con_vehiculo": True, "parqueadero": None}
    assert retiro.antes == {"hora_salida": None}
    # La auditoría no guarda a quién visitó con su nombre ni su cédula.
    assert "María" not in str(entrada.despues) and "123456789" not in str(entrada.despues)


def test_una_visita_de_ayer_sin_salida_sigue_en_el_listado_del_vigilante(datos, vigilancia):
    conjunto, unidad = datos
    sigue_adentro = visita(vigilancia, unidad, placa="AAA111").json()
    ya_salio = visita(vigilancia, unidad, placa="BBB222").json()
    de_hoy = visita(vigilancia, unidad, placa="CCC333").json()
    assert salida(vigilancia, ya_salio["id"]).status_code == 200
    ayer = timezone.now() - timedelta(days=1)
    with usar_conjunto(conjunto.id):
        Visitante.objects.filter(pk__in=[sigue_adentro["id"], ya_salio["id"]]).update(hora_entrada=ayer)
        Visitante.objects.filter(pk=ya_salio["id"]).update(hora_salida=ayer + timedelta(hours=1))

    placas = [v["placa_vehiculo"] for v in vigilancia.get("/visitantes/").json()]

    assert sorted(placas) == ["AAA111", "CCC333"]
    assert de_hoy["placa_vehiculo"] == "CCC333"


def test_con_historico_se_ve_todo_y_el_listado_trae_salida_y_parqueadero(datos, vigilancia, administracion):
    conjunto, unidad = datos
    primero = visita(vigilancia, unidad, placa="AAA111").json()
    visita(vigilancia, unidad, placa="BBB222")
    salida(vigilancia, primero["id"])

    lista = administracion.get("/visitantes/").json()

    assert len(lista) == 2
    por_placa = {v["placa_vehiculo"]: v for v in lista}
    assert por_placa["AAA111"]["hora_salida"] is not None
    assert por_placa["BBB222"]["hora_salida"] is None
    assert por_placa["BBB222"]["parqueadero"] is None


def test_la_base_rechaza_una_salida_anterior_a_la_entrada(datos, vigilancia):
    conjunto, unidad = datos
    visitante = visita(vigilancia, unidad).json()

    with usar_conjunto(conjunto.id), pytest.raises(IntegrityError), transaction.atomic():
        Visitante.objects.filter(pk=visitante["id"]).update(hora_salida=timezone.now() - timedelta(days=1))


# Ocupar un parqueadero de visitantes (HU-28, F3): los cinco criterios


def puesto(administracion, codigo, tipo="visitantes"):
    respuesta = administracion.post("/parqueaderos/", {"codigo": codigo, "tipo": tipo}, format="json")
    assert respuesta.status_code == 201
    return respuesta.json()["id"]


def libres(cliente):
    return [p["codigo"] for p in cliente.get("/parqueaderos/", {"tipo": "visitantes", "libres": "1"}).json()]


def test_con_un_puesto_libre_la_visita_lo_ocupa_y_ya_no_aparece_como_libre(datos, vigilancia, administracion):
    _, unidad = datos
    v01 = puesto(administracion, "V-01")
    puesto(administracion, "V-02")
    assert libres(vigilancia) == ["V-01", "V-02"]

    respuesta = visita(vigilancia, unidad, parqueadero=v01)

    assert respuesta.status_code == 201
    assert respuesta.json()["parqueadero"] == "V-01"
    assert libres(vigilancia) == ["V-02"]
    ocupado = {p["codigo"]: p["ocupado"] for p in administracion.get("/parqueaderos/").json()}
    assert ocupado == {"V-01": True, "V-02": False}


def test_el_listado_de_parqueaderos_dice_que_esta_ocupado_pero_no_por_quien(datos, vigilancia, administracion):
    _, unidad = datos
    v01 = puesto(administracion, "V-01")
    visita(vigilancia, unidad, parqueadero=v01, placa="ZZZ999")

    cuerpo = administracion.get("/parqueaderos/").content.decode()

    assert '"ocupado":true' in cuerpo.replace(" ", "")
    assert "ZZZ999" not in cuerpo and "María" not in cuerpo


def test_sin_puestos_libres_la_lista_llega_vacia_y_la_visita_se_registra_sin_parqueadero(
    datos, vigilancia, administracion
):
    _, unidad = datos
    v01 = puesto(administracion, "V-01")
    assert visita(vigilancia, unidad, parqueadero=v01).status_code == 201
    assert libres(vigilancia) == []

    respuesta = visita(vigilancia, unidad, placa="DEF456")

    assert respuesta.status_code == 201
    assert respuesta.json()["parqueadero"] is None


def test_la_salida_libera_el_puesto_de_inmediato_y_otra_visita_lo_ocupa(datos, vigilancia, administracion):
    _, unidad = datos
    v01 = puesto(administracion, "V-01")
    primera = visita(vigilancia, unidad, parqueadero=v01).json()
    assert libres(vigilancia) == []

    assert salida(vigilancia, primera["id"]).status_code == 200

    assert libres(vigilancia) == ["V-01"]
    segunda = visita(vigilancia, unidad, parqueadero=v01, placa="DEF456")
    assert segunda.status_code == 201 and segunda.json()["parqueadero"] == "V-01"


def test_un_puesto_de_residentes_no_se_ofrece_ni_se_acepta(datos, vigilancia, administracion):
    conjunto, unidad = datos
    r01 = puesto(administracion, "R-01", tipo="residentes")

    respuesta = visita(vigilancia, unidad, parqueadero=r01)

    assert respuesta.status_code == 400
    assert respuesta.json() == {"parqueadero": ["Ese parqueadero no es de visitantes o ya no existe."]}
    with usar_conjunto(conjunto.id):
        assert Visitante.objects.count() == 0
    assert libres(vigilancia) == []


def test_un_puesto_retirado_o_de_otro_conjunto_responde_400(datos, vigilancia, administracion):
    conjunto, unidad = datos
    retirado = puesto(administracion, "V-01")
    administracion.post(f"/parqueaderos/{retirado}/desactivar/")
    otro = Conjunto.objects.create(nombre="Mirador")
    with usar_conjunto(otro.id):
        creador = Persona.objects.create(
            tipo_documento=TipoDocumento.CC, numero_documento="777000111", nombres="Ana", apellidos="Ajena"
        )
        ajeno = Parqueadero.objects.create(codigo="V-01", tipo="visitantes", creado_por=creador)

    assert visita(vigilancia, unidad, parqueadero=retirado).status_code == 400
    assert visita(vigilancia, unidad, parqueadero=ajeno.id).status_code == 400
    with usar_conjunto(conjunto.id):
        assert Visitante.objects.count() == 0


def test_sin_vehiculo_no_se_acepta_un_puesto(datos, vigilancia, administracion):
    conjunto, unidad = datos
    v01 = puesto(administracion, "V-01")

    respuesta = visita(vigilancia, unidad, parqueadero=v01, con_vehiculo=False)

    assert respuesta.status_code == 400
    assert "parqueadero" in respuesta.json()
    with usar_conjunto(conjunto.id):
        assert Visitante.objects.count() == 0


def test_un_puesto_ya_ocupado_responde_409_y_no_crea_la_visita(datos, vigilancia, administracion):
    conjunto, unidad = datos
    v01 = puesto(administracion, "V-01")
    assert visita(vigilancia, unidad, parqueadero=v01).status_code == 201

    respuesta = visita(vigilancia, unidad, parqueadero=v01, placa="DEF456")

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == (
        "Ese parqueadero se acaba de ocupar. Elige otro o registra la visita sin parqueadero."
    )
    with usar_conjunto(conjunto.id):
        assert Visitante.objects.count() == 1


def test_un_puesto_ocupado_no_se_retira_hasta_que_la_visita_salga(datos, vigilancia, administracion):
    _, unidad = datos
    v01 = puesto(administracion, "V-01")
    ocupante = visita(vigilancia, unidad, parqueadero=v01).json()

    bloqueado = administracion.post(f"/parqueaderos/{v01}/desactivar/")
    salida(vigilancia, ocupante["id"])
    retirado = administracion.post(f"/parqueaderos/{v01}/desactivar/")

    assert bloqueado.status_code == 409
    assert bloqueado.json()["detail"] == (
        "Este parqueadero está ocupado por una visita: registra primero su salida."
    )
    assert retirado.status_code == 200
    # El historial conserva el puesto aunque ya esté retirado.
    historial = administracion.get("/visitantes/").json()
    assert historial[0]["parqueadero"] == "V-01"


def test_la_base_no_acepta_dos_visitas_abiertas_en_el_mismo_puesto(datos, administracion):
    conjunto, unidad = datos
    v01 = puesto(administracion, "V-01")

    with usar_conjunto(conjunto.id):
        parqueadero = Parqueadero.objects.get(pk=v01)
        primera = Visitante.objects.create(nombre="A", cedula="1", unidad=unidad, parqueadero=parqueadero)
        with pytest.raises(IntegrityError), transaction.atomic():
            Visitante.objects.create(nombre="B", cedula="2", unidad=unidad, parqueadero=parqueadero)
        # Cuando la primera sale, el puesto vuelve a admitir otra visita.
        Visitante.objects.filter(pk=primera.pk).update(hora_salida=timezone.now())
        Visitante.objects.create(nombre="C", cedula="3", unidad=unidad, parqueadero=parqueadero)
        # Varias visitas sin parqueadero conviven: la condición del índice no las cuenta.
        Visitante.objects.create(nombre="D", cedula="4", unidad=unidad)
        Visitante.objects.create(nombre="E", cedula="5", unidad=unidad)
