"""Pruebas de las unidades y del enrutamiento por vínculos (maestro §5.5), y de su API (HU-08)."""
import uuid
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from rest_framework.test import APIClient

from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.unidades.models import Agrupacion, TipoDeVivienda, TipoVinculo, Unidad, VinculoUnidad
from apps.unidades.servicios import (
    Hecho,
    destinatarios,
    residentes_por_documento,
    unidades_de,
    unidades_para_solicitar,
)

pytestmark = pytest.mark.django_db


def crear_persona(nombres):
    return Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres=nombres,
        apellidos="Gómez",
    )


@pytest.fixture
def torres():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    with usar_conjunto(conjunto.id):
        yield conjunto


@pytest.fixture
def apto_402(torres):
    return Unidad.objects.create(nombre="Torre 3 – 402")


@pytest.fixture
def propietaria_que_arrienda(apto_402):
    """Dueña que no vive ahí, y un arrendatario que sí: dos vínculos sobre la misma unidad."""
    duena = crear_persona("Marta")
    inquilino = crear_persona("Pedro")
    VinculoUnidad.objects.create(persona=duena, unidad=apto_402, tipo=TipoVinculo.PROPIETARIO, reside=False)
    VinculoUnidad.objects.create(persona=inquilino, unidad=apto_402, tipo=TipoVinculo.ARRENDATARIO, reside=True)
    return duena, inquilino


def nombres(personas):
    return sorted(persona.nombres for persona in personas)


@pytest.mark.parametrize(
    ("hecho", "esperados"),
    [
        (Hecho.ANUNCIO_A_VIVIENDA, ["Marta", "Pedro"]),
        (Hecho.OPERATIVO, ["Pedro"]),
        (Hecho.ASAMBLEA, ["Marta"]),
        (Hecho.INFRACCION, ["Marta", "Pedro"]),
        (Hecho.MORA, ["Marta"]),
    ],
)
def test_cada_hecho_llega_a_quien_corresponde_segun_el_vinculo(apto_402, propietaria_que_arrienda, hecho, esperados):
    assert nombres(destinatarios(apto_402, hecho)) == esperados


def test_un_vinculo_cerrado_ya_no_recibe_nada_pero_se_conserva(apto_402, propietaria_que_arrienda):
    _, inquilino = propietaria_que_arrienda
    VinculoUnidad.objects.filter(persona=inquilino).update(vigencia_hasta=timezone.localdate())

    assert nombres(destinatarios(apto_402, Hecho.ANUNCIO_A_VIVIENDA)) == ["Marta"]
    assert VinculoUnidad.objects.filter(persona=inquilino).exists()


def test_un_vinculo_que_aun_no_empieza_no_recibe_nada(apto_402):
    futura = crear_persona("Ana")
    manana = timezone.localdate() + timedelta(days=1)
    VinculoUnidad.objects.create(
        persona=futura, unidad=apto_402, tipo=TipoVinculo.ARRENDATARIO, reside=True, vigencia_desde=manana
    )

    assert not destinatarios(apto_402, Hecho.ANUNCIO_A_VIVIENDA).exists()


def test_no_hay_dos_vinculos_vigentes_iguales_sobre_la_misma_unidad(apto_402, propietaria_que_arrienda):
    duena, _ = propietaria_que_arrienda

    with pytest.raises(IntegrityError), transaction.atomic():
        VinculoUnidad.objects.create(persona=duena, unidad=apto_402, tipo=TipoVinculo.PROPIETARIO, reside=True)


def test_unidades_de_una_persona_son_solo_las_de_sus_vinculos_vigentes(apto_402, propietaria_que_arrienda):
    Unidad.objects.create(nombre="Torre 3 – 403")
    duena, _ = propietaria_que_arrienda

    assert [unidad.nombre for unidad in unidades_de(duena)] == ["Torre 3 – 402"]


def test_la_base_no_deja_que_un_vinculo_apunte_a_una_unidad_de_otro_conjunto(torres):
    mirador = Conjunto.objects.create(nombre="Mirador")
    with usar_conjunto(mirador.id):
        ajena = Unidad.objects.create(nombre="Casa 1")
    persona = crear_persona("Laura")

    with pytest.raises(IntegrityError), transaction.atomic():
        # Se salta save() a propósito: la última barrera es la FK compuesta en la base.
        VinculoUnidad.objects.bulk_create(
            [VinculoUnidad(conjunto=torres, persona=persona, unidad=ajena, tipo=TipoVinculo.PROPIETARIO, reside=True)]
        )


