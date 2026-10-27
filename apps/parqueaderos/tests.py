"""Pruebas de HU-28 (el catálogo de parqueaderos del conjunto activo) y de HU-34 (su asignación a una vivienda).

La ocupación por una visita se prueba en `apps/visitantes/test_visitantes.py`.
"""
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.urls import URLResolver, get_resolver
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.parqueaderos.models import AsignacionParqueadero, Parqueadero
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.reglas.models import Regla
from apps.unidades.models import Unidad, VinculoUnidad

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"


def crear_usuario(correo, rol, conjunto):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres="Laura",
        apellidos="Gómez",
    )
    Asignacion.objects.create(persona=persona, rol=rol, conjunto=conjunto)
    Usuario.objects.create_user(correo, CONTRASENA, persona)
    return persona


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
def administracion(torres):
    crear_usuario("admin@torres.com", Rol.ADMINISTRACION, torres)
    return cliente_para("admin@torres.com")


@pytest.fixture
def vigilancia(torres):
    crear_usuario("vigilante@torres.com", Rol.VIGILANCIA, torres)
    return cliente_para("vigilante@torres.com")


@pytest.fixture
def residente(torres):
    crear_usuario("vecino@torres.com", Rol.RESIDENTE, torres)
    return cliente_para("vecino@torres.com")


def crear(cliente, codigo="V-01", tipo="visitantes", **extra):
    return cliente.post("/parqueaderos/", {"codigo": codigo, "tipo": tipo, **extra}, format="json")


# Administración crea, lista y retira


def test_administracion_crea_un_parqueadero_y_lo_lista_con_su_contrato(administracion, torres):
    respuesta = crear(administracion, "V-01", accesible=True, notas="Junto a la portería")

    assert respuesta.status_code == 201
    creado = respuesta.json()
    assert {k: creado[k] for k in ("codigo", "tipo", "accesible", "notas", "ocupado")} == {
        "codigo": "V-01",
        "tipo": "visitantes",
        "accesible": True,
        "notas": "Junto a la portería",
        "ocupado": False,
    }
    assert administracion.get("/parqueaderos/").json() == [creado]


def test_el_codigo_se_guarda_en_mayusculas_y_sin_espacios(administracion):
    respuesta = crear(administracion, "  v-02 ")

    assert respuesta.json()["codigo"] == "V-02"


def test_el_codigo_no_se_repite_ni_sin_distinguir_mayusculas(administracion, torres):
    assert crear(administracion, "V-01").status_code == 201

    repetido = crear(administracion, "v-01", tipo="residentes")

    assert repetido.status_code == 400
    assert repetido.json() == {"codigo": ["Ya existe un parqueadero con ese código en el conjunto."]}
    with usar_conjunto(torres.id):
        assert Parqueadero.objects.count() == 1


def test_la_base_tambien_rechaza_el_codigo_repetido_escribiendo_directo(torres):
    persona = crear_usuario("admin@torres.com", Rol.ADMINISTRACION, torres)
    with usar_conjunto(torres.id):
        Parqueadero.objects.create(codigo="V-01", tipo="visitantes", creado_por=persona)

        with pytest.raises(IntegrityError), transaction.atomic():
            Parqueadero.objects.create(codigo="v-01", tipo="residentes", creado_por=persona)


def test_el_mismo_codigo_puede_existir_en_otro_conjunto(administracion, torres):
    otro = Conjunto.objects.create(nombre="Mirador")
    creador = crear_usuario("otro@mirador.com", Rol.ADMINISTRACION, otro)
    with usar_conjunto(otro.id):
        Parqueadero.objects.create(codigo="V-01", tipo="visitantes", creado_por=creador)

    assert crear(administracion, "V-01").status_code == 201


def test_se_crean_los_dos_tipos_y_el_listado_filtra_por_tipo(administracion):
    crear(administracion, "V-01", "visitantes")
    crear(administracion, "R-01", "residentes")

    todos = administracion.get("/parqueaderos/").json()
    visitantes = administracion.get("/parqueaderos/", {"tipo": "visitantes"}).json()

    assert [p["codigo"] for p in todos] == ["R-01", "V-01"]
    assert [p["codigo"] for p in visitantes] == ["V-01"]
    assert administracion.get("/parqueaderos/", {"tipo": "carros"}).status_code == 400


def test_un_tipo_que_no_existe_o_un_codigo_vacio_se_rechazan(administracion):
    assert crear(administracion, "V-01", tipo="motos").status_code == 400
    assert crear(administracion, "   ").status_code == 400


