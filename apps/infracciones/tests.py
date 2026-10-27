"""Pruebas de HU-30: el registro de una infracción que se comunica, se cierra o se anula. El sistema no sanciona."""
from datetime import timedelta
from unittest import mock

import pytest
from django.db import IntegrityError, transaction
from django.urls import URLResolver, get_resolver
from django.utils import timezone
from rest_framework.test import APIClient

from apps.anuncios.models import Anuncio
from apps.auditoria.models import Registro
from apps.casos.models import Caso
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.infracciones.models import RegistroDeInfraccion
from apps.infracciones.servicios import FRASE_DE_R11
from apps.notificaciones.models import Notificacion
from apps.permisos.catalogo import PERMISOS, PERMISOS_POR_ROL, PERMISOS_SENSIBLES, Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.unidades.models import TipoVinculo, Unidad, VinculoUnidad

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"
HOY = timezone.localdate


def crear_usuario(correo, rol, conjunto, nombres="Laura"):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres=nombres,
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
    return Conjunto.objects.create(nombre="Torres del Río", direccion="Calle 9 # 4-50")


@pytest.fixture
def administradora(torres):
    return crear_usuario("admin@torres.com", Rol.ADMINISTRACION, torres, nombres="Laura")


@pytest.fixture
def admin(administradora):
    return cliente_para("admin@torres.com")


@pytest.fixture
def superusuario(torres):
    crear_usuario("super@admind.com", Rol.SUPERUSUARIO, None, nombres="Sonia")
    cliente = cliente_para("super@admind.com")
    cliente.post("/auth/conjunto-activo/", {"conjunto": str(torres.id)}, format="json")
    return cliente


@pytest.fixture
def apto(torres):
    with usar_conjunto(torres.id):
        return Unidad.objects.create(nombre="Torre 1 – 101")


@pytest.fixture
def duenos(torres, apto):
    """El propietario que no vive ahí y el arrendatario que sí: los dos reciben (C-318/02)."""
    propietario = crear_usuario("marta@torres.com", Rol.RESIDENTE, torres, nombres="Marta")
    inquilino = crear_usuario("pedro@torres.com", Rol.RESIDENTE, torres, nombres="Pedro")
    with usar_conjunto(torres.id):
        VinculoUnidad.objects.create(persona=propietario, unidad=apto, tipo=TipoVinculo.PROPIETARIO, reside=False)
        VinculoUnidad.objects.create(persona=inquilino, unidad=apto, tipo=TipoVinculo.ARRENDATARIO, reside=True)
    return propietario, inquilino


def registrar(cliente, apto, descripcion="Música a alto volumen pasada la medianoche", dias_atras=2, **extra):
    datos = {
        "unidad": str(apto.id),
        "descripcion_hecho": descripcion,
        "fecha_hecho": str(HOY() - timedelta(days=dias_atras)),
        **extra,
    }
    return cliente.post("/infracciones/", datos, format="json")


def filas(torres):
    with usar_conjunto(torres.id):
        return list(RegistroDeInfraccion.objects.order_by("registrado_en"))


# Lo que hace cumplir la base, aunque alguien se salte el servicio


def test_hu30_registro_sin_fecha_de_notificacion_falla(torres, apto, administradora):
    with usar_conjunto(torres.id):
        with pytest.raises(IntegrityError), transaction.atomic():
            RegistroDeInfraccion.objects.create(
                unidad=apto, descripcion_hecho="Ruido", fecha_hecho=HOY(), registrado_por=administradora
            )


def test_hu30_no_existe_campo_de_sancion_multa_ni_restriccion():
    campos = {campo.name for campo in RegistroDeInfraccion._meta.get_fields()}

    for prohibido in ("sancion", "multa", "restriccion", "estado", "monto", "valor"):
        assert not [campo for campo in campos if prohibido in campo], prohibido
    # Abierto o cerrado se deduce de `cierre_fecha`: no hay un segundo dato que lo contradiga.
    assert "cierre_fecha" in campos