def test_no_hay_dos_agrupaciones_con_la_misma_clave(torres):
    Agrupacion.objects.create(
        etiqueta="Torre", nombre="1", clave="torre 1", tipo_vivienda=TipoDeVivienda.APARTAMENTO, orden=1
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Agrupacion.objects.create(
            etiqueta="TORRE", nombre="1", clave="torre 1", tipo_vivienda=TipoDeVivienda.APARTAMENTO, orden=2
        )


def test_la_base_no_deja_que_una_unidad_apunte_a_una_agrupacion_de_otro_conjunto(torres):
    mirador = Conjunto.objects.create(nombre="Mirador")
    with usar_conjunto(mirador.id):
        ajena = Agrupacion.objects.create(
            etiqueta="Manzana", nombre="A", clave="manzana a", tipo_vivienda=TipoDeVivienda.CASA, orden=1
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        # Se salta save() a propósito: la última barrera es la FK compuesta en la base.
        Unidad.objects.bulk_create([Unidad(conjunto=torres, nombre="Manzana A – Casa 1", agrupacion=ajena)])


def test_solo_se_solicita_a_nombre_de_una_unidad_donde_se_reside(apto_402, propietaria_que_arrienda):
    duena, inquilino = propietaria_que_arrienda

    assert list(unidades_para_solicitar(duena)) == []
    assert [unidad.nombre for unidad in unidades_para_solicitar(inquilino)] == ["Torre 3 – 402"]


# API de unidades y vínculos (HU-08)

CONTRASENA = "una-clave-larga-2026"


def con_cuenta(correo, rol, conjunto, nombres="Laura"):
    persona = crear_persona(nombres)
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
def admin(torres):
    con_cuenta("admin@torres.com", Rol.ADMINISTRACION, torres)
    return cliente_para("admin@torres.com")


@pytest.fixture
def vecinos(torres):
    """Dos personas con rol Residente en el conjunto, sin vínculos todavía."""
    marta = con_cuenta("marta@correo.com", Rol.RESIDENTE, torres, "Marta")
    pedro = con_cuenta("pedro@correo.com", Rol.RESIDENTE, torres, "Pedro")
    return marta, pedro


def vincular_por_api(cliente, unidad, persona, tipo, reside=True, **extra):
    datos = {"persona": str(persona.id), "tipo": tipo, "reside": reside, **extra}
    return cliente.post(f"/unidades/{unidad.id}/vinculos/", datos, format="json")


def nombres_en(detalle, lista):
    return sorted(vinculo["persona"]["nombre"] for vinculo in detalle[lista])


def test_propietario_y_arrendatario_vigentes_coexisten(admin, apto_402, vecinos):
    marta, pedro = vecinos

    assert vincular_por_api(admin, apto_402, marta, "propietario", reside=False).status_code == 201
    assert vincular_por_api(admin, apto_402, pedro, "arrendatario").status_code == 201

    detalle = admin.get(f"/unidades/{apto_402.id}/").json()
    assert nombres_en(detalle, "vigentes") == ["Marta Gómez", "Pedro Gómez"]
    assert detalle["historicos"] == []
    assert admin.get("/unidades/").json() == [
        {"id": str(apto_402.id), "nombre": "Torre 3 – 402", "vinculos_vigentes": 2}
    ]


def test_al_cerrar_el_vinculo_del_arrendatario_el_historico_se_conserva(admin, apto_402, vecinos):
    marta, pedro = vecinos
    vincular_por_api(admin, apto_402, marta, "propietario", reside=False)
    arriendo = vincular_por_api(admin, apto_402, pedro, "arrendatario").json()

    respuesta = admin.post(f"/unidades/{apto_402.id}/vinculos/{arriendo['id']}/cerrar/", {}, format="json")

    assert respuesta.status_code == 200
    assert nombres_en(respuesta.json(), "vigentes") == ["Marta Gómez"]
    assert nombres_en(respuesta.json(), "historicos") == ["Pedro Gómez"]
    assert respuesta.json()["historicos"][0]["vigencia_hasta"] == str(timezone.localdate())
    assert VinculoUnidad.objects.filter(pk=arriendo["id"]).exists()
    assert admin.delete(f"/unidades/{apto_402.id}/vinculos/{arriendo['id']}/cerrar/").status_code == 405


def test_no_se_vincula_a_una_persona_sin_rol_en_el_conjunto(admin, torres, apto_402):
    mirador = Conjunto.objects.create(nombre="Mirador")
    ajena = con_cuenta("ajena@correo.com", Rol.RESIDENTE, mirador, "Ana")

    respuesta = vincular_por_api(admin, apto_402, ajena, "propietario")

    assert respuesta.status_code == 400
    assert respuesta.json()["persona"] == ["Primero vincula a la persona al conjunto."]
    assert not VinculoUnidad.objects.exists()


def test_vinculo_duplicado_responde_409_y_cerrar_dos_veces_tambien(admin, apto_402, vecinos):
    marta, _ = vecinos
    vinculo = vincular_por_api(admin, apto_402, marta, "propietario").json()

    assert vincular_por_api(admin, apto_402, marta, "propietario").status_code == 409
    cerrar = f"/unidades/{apto_402.id}/vinculos/{vinculo['id']}/cerrar/"
    assert admin.post(cerrar, {}, format="json").status_code == 200
    assert admin.post(cerrar, {}, format="json").status_code == 409


def test_el_cierre_no_puede_ser_anterior_al_inicio(admin, apto_402, vecinos):
    marta, _ = vecinos
    manana = timezone.localdate() + timedelta(days=1)
    vinculo = vincular_por_api(admin, apto_402, marta, "arrendatario", vigencia_desde=str(manana)).json()

    respuesta = admin.post(
        f"/unidades/{apto_402.id}/vinculos/{vinculo['id']}/cerrar/",
        {"vigencia_hasta": str(timezone.localdate())},
        format="json",
    )

    assert respuesta.status_code == 400
    assert "vigencia_hasta" in respuesta.json()


def test_crear_unidades_y_vinculos_deja_auditoria(admin, torres, vecinos):
    marta, _ = vecinos
    unidad = admin.post("/unidades/", {"nombre": "Torre 1 – 101"}, format="json")
    vinculo = vincular_por_api(admin, Unidad.objects.get(pk=unidad.json()["id"]), marta, "propietario").json()

    assert unidad.status_code == 201
    assert admin.post("/unidades/", {"nombre": "Torre 1 – 101"}, format="json").status_code == 400
    registros = list(Registro.objects.order_by("creado_en"))
    assert [registro.accion for registro in registros] == ["unidad.crear", "vinculo.registrar"]
    assert registros[1].entidad_id == uuid.UUID(vinculo["id"])


def test_sin_vinculo_gestionar_no_se_crean_unidades_ni_vinculos(torres, apto_402, vecinos):
    marta, _ = vecinos
    residente = cliente_para("marta@correo.com")

    assert residente.post("/unidades/", {"nombre": "Torre 1 – 101"}, format="json").status_code == 403
    assert residente.get(f"/unidades/{apto_402.id}/").status_code == 403
    assert vincular_por_api(residente, apto_402, marta, "propietario").status_code == 403


def test_el_usuario_trae_su_persona_y_cada_asignacion(admin, torres, vecinos):
    marta, _ = vecinos

    usuario = next(u for u in admin.get("/auth/usuarios/").json() if u["nombre"] == "Marta Gómez")

    assert usuario["persona"] == str(marta.id)
    assert [(a["rol"], a["nombre"]) for a in usuario["asignaciones"]] == [("residente", "Residente")]


# Estructura de viviendas (HU-39)

DOS_TORRES = {
    "tipo_vivienda": "apartamento",
    "etiqueta": "Torre",
    "patron": "piso_consecutivo",
    "agrupaciones": [{"nombre": "1", "pisos": 10, "por_piso": 4}, {"nombre": "2", "pisos": 12, "por_piso": 4}],
}
DOS_MANZANAS = {
    "tipo_vivienda": "casa",
    "etiqueta": "Manzana",
    "patron": "consecutivo",
    "agrupaciones": [{"nombre": "A", "cantidad": 10}, {"nombre": "B", "cantidad": 15}],
}


def test_previsualizar_dice_lo_que_se_crearia_y_no_guarda_nada(admin, torres):
    respuesta = admin.post("/unidades/estructura/previsualizar/", DOS_TORRES, format="json")

    assert respuesta.status_code == 200
    assert respuesta.json()["nuevas"] == 88
    assert respuesta.json()["agrupaciones"][1]["ultima"] == "Torre 2 – Apto 1204"
    assert not Unidad.objects.exists() and not Agrupacion.objects.exists()


def test_generar_crea_agrupaciones_y_viviendas_y_deja_un_registro(admin, torres):
    respuesta = admin.post("/unidades/estructura/", DOS_TORRES, format="json")

    assert respuesta.status_code == 201
    assert Agrupacion.objects.count() == 2
    assert Unidad.objects.filter(agrupacion__nombre="2").count() == 48
    vivienda = Unidad.objects.get(nombre="Torre 1 – Apto 302")
    assert (vivienda.tipo, vivienda.numero, vivienda.piso) == ("apartamento", "302", 3)
    assert [registro.accion for registro in Registro.objects.all()] == ["unidad.generar"]


def test_generar_dos_veces_lo_mismo_no_duplica(admin, torres):
    admin.post("/unidades/estructura/", DOS_TORRES, format="json")

    respuesta = admin.post("/unidades/estructura/", DOS_TORRES, format="json")

    assert respuesta.status_code == 200
    assert (respuesta.json()["nuevas"], respuesta.json()["repetidas"]) == (0, 88)
    assert (Agrupacion.objects.count(), Unidad.objects.count()) == (2, 88)


def test_un_conjunto_mixto_se_genera_en_dos_tandas(admin, torres):
    assert admin.post("/unidades/estructura/", DOS_TORRES, format="json").status_code == 201
    assert admin.post("/unidades/estructura/", DOS_MANZANAS, format="json").status_code == 201

    tipos = list(Agrupacion.objects.order_by("orden").values_list("tipo_vivienda", flat=True))
    assert tipos == ["apartamento", "apartamento", "casa", "casa"]
    assert Unidad.objects.filter(tipo=TipoDeVivienda.CASA).count() == 25
    resumen = admin.get("/unidades/agrupaciones/").json()
    assert [fila["nombre_completo"] for fila in resumen["agrupaciones"]][2:] == ["Manzana A", "Manzana B"]
    assert (resumen["agrupaciones"][3]["viviendas"], resumen["sin_agrupar"], resumen["total"]) == (15, 0, 113)


def test_sin_vinculo_gestionar_no_se_ve_ni_se_genera_la_estructura(torres, vecinos):
    residente = cliente_para("marta@correo.com")

    assert residente.post("/unidades/estructura/previsualizar/", DOS_TORRES, format="json").status_code == 403
    assert residente.post("/unidades/estructura/", DOS_TORRES, format="json").status_code == 403
    assert residente.get("/unidades/agrupaciones/").status_code == 403
    assert not Unidad.objects.exists()


def test_mas_de_dos_mil_viviendas_en_una_tanda_responde_400(admin, torres):
    cinco_torres = [{"nombre": str(numero), "pisos": 11, "por_piso": 40} for numero in range(1, 6)]

    respuesta = admin.post("/unidades/estructura/", {**DOS_TORRES, "agrupaciones": cinco_torres}, format="json")

    assert respuesta.status_code == 400
    assert respuesta.json()["non_field_errors"] == ["Son 2200 viviendas. Se registran hasta 2000 a la vez."]
    assert not Unidad.objects.exists()


def test_una_agrupacion_no_cambia_de_tipo_de_vivienda(admin, torres):
    admin.post("/unidades/estructura/", DOS_TORRES, format="json")
    casas_en_la_torre = {**DOS_MANZANAS, "etiqueta": "torre", "agrupaciones": [{"nombre": "1", "cantidad": 5}]}

    respuesta = admin.post("/unidades/estructura/", casas_en_la_torre, format="json")

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "«Torre 1» ya existe y es de otro tipo de vivienda."
    assert admin.post("/unidades/estructura/previsualizar/", casas_en_la_torre, format="json").status_code == 409
    assert not Unidad.objects.filter(tipo=TipoDeVivienda.CASA).exists()


def test_el_listado_sale_por_agrupacion_y_en_orden_natural(admin, torres):
    diez_torres = [{"nombre": str(numero), "pisos": 10, "por_piso": 2} for numero in range(1, 11)]
    admin.post("/unidades/estructura/", {**DOS_TORRES, "agrupaciones": diez_torres}, format="json")

    nombres_en_orden = [unidad["nombre"] for unidad in admin.get("/unidades/").json()]

    def posicion(nombre):
        return nombres_en_orden.index(nombre)

    assert posicion("Torre 2 – Apto 101") < posicion("Torre 10 – Apto 101")
    assert posicion("Torre 1 – Apto 902") < posicion("Torre 1 – Apto 1001")


def test_residentes_por_documento_solo_trae_a_quien_vive_en_el_conjunto_con_sus_viviendas(torres):
    vecina = Persona.objects.create(
        tipo_documento=TipoDocumento.CC, numero_documento="1000000001", nombres="Lucía", apellidos="Gómez"
    )
    dueno = Persona.objects.create(
        tipo_documento=TipoDocumento.CC, numero_documento="1000000002", nombres="Dueño", apellidos="Gómez"
    )
    primera, segunda = Unidad.objects.create(nombre="Torre 1 – 101"), Unidad.objects.create(nombre="Torre 1 – 102")
    VinculoUnidad.objects.create(persona=vecina, unidad=primera, tipo=TipoVinculo.ARRENDATARIO, reside=True)
    VinculoUnidad.objects.create(persona=vecina, unidad=segunda, tipo=TipoVinculo.PROPIETARIO, reside=True)
    VinculoUnidad.objects.create(persona=dueno, unidad=primera, tipo=TipoVinculo.PROPIETARIO, reside=False)

    encontrados = residentes_por_documento("1.000.000.001")

    assert [(e["persona"], [u.nombre for u in e["unidades"]]) for e in encontrados] == [
        (vecina, ["Torre 1 – 101", "Torre 1 – 102"])
    ]
    assert residentes_por_documento("1000000002") == []
    assert residentes_por_documento("   ") == []