def test_retirar_un_parqueadero_lo_saca_del_listado_y_queda_en_la_auditoria(administracion, torres):
    creado = crear(administracion, "V-01").json()
    crear(administracion, "V-02")

    respuesta = administracion.post(f"/parqueaderos/{creado['id']}/desactivar/")

    assert respuesta.status_code == 200
    assert [p["codigo"] for p in administracion.get("/parqueaderos/").json()] == ["V-02"]
    with usar_conjunto(torres.id):
        registro = Registro.objects.get(accion="parqueadero.desactivar", entidad_id=creado["id"])
        assert Parqueadero.objects.get(pk=creado["id"]).activo is False
        assert Registro.objects.filter(accion="parqueadero.crear").count() == 2
    assert registro.antes == {"activo": True}
    assert registro.despues == {"activo": False, "codigo": "V-01"}
    # Ya retirado, no está: no se retira dos veces.
    assert administracion.post(f"/parqueaderos/{creado['id']}/desactivar/").status_code == 404


def test_un_codigo_retirado_sigue_ocupando_el_codigo(administracion):
    creado = crear(administracion, "V-01").json()
    administracion.post(f"/parqueaderos/{creado['id']}/desactivar/")

    assert crear(administracion, "V-01").status_code == 400


# Quién puede qué


def test_vigilancia_lista_los_parqueaderos_y_no_los_crea(administracion, vigilancia):
    creado = crear(administracion, "V-01").json()

    listado = vigilancia.get("/parqueaderos/", {"tipo": "visitantes", "libres": "1"})
    creacion = crear(vigilancia, "V-09")
    retiro = vigilancia.post(f"/parqueaderos/{creado['id']}/desactivar/")

    assert listado.status_code == 200 and [p["codigo"] for p in listado.json()] == ["V-01"]
    assert creacion.status_code == 403
    assert retiro.status_code == 403


def test_un_residente_no_ve_ni_crea_ni_retira(administracion, residente):
    creado = crear(administracion, "V-01").json()

    assert residente.get("/parqueaderos/").status_code == 403
    assert crear(residente, "V-09").status_code == 403
    assert residente.post(f"/parqueaderos/{creado['id']}/desactivar/").status_code == 403


def test_el_permiso_nuevo_es_de_administracion_y_no_es_sensible():
    from apps.permisos.catalogo import PERMISOS, PERMISOS_POR_ROL, PERMISOS_SENSIBLES

    assert "parqueadero.gestionar" in PERMISOS
    assert "parqueadero.gestionar" in PERMISOS_POR_ROL[Rol.ADMINISTRACION]
    assert "parqueadero.gestionar" not in PERMISOS_SENSIBLES
    for rol in (Rol.SECRETARIA, Rol.VIGILANCIA, Rol.RESIDENTE):
        assert "parqueadero.gestionar" not in PERMISOS_POR_ROL[rol]


def rutas_de_parqueaderos(patrones):
    for patron in patrones:
        if isinstance(patron, URLResolver):
            yield from rutas_de_parqueaderos(patron.url_patterns)
        elif str(patron.callback.__module__).startswith("apps.parqueaderos"):
            yield str(patron.pattern), patron.name


# HU-34: asignar un parqueadero de residentes a una vivienda


@pytest.fixture
def viviendas(torres):
    with usar_conjunto(torres.id):
        return Unidad.objects.create(nombre="Torre 1 – 101"), Unidad.objects.create(nombre="Torre 2 – 202")


def asignar(cliente, parqueadero, unidad):
    return cliente.post(f"/parqueaderos/{parqueadero['id']}/asignacion/", {"unidad": str(unidad.id)}, format="json")


def liberar(cliente, parqueadero):
    return cliente.post(f"/parqueaderos/{parqueadero['id']}/liberacion/")


def definir_tope(torres, carro, moto, bicicleta):
    with usar_conjunto(torres.id):
        Regla.objects.create(
            tipo="PARQUEADEROS_POR_VIVIENDA",
            parametros={"carro": carro, "moto": moto, "bicicleta": bicicleta},
            creada_por=Persona.objects.first(),
        )


def vigentes_de(parqueadero_id, torres):
    with usar_conjunto(torres.id):
        return AsignacionParqueadero.objects.filter(parqueadero_id=parqueadero_id, vigencia_hasta__isnull=True).count()