def test_la_base_no_acepta_un_cierre_a_medias_ni_una_anulacion_sin_motivo(torres, apto, administradora):
    base = dict(unidad=apto, descripcion_hecho="Ruido", fecha_hecho=HOY(), registrado_por=administradora,
                fecha_notificacion=timezone.now())
    with usar_conjunto(torres.id):
        for invalido in (
            {"cierre_fecha": timezone.now()},
            {"cierre_comentario": "Hablado con el vecino"},
            {"cierre_fecha": timezone.now(), "cierre_comentario": ""},
            {"anulado": True},
            {"anulado": True, "anulacion_motivo": "Error", "anulado_por": administradora},
            {"descripcion_hecho": ""},
        ):
            with pytest.raises(IntegrityError), transaction.atomic():
                RegistroDeInfraccion.objects.create(**{**base, **invalido})
        RegistroDeInfraccion.objects.create(
            **base, cierre_fecha=timezone.now(), cierre_comentario="Resuelto", cerrado_por=administradora
        )


def test_la_base_no_mezcla_conjuntos_en_la_infraccion(torres, administradora):
    otro = Conjunto.objects.create(nombre="Mirador")
    ajena = crear_usuario("otro@mirador.com", Rol.ADMINISTRACION, otro)
    with usar_conjunto(otro.id):
        vivienda_ajena = Unidad.objects.create(nombre="Torre 9 – 901")

    with usar_conjunto(torres.id):
        with pytest.raises(IntegrityError), transaction.atomic():
            # La vivienda es de Mirador y el registro de Torres: la FK compuesta lo rechaza.
            RegistroDeInfraccion.objects.create(
                unidad=vivienda_ajena, descripcion_hecho="Ruido", fecha_hecho=HOY(), registrado_por=ajena,
                fecha_notificacion=timezone.now(),
            )


# Registrar y comunicar


def test_hu30_propietario_y_arrendatario_reciben_la_comunicacion(admin, torres, apto, duenos):
    respuesta = registrar(admin, apto)

    assert respuesta.status_code == 201
    creado = respuesta.json()
    assert creado["vivienda"] == "Torre 1 – 101" and creado["abierto"] is True and creado["fecha_notificacion"]
    with usar_conjunto(torres.id):
        avisos = Notificacion.objects.filter(origen="infraccion", referencia=creado["id"])
        assert sorted(aviso.persona.nombres for aviso in avisos) == ["Marta", "Pedro"]
        aviso = avisos.first()
    assert aviso.titulo == "Registro de infracción"
    assert "Música a alto volumen" in aviso.cuerpo and "Torre 1 – 101" in aviso.cuerpo
    # R11: el aviso dice que no es una sanción ni reemplaza el debido proceso.
    assert FRASE_DE_R11 in aviso.cuerpo and "No es una sanción" in aviso.cuerpo


def test_el_aviso_no_dice_quien_registro(admin, torres, apto, duenos):
    registrar(admin, apto)

    with usar_conjunto(torres.id):
        cuerpos = " ".join(Notificacion.objects.values_list("cuerpo", flat=True))
    assert "Laura" not in cuerpos and "Gómez" not in cuerpos


def test_hu30_el_registro_sella_la_fecha_de_notificacion_en_la_misma_transaccion(admin, torres, apto, duenos):
    antes = timezone.now()

    registrar(admin, apto)

    (registro,) = filas(torres)
    assert antes <= registro.fecha_notificacion <= timezone.now() and registro.cierre_fecha is None


def test_hu30_una_vivienda_sin_vinculos_vigentes_no_se_puede_registrar(admin, torres, apto):
    respuesta = registrar(admin, apto)

    assert respuesta.status_code == 400
    assert respuesta.json() == {"unidad": ["La vivienda no tiene a quién comunicarle."]}
    assert filas(torres) == []
    with usar_conjunto(torres.id):
        assert Notificacion.objects.count() == 0


def test_hu30_si_la_comunicacion_falla_no_queda_registro(admin, torres, apto, duenos):
    with mock.patch("apps.infracciones.servicios.notificar", side_effect=RuntimeError("canal caído")):
        with pytest.raises(RuntimeError):
            registrar(admin, apto)

    assert filas(torres) == []
    with usar_conjunto(torres.id):
        assert Notificacion.objects.count() == 0 and not Registro.objects.filter(accion="infraccion.registrar").exists()