def test_hu34_la_base_deja_una_sola_asignacion_vigente_por_puesto(torres, viviendas):
    persona = crear_usuario("admin@torres.com", Rol.ADMINISTRACION, torres)
    with usar_conjunto(torres.id):
        puesto = Parqueadero.objects.create(codigo="R-01", tipo="residentes", creado_por=persona)
        AsignacionParqueadero.objects.create(parqueadero=puesto, unidad=viviendas[0], registrado_por=persona)

        with pytest.raises(IntegrityError), transaction.atomic():
            AsignacionParqueadero.objects.create(parqueadero=puesto, unidad=viviendas[1], registrado_por=persona)

        # Cerrada la primera, otra puede entrar: «único mientras esté vigente».
        AsignacionParqueadero.objects.update(vigencia_hasta=timezone.localdate())
        AsignacionParqueadero.objects.create(parqueadero=puesto, unidad=viviendas[1], registrado_por=persona)


def test_hu34_la_base_no_acepta_una_asignacion_que_termina_antes_de_empezar(torres, viviendas):
    persona = crear_usuario("admin@torres.com", Rol.ADMINISTRACION, torres)
    hoy = timezone.localdate()
    with usar_conjunto(torres.id):
        puesto = Parqueadero.objects.create(codigo="R-01", tipo="residentes", creado_por=persona)

        with pytest.raises(IntegrityError), transaction.atomic():
            AsignacionParqueadero.objects.create(
                parqueadero=puesto, unidad=viviendas[0], registrado_por=persona,
                vigencia_desde=hoy, vigencia_hasta=hoy - timedelta(days=1),
            )


def test_hu34_la_base_no_mezcla_conjuntos_en_la_asignacion(torres, viviendas):
    otro = Conjunto.objects.create(nombre="Mirador")
    ajena = crear_usuario("otro@mirador.com", Rol.ADMINISTRACION, otro)
    with usar_conjunto(otro.id):
        puesto = Parqueadero.objects.create(codigo="R-01", tipo="residentes", creado_por=ajena)

    with usar_conjunto(torres.id):
        with pytest.raises(IntegrityError), transaction.atomic():
            # La vivienda es de Torres y el puesto de Mirador: la FK compuesta lo rechaza.
            AsignacionParqueadero.objects.create(parqueadero=puesto, unidad=viviendas[0], registrado_por=ajena)


def test_hu34_la_base_no_sabe_que_un_puesto_de_visitantes_no_se_asigna(torres, viviendas):
    # Dejado dicho: que el puesto sea de residentes lo comprueba el servicio; un CHECK no mira otra tabla.
    persona = crear_usuario("admin@torres.com", Rol.ADMINISTRACION, torres)
    with usar_conjunto(torres.id):
        visitantes = Parqueadero.objects.create(codigo="V-01", tipo="visitantes", creado_por=persona)

        AsignacionParqueadero.objects.create(parqueadero=visitantes, unidad=viviendas[0], registrado_por=persona)


def test_hu34_un_puesto_libre_queda_con_una_sola_asignacion_vigente(administracion, torres, viviendas):
    puesto = crear(administracion, "R-01", "residentes").json()
    assert puesto["asignado_a"] is None and puesto["vehiculo"] == "carro"

    respuesta = asignar(administracion, puesto, viviendas[0])

    assert respuesta.status_code == 201
    assert respuesta.json()["reasignada"] is False and respuesta.json()["vivienda"] == "Torre 1 – 101"
    assert vigentes_de(puesto["id"], torres) == 1
    listado = administracion.get("/parqueaderos/").json()
    assert [(p["codigo"], p["asignado_a"]) for p in listado] == [("R-01", "Torre 1 – 101")]


def test_hu34_la_asignacion_dice_quien_la_registro_y_desde_cuando(administracion, torres, viviendas):
    puesto = crear(administracion, "R-01", "residentes").json()
    asignar(administracion, puesto, viviendas[0])

    historial = administracion.get(f"/parqueaderos/{puesto['id']}/asignaciones/").json()

    assert len(historial) == 1
    assert historial[0]["vigencia_desde"] == str(timezone.localdate()) and historial[0]["vigencia_hasta"] is None
    assert historial[0]["registrado_por"] == "Laura Gómez" and historial[0]["cerrado_por"] is None


def test_hu34_reasignar_cierra_la_anterior_con_fecha_y_conserva_el_historial(administracion, torres, viviendas):
    puesto = crear(administracion, "R-01", "residentes").json()
    asignar(administracion, puesto, viviendas[0])

    respuesta = asignar(administracion, puesto, viviendas[1])

    assert respuesta.status_code == 200 and respuesta.json()["reasignada"] is True
    assert vigentes_de(puesto["id"], torres) == 1
    historial = administracion.get(f"/parqueaderos/{puesto['id']}/asignaciones/").json()
    assert [(fila["vivienda"], fila["vigencia_hasta"]) for fila in historial] == [
        ("Torre 2 – 202", None),
        ("Torre 1 – 101", str(timezone.localdate())),
    ]
    assert historial[1]["cerrado_por"] == "Laura Gómez"
    with usar_conjunto(torres.id):
        assert Registro.objects.filter(accion="parqueadero.asignar").count() == 1
        reasignacion = Registro.objects.get(accion="parqueadero.reasignar")
    assert reasignacion.antes["unidad"] == "Torre 1 – 101" and reasignacion.despues["unidad"] == "Torre 2 – 202"


def test_hu34_reasignar_a_la_misma_vivienda_es_un_conflicto(administracion, torres, viviendas):
    puesto = crear(administracion, "R-01", "residentes").json()
    asignar(administracion, puesto, viviendas[0])

    respuesta = asignar(administracion, puesto, viviendas[0])

    assert respuesta.status_code == 409
    assert vigentes_de(puesto["id"], torres) == 1
    assert len(administracion.get(f"/parqueaderos/{puesto['id']}/asignaciones/").json()) == 1


def test_hu34_un_parqueadero_de_visitantes_no_se_asigna(administracion, torres, viviendas):
    visitantes = crear(administracion, "V-01", "visitantes").json()

    respuesta = asignar(administracion, visitantes, viviendas[0])

    # No se «deniega» (403): el puesto de visitantes no se encuentra para esta operación.
    assert respuesta.status_code == 404
    assert liberar(administracion, visitantes).status_code == 404
    assert administracion.get(f"/parqueaderos/{visitantes['id']}/asignaciones/").status_code == 404
    with usar_conjunto(torres.id):
        assert AsignacionParqueadero.objects.count() == 0
    assert administracion.get("/parqueaderos/").json()[0]["asignado_a"] is None


def test_hu34_la_vivienda_debe_existir_en_el_conjunto(administracion, torres):
    otro = Conjunto.objects.create(nombre="Mirador")
    with usar_conjunto(otro.id):
        ajena = Unidad.objects.create(nombre="Torre 9 – 901")
    puesto = crear(administracion, "R-01", "residentes").json()

    respuesta = asignar(administracion, puesto, ajena)

    assert respuesta.status_code == 400 and "unidad" in respuesta.json()
    assert administracion.post(f"/parqueaderos/{puesto['id']}/asignacion/", {}, format="json").status_code == 400


def test_hu34_liberar_deja_el_puesto_sin_asignar_y_conserva_el_historial(administracion, torres, viviendas):
    puesto = crear(administracion, "R-01", "residentes").json()
    asignar(administracion, puesto, viviendas[0])

    respuesta = liberar(administracion, puesto)

    assert respuesta.status_code == 200 and respuesta.json()["vigencia_hasta"] == str(timezone.localdate())
    assert administracion.get("/parqueaderos/").json()[0]["asignado_a"] is None
    historial = administracion.get(f"/parqueaderos/{puesto['id']}/asignaciones/").json()
    assert len(historial) == 1 and historial[0]["cerrado_por"] == "Laura Gómez"
    # Ya libre: no hay nada que liberar.
    assert liberar(administracion, puesto).status_code == 409
    with usar_conjunto(torres.id):
        assert Registro.objects.filter(accion="parqueadero.liberar").count() == 1
    # Libre otra vez, se asigna a cualquiera.
    assert asignar(administracion, puesto, viviendas[1]).status_code == 201


def test_hu34_un_puesto_asignado_no_se_retira_hasta_liberarlo(administracion, viviendas):
    puesto = crear(administracion, "R-01", "residentes").json()
    asignar(administracion, puesto, viviendas[0])

    retiro = administracion.post(f"/parqueaderos/{puesto['id']}/desactivar/")

    assert retiro.status_code == 409
    liberar(administracion, puesto)
    assert administracion.post(f"/parqueaderos/{puesto['id']}/desactivar/").status_code == 200


# El tope por vivienda y por tipo de vehículo (D2, D5, D6)