def test_un_vinculo_cerrado_ya_no_recibe_la_comunicacion(admin, torres, apto, duenos):
    _, inquilino = duenos
    with usar_conjunto(torres.id):
        VinculoUnidad.objects.filter(persona=inquilino).update(vigencia_hasta=HOY())

    registrar(admin, apto)

    with usar_conjunto(torres.id):
        assert [n.persona.nombres for n in Notificacion.objects.all()] == ["Marta"]


def test_hu30_la_infraccion_puede_nacer_de_un_caso(admin, torres, apto, duenos, administradora):
    with usar_conjunto(torres.id):
        caso = Caso.objects.create(titulo="Ruido", cuerpo="Fiesta", autor=duenos[1])

    respuesta = registrar(admin, apto, caso=str(caso.id))

    assert respuesta.status_code == 201 and respuesta.json()["caso"] == str(caso.id)
    assert registrar(admin, apto, caso=str(caso.id).replace(str(caso.id)[:8], "00000000")).status_code == 400


def test_se_valida_lo_que_llega(admin, apto, duenos):
    futuro = str(HOY() + timedelta(days=1))

    assert registrar(admin, apto, descripcion="   ").status_code == 400
    assert registrar(admin, apto, fecha_hecho=futuro).json() == {"fecha_hecho": ["La fecha del hecho no puede ser futura."]}
    assert admin.post("/infracciones/", {"unidad": str(apto.id)}, format="json").status_code == 400
    assert registrar(admin, apto, unidad="3b1c2d4e-0000-4000-8000-000000000000").status_code == 400


def test_el_registro_nunca_llega_al_tablon_de_anuncios(admin, torres, apto, duenos):
    registrar(admin, apto)

    with usar_conjunto(torres.id):
        assert Anuncio.objects.count() == 0


def test_hu30_registrar_deja_la_auditoria(admin, torres, apto, duenos):
    creado = registrar(admin, apto).json()

    with usar_conjunto(torres.id):
        registro = Registro.objects.get(accion="infraccion.registrar")
    assert str(registro.entidad_id) == creado["id"] and registro.despues["unidad"] == "Torre 1 – 101"


# Cerrar


def test_hu30_cerrar_no_modifica_la_comunicacion_original(admin, torres, apto, duenos):
    creado = registrar(admin, apto).json()

    respuesta = admin.post(f"/infracciones/{creado['id']}/cierre/", {"comentario": "Se habló con el arrendatario"}, format="json")

    assert respuesta.status_code == 200
    cerrado = respuesta.json()
    assert cerrado["abierto"] is False and cerrado["cierre_comentario"] == "Se habló con el arrendatario"
    assert cerrado["cierre_fecha"] and cerrado["cerrado_por"] == "Laura Gómez"
    for campo in ("descripcion_hecho", "fecha_hecho", "fecha_notificacion", "registrado_en", "registrado_por"):
        assert cerrado[campo] == creado[campo], campo