def test_hu34_sin_la_regla_una_vivienda_puede_tener_varios_puestos_del_mismo_vehiculo(administracion, viviendas):
    primero = crear(administracion, "R-01", "residentes").json()
    segundo = crear(administracion, "R-02", "residentes").json()

    assert asignar(administracion, primero, viviendas[0]).status_code == 201
    assert asignar(administracion, segundo, viviendas[0]).status_code == 201


def test_hu34_con_la_regla_el_tope_se_cuenta_por_vehiculo(administracion, torres, viviendas):
    definir_tope(torres, carro=1, moto=1, bicicleta=0)
    carro = crear(administracion, "R-01", "residentes", vehiculo="carro").json()
    otro_carro = crear(administracion, "R-02", "residentes", vehiculo="carro").json()
    moto = crear(administracion, "M-01", "residentes", vehiculo="moto").json()
    bici = crear(administracion, "B-01", "residentes", vehiculo="bicicleta").json()

    assert asignar(administracion, carro, viviendas[0]).status_code == 201
    segundo_carro = asignar(administracion, otro_carro, viviendas[0])
    assert segundo_carro.status_code == 409 and "máximo" in segundo_carro.json()["detail"]
    assert asignar(administracion, moto, viviendas[0]).status_code == 201
    sin_bicicletas = asignar(administracion, bici, viviendas[0])
    assert sin_bicicletas.status_code == 409 and "no asigna parqueaderos de bicicleta" in sin_bicicletas.json()["detail"]
    # Otra vivienda tiene su propio cupo.
    assert asignar(administracion, otro_carro, viviendas[1]).status_code == 201


def test_hu34_reasignar_dentro_del_tope_solo_cuenta_la_vivienda_que_recibe(administracion, torres, viviendas):
    definir_tope(torres, carro=1, moto=1, bicicleta=1)
    carro = crear(administracion, "R-01", "residentes").json()
    asignar(administracion, carro, viviendas[0])

    # La 101 queda libre de carro al cederlo; la 202 lo recibe porque no tiene ninguno.
    assert asignar(administracion, carro, viviendas[1]).status_code == 200
    # Y la 202, llena, no recibe otro.
    otro = crear(administracion, "R-02", "residentes").json()
    assert asignar(administracion, otro, viviendas[1]).status_code == 409
    assert asignar(administracion, otro, viviendas[0]).status_code == 201


def test_hu34_la_regla_solo_limita_asignaciones_nuevas(administracion, torres, viviendas):
    carro = crear(administracion, "R-01", "residentes").json()
    otro = crear(administracion, "R-02", "residentes").json()
    asignar(administracion, carro, viviendas[0])
    asignar(administracion, otro, viviendas[0])

    definir_tope(torres, carro=1, moto=1, bicicleta=1)

    # Ya tiene dos: no se le quita ninguno, pero tampoco se le suma un tercero.
    assert vigentes_de(carro["id"], torres) == 1 and vigentes_de(otro["id"], torres) == 1
    tercero = crear(administracion, "R-03", "residentes").json()
    assert asignar(administracion, tercero, viviendas[0]).status_code == 409


def test_hu34_la_regla_nueva_no_la_evalua_ningun_evaluador_de_reservas():
    from apps.reglas.catalogo import MODOS_POR_TIPO, NIVEL_POR_TIPO, TipoDeRegla

    assert NIVEL_POR_TIPO[TipoDeRegla.PARQUEADEROS_POR_VIVIENDA].value == "alfa"
    assert MODOS_POR_TIPO[TipoDeRegla.PARQUEADEROS_POR_VIVIENDA] == []


def test_hu34_el_vehiculo_vale_carro_por_defecto_y_se_valida(administracion):
    assert crear(administracion, "R-01", "residentes").json()["vehiculo"] == "carro"
    assert crear(administracion, "M-01", "residentes", vehiculo="moto").json()["vehiculo"] == "moto"
    assert crear(administracion, "X-01", "residentes", vehiculo="avion").status_code == 400


# Quién puede qué


def test_hu34_solo_administracion_asigna_y_libera(administracion, vigilancia, residente, viviendas):
    puesto = crear(administracion, "R-01", "residentes").json()

    for cliente in (vigilancia, residente):
        assert asignar(cliente, puesto, viviendas[0]).status_code == 403
        assert liberar(cliente, puesto).status_code == 403
        assert cliente.get(f"/parqueaderos/{puesto['id']}/asignaciones/").status_code == 403


def test_hu34_el_permiso_de_asignar_ya_existe_y_no_se_toco_el_catalogo():
    from apps.permisos.catalogo import PERMISOS, PERMISOS_POR_ROL, PERMISOS_SENSIBLES

    assert "parqueadero.asignar" in PERMISOS and "parqueadero.asignar" in PERMISOS_POR_ROL[Rol.ADMINISTRACION]
    assert "parqueadero.asignar" not in PERMISOS_SENSIBLES
    for rol in (Rol.SECRETARIA, Rol.VIGILANCIA, Rol.RESIDENTE):
        assert "parqueadero.asignar" not in PERMISOS_POR_ROL[rol]


# «Mi parqueadero»


def residente_de(torres, unidad, correo="vecino@torres.com", **vinculo):
    persona = crear_usuario(correo, Rol.RESIDENTE, torres)
    with usar_conjunto(torres.id):
        VinculoUnidad.objects.create(persona=persona, unidad=unidad, tipo="arrendatario", reside=True, **vinculo)
    return cliente_para(correo)


def test_hu34_el_residente_ve_solo_los_puestos_vigentes_de_su_vivienda(administracion, torres, viviendas):
    vecino = residente_de(torres, viviendas[0])
    suyo = crear(administracion, "R-01", "residentes", vehiculo="moto").json()
    ajeno = crear(administracion, "R-02", "residentes").json()
    cedido = crear(administracion, "R-03", "residentes").json()
    asignar(administracion, suyo, viviendas[0])
    asignar(administracion, ajeno, viviendas[1])
    asignar(administracion, cedido, viviendas[0])
    liberar(administracion, cedido)

    respuesta = vecino.get("/parqueaderos/mios/")

    assert respuesta.status_code == 200
    assert [(p["codigo"], p["vehiculo"], p["vivienda"]) for p in respuesta.json()] == [("R-01", "moto", "Torre 1 – 101")]
    # Al cambiar de vivienda el puesto sale de «Mi parqueadero» y entra en el de la otra.
    asignar(administracion, suyo, viviendas[1])
    assert vecino.get("/parqueaderos/mios/").json() == []


def test_hu34_quien_no_tiene_vinculo_vigente_no_ve_nada(administracion, torres, viviendas):
    sin_vinculo = residente_de(torres, viviendas[0], vigencia_hasta=timezone.localdate())
    puesto = crear(administracion, "R-01", "residentes").json()
    asignar(administracion, puesto, viviendas[0])

    assert sin_vinculo.get("/parqueaderos/mios/").json() == []
    assert administracion.get("/parqueaderos/mios/").json() == []


# Lo que no existe


def test_hu34_no_existe_operacion_de_restriccion_por_mora():
    rutas = list(rutas_de_parqueaderos(get_resolver().url_patterns))

    assert rutas, "no se encontraron las rutas de parqueaderos"
    prohibidas = ("restring", "suspend", "retirar", "bloque", "mora", "sancion", "multa", "quitar")
    assert not [ruta for ruta in rutas if any(palabra in ruta[0] or palabra in (ruta[1] or "") for palabra in prohibidas)]
    # Las únicas rutas: asignar (o reasignar), liberar, el historial, las propias y las del catálogo.
    assert sorted(ruta[1] for ruta in rutas) == [
        "parqueadero-asignacion",
        "parqueadero-asignaciones",
        "parqueadero-desactivar",
        "parqueadero-liberacion",
        "parqueaderos",
        "parqueaderos-mios",
    ]


def test_hu34_el_servicio_no_conoce_la_mora():
    import inspect

    from apps.parqueaderos import servicios

    # El módulo la nombra en su docstring para decir que no existe; lo que no puede es preguntar por ella.
    fuente = inspect.getsource(servicios)
    assert "apps.pagos" not in fuente and "unidad_en_mora" not in fuente and "apps.reglas.mora" not in fuente


def test_hu34_el_puesto_no_apunta_a_una_unidad_y_la_api_de_crear_la_ignora(administracion, viviendas):
    campos_hacia_unidad = [
        campo for campo in Parqueadero._meta.get_fields() if getattr(campo.related_model, "__name__", "") == "Unidad"
    ]
    # La relación vive en la asignación, no en el puesto.
    assert campos_hacia_unidad == []

    respuesta = crear(administracion, "R-01", "residentes", unidad=str(viviendas[0].id))

    assert respuesta.status_code == 201
    assert respuesta.json()["asignado_a"] is None