def test_el_cierre_solo_acepta_el_comentario_y_la_fecha_la_pone_el_sistema(admin, apto, duenos):
    creado = registrar(admin, apto).json()
    ayer = str(timezone.now() - timedelta(days=3))

    respuesta = admin.post(
        f"/infracciones/{creado['id']}/cierre/",
        {"comentario": "Cerrado", "cierre_fecha": ayer, "fecha_notificacion": ayer, "descripcion_hecho": "otra"},
        format="json",
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["descripcion_hecho"] == creado["descripcion_hecho"]
    assert respuesta.json()["cierre_fecha"] != ayer and respuesta.json()["fecha_notificacion"] == creado["fecha_notificacion"]
    assert admin.post(f"/infracciones/{creado['id']}/cierre/", {}, format="json").status_code in (400, 409)


def test_hu30_cerrar_dos_veces_es_un_conflicto_y_el_comentario_no_cambia(admin, apto, duenos):
    creado = registrar(admin, apto).json()
    admin.post(f"/infracciones/{creado['id']}/cierre/", {"comentario": "Primero"}, format="json")

    segundo = admin.post(f"/infracciones/{creado['id']}/cierre/", {"comentario": "Segundo"}, format="json")

    assert segundo.status_code == 409
    assert admin.get(f"/infracciones/{creado['id']}/").json()["cierre_comentario"] == "Primero"


def test_cerrar_avisa_a_la_vivienda_y_la_auditoria_guarda_antes_y_despues(admin, torres, apto, duenos):
    creado = registrar(admin, apto).json()

    admin.post(f"/infracciones/{creado['id']}/cierre/", {"comentario": "Resuelto"}, format="json")

    with usar_conjunto(torres.id):
        cierres = Notificacion.objects.filter(origen="infraccion.cierre", referencia=creado["id"])
        assert sorted(n.persona.nombres for n in cierres) == ["Marta", "Pedro"]
        registro = Registro.objects.get(accion="infraccion.cerrar")
    assert FRASE_DE_R11 in cierres.first().cuerpo and "Resuelto" in cierres.first().cuerpo
    assert registro.antes["cierre_fecha"] is None and registro.despues["cierre_fecha"] is not None


def test_cerrar_sin_comentario_no_se_acepta(admin, apto, duenos):
    creado = registrar(admin, apto).json()

    assert admin.post(f"/infracciones/{creado['id']}/cierre/", {"comentario": "  "}, format="json").status_code == 400
    assert admin.get(f"/infracciones/{creado['id']}/").json()["abierto"] is True


# Anular: solo el Superusuario, y no se borra


def test_hu30_el_administrador_no_puede_borrar_y_solo_el_superusuario_anula(admin, superusuario, torres, apto, duenos):
    creado = registrar(admin, apto).json()
    url = f"/infracciones/{creado['id']}/"

    assert admin.delete(url).status_code == 405
    assert admin.put(url, {}, format="json").status_code == 405
    assert admin.patch(url, {}, format="json").status_code == 405
    assert admin.post(f"{url}anulacion/", {"motivo": "Me equivoqué"}, format="json").status_code == 403

    respuesta = superusuario.post(f"{url}anulacion/", {"motivo": "Vivienda equivocada"}, format="json")

    assert respuesta.status_code == 200
    anulado = respuesta.json()
    assert anulado["anulado"] is True and anulado["anulacion_motivo"] == "Vivienda equivocada"
    assert anulado["anulado_por"] == "Sonia Gómez" and anulado["anulado_en"] and anulado["abierto"] is False
    assert len(filas(torres)) == 1


def test_anular_pide_motivo_y_no_se_anula_dos_veces(admin, superusuario, apto, duenos):
    url = f"/infracciones/{registrar(admin, apto).json()['id']}/anulacion/"

    assert superusuario.post(url, {"motivo": "  "}, format="json").status_code == 400
    assert superusuario.post(url, {"motivo": "Error"}, format="json").status_code == 200
    assert superusuario.post(url, {"motivo": "Otra vez"}, format="json").status_code == 409


def test_un_registro_anulado_sigue_en_la_lista_y_no_se_puede_cerrar(admin, superusuario, apto, duenos):
    creado = registrar(admin, apto).json()
    superusuario.post(f"/infracciones/{creado['id']}/anulacion/", {"motivo": "Error"}, format="json")

    lista = admin.get("/infracciones/").json()

    assert [(fila["id"], fila["anulado"], fila["anulacion_motivo"]) for fila in lista] == [(creado["id"], True, "Error")]
    assert admin.post(f"/infracciones/{creado['id']}/cierre/", {"comentario": "Tarde"}, format="json").status_code == 409


def test_anular_no_avisa_a_la_vivienda_y_se_audita(admin, superusuario, torres, apto, duenos):
    creado = registrar(admin, apto).json()
    with usar_conjunto(torres.id):
        avisos_antes = Notificacion.objects.count()

    superusuario.post(f"/infracciones/{creado['id']}/anulacion/", {"motivo": "Error"}, format="json")

    with usar_conjunto(torres.id):
        assert Notificacion.objects.count() == avisos_antes
        registro = Registro.objects.get(accion="infraccion.anular")
    assert registro.antes["anulado"] is False and registro.despues["anulado"] is True and registro.despues["motivo"] == "Error"


def test_el_permiso_de_anular_es_sensible_y_solo_lo_tiene_el_superusuario():
    assert "infraccion.anular" in PERMISOS and "infraccion.anular" in PERMISOS_SENSIBLES
    assert "infraccion.anular" in PERMISOS_POR_ROL[Rol.SUPERUSUARIO]
    for rol in (Rol.ADMINISTRACION, Rol.SECRETARIA, Rol.VIGILANCIA, Rol.RESIDENTE):
        assert "infraccion.anular" not in PERMISOS_POR_ROL[rol]


# Quién ve y quién registra


def test_la_secretaria_el_residente_y_vigilancia_no_entran(admin, torres, apto, duenos):
    creado = registrar(admin, apto).json()
    crear_usuario("sec@torres.com", Rol.SECRETARIA, torres)
    crear_usuario("vig@torres.com", Rol.VIGILANCIA, torres)
    clientes = [cliente_para("sec@torres.com"), cliente_para("vig@torres.com"), cliente_para("pedro@torres.com")]

    for cliente in clientes:
        assert cliente.get("/infracciones/").status_code == 403
        assert cliente.get(f"/infracciones/{creado['id']}/").status_code == 403
        assert registrar(cliente, apto).status_code == 403
        assert cliente.post(f"/infracciones/{creado['id']}/cierre/", {"comentario": "x"}, format="json").status_code == 403
        assert cliente.post(f"/infracciones/{creado['id']}/anulacion/", {"motivo": "x"}, format="json").status_code == 403
    assert len(filas(torres)) == 1


def test_la_lista_pone_primero_los_abiertos_y_luego_el_mas_reciente(admin, torres, apto, duenos):
    primero = registrar(admin, apto, "Primero").json()
    segundo = registrar(admin, apto, "Segundo").json()
    tercero = registrar(admin, apto, "Tercero").json()
    admin.post(f"/infracciones/{segundo['id']}/cierre/", {"comentario": "Cerrado"}, format="json")

    lista = admin.get("/infracciones/").json()

    assert [fila["descripcion_hecho"] for fila in lista] == ["Tercero", "Primero", "Segundo"]


def test_un_registro_de_otro_conjunto_no_existe(admin, superusuario, torres, apto, duenos):
    otro = Conjunto.objects.create(nombre="Mirador")
    ajena = crear_usuario("otro@mirador.com", Rol.ADMINISTRACION, otro)
    with usar_conjunto(otro.id):
        unidad = Unidad.objects.create(nombre="Torre 9 – 901")
        registro = RegistroDeInfraccion.objects.create(
            unidad=unidad, descripcion_hecho="Ajeno", fecha_hecho=HOY(), registrado_por=ajena,
            fecha_notificacion=timezone.now(),
        )

    assert admin.get(f"/infracciones/{registro.id}/").status_code == 404
    assert admin.post(f"/infracciones/{registro.id}/cierre/", {"comentario": "x"}, format="json").status_code == 404
    assert superusuario.post(f"/infracciones/{registro.id}/anulacion/", {"motivo": "x"}, format="json").status_code == 404
    assert registrar(admin, unidad).status_code == 400
    assert admin.get("/infracciones/").json() == []


# Lo que no existe


def test_ninguna_ruta_de_infracciones_sanciona_ni_borra():
    rutas = []

    def recorrer(patrones):
        for patron in patrones:
            if isinstance(patron, URLResolver):
                recorrer(patron.url_patterns)
            elif str(patron.callback.__module__).startswith("apps.infracciones"):
                rutas.append((str(patron.pattern), patron.name, patron.callback.cls().allowed_methods))

    recorrer(get_resolver().url_patterns)

    assert sorted(nombre for _, nombre, _ in rutas) == [
        "infraccion-anulacion", "infraccion-cierre", "infraccion-detalle", "infracciones",
    ]
    for ruta, nombre, metodos in rutas:
        assert not [palabra for palabra in ("sancion", "multa", "restric", "borrar", "eliminar") if palabra in ruta + nombre]
        assert not {"DELETE", "PUT", "PATCH"} & {metodo.upper() for metodo in metodos}
