from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.areas.models import ModoDeUso, ocupacion_areas
from apps.casos.models import Caso, EstadoCaso, PrioridadCaso, resumen_casos
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.ingresos.models import Ingreso, aforo_actual
from apps.pagos.models import PagoDeAdministracion, estado_pagos
from apps.reservas.models import EstadoSolicitud, Solicitud, expirar_bloqueos_vencidos

pytestmark = pytest.mark.django_db


def crear_solicitud(conjunto, area, persona, unidad, *, estado, inicio, fin, vence):
    with usar_conjunto(conjunto.id):
        return Solicitud.objects.create(
            area=area,
            persona=persona,
            unidad=unidad,
            fecha=date(2026, 11, 16),
            hora_inicio=inicio,
            hora_fin=fin,
            estado=estado,
            bloqueo_vence_en=vence,
        )


def test_fn_ocupacion_areas_suma_solo_reservas_confirmadas_del_conjunto_y_rango(
    conjunto, conjunto_ajeno, persona_factory, unidad_factory, area_factory
):
    persona = persona_factory()
    otra_persona = persona_factory()
    unidad = unidad_factory(conjunto)
    otra_unidad = unidad_factory(conjunto_ajeno)
    area = area_factory(conjunto, "Salón")
    area_sin_reservas = area_factory(conjunto, "Gimnasio")
    area_ajena = area_factory(conjunto_ajeno, "Piscina")
    vence = timezone.now() + timedelta(minutes=3)
    crear_solicitud(
        conjunto,
        area,
        persona,
        unidad,
        estado=EstadoSolicitud.RESERVADA,
        inicio=time(8),
        fin=time(10),
        vence=vence,
    )
    crear_solicitud(
        conjunto,
        area,
        persona_factory(),
        unidad,
        estado=EstadoSolicitud.APARTADA,
        inicio=time(10),
        fin=time(12),
        vence=vence,
    )
    crear_solicitud(
        conjunto_ajeno,
        area_ajena,
        otra_persona,
        otra_unidad,
        estado=EstadoSolicitud.RESERVADA,
        inicio=time(8),
        fin=time(12),
        vence=vence,
    )

    filas = ocupacion_areas(conjunto.id, date(2026, 11, 1), date(2026, 11, 30))

    assert {
        fila["area_id"]: (fila["reservas"], fila["horas_reservadas"])
        for fila in filas
    } == {
        area.id: (1, Decimal("2.00")),
        area_sin_reservas.id: (0, Decimal("0")),
    }


def test_fn_ocupacion_areas_rechaza_un_rango_invalido(conjunto):
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            ocupacion_areas(conjunto.id, date(2026, 11, 17), date(2026, 11, 16))


def test_fn_estado_pagos_devuelve_estado_por_vivienda_y_no_filtra_otro_conjunto(
    conjunto, conjunto_ajeno, unidad_factory, persona_factory
):
    reportante = persona_factory("Reportante")
    confirmante = persona_factory("Confirmante")
    confirmada = unidad_factory(conjunto, "Apto")
    reportada = unidad_factory(conjunto, "Casa")
    sin_reporte = unidad_factory(conjunto, "Torre")
    ajena = unidad_factory(conjunto_ajeno)
    periodo = date(2026, 11, 1)
    with usar_conjunto(conjunto.id):
        PagoDeAdministracion.objects.create(
            unidad=confirmada,
            periodo=periodo,
            reportado_por=reportante,
            reportado_en=timezone.now(),
            confirmado_por=confirmante,
            confirmado_en=timezone.now(),
        )
        PagoDeAdministracion.objects.create(
            unidad=reportada,
            periodo=periodo,
            reportado_por=reportante,
            reportado_en=timezone.now(),
        )
    with usar_conjunto(conjunto_ajeno.id):
        PagoDeAdministracion.objects.create(unidad=ajena, periodo=periodo)

    filas = estado_pagos(conjunto.id, periodo)

    assert {fila["unidad_id"]: fila["estado"] for fila in filas} == {
        confirmada.id: "CONFIRMADO",
        reportada.id: "REPORTADO",
        sin_reporte.id: "SIN_REPORTE",
    }


def test_fn_estado_pagos_rechaza_un_periodo_que_no_empieza_el_dia_uno(conjunto):
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            estado_pagos(conjunto.id, date(2026, 11, 2))


def test_fn_resumen_casos_agrupa_por_estado_y_prioridad_y_aísla_el_conjunto(
    conjunto, conjunto_ajeno, persona_factory
):
    autor = persona_factory()
    with usar_conjunto(conjunto.id):
        Caso.objects.create(titulo="Uno", cuerpo="Detalle", autor=autor)
        Caso.objects.create(
            titulo="Urgente",
            cuerpo="Detalle",
            autor=autor,
            prioridad=PrioridadCaso.URGENTE,
            justificacion_prioridad="Riesgo inmediato",
        )
        Caso.objects.create(titulo="En revisión", cuerpo="Detalle", autor=autor, estado=EstadoCaso.EN_REVISION)
    with usar_conjunto(conjunto_ajeno.id):
        Caso.objects.create(titulo="Ajeno", cuerpo="Detalle", autor=autor)

    filas = resumen_casos(conjunto.id)

    assert filas == [
        {"estado": "ABIERTO", "prioridad": "NORMAL", "total": 1},
        {"estado": "ABIERTO", "prioridad": "URGENTE", "total": 1},
        {"estado": "EN_REVISION", "prioridad": "NORMAL", "total": 1},
    ]


def test_fn_resumen_casos_rechaza_un_conjunto_nulo():
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            resumen_casos(None)


def test_fn_aforo_actual_suma_personas_y_acompanantes_adentro_del_area(
    conjunto, conjunto_ajeno, persona_factory, unidad_factory, area_factory
):
    area = area_factory(conjunto, modo=ModoDeUso.INGRESO)
    area_ajena = area_factory(conjunto_ajeno, modo=ModoDeUso.INGRESO)
    unidad = unidad_factory(conjunto)
    ahora = timezone.now()
    for acompanantes in (1, 2):
        persona = persona_factory()
        with usar_conjunto(conjunto.id):
            Ingreso.objects.create(
                area=area,
                persona=persona,
                unidad=unidad,
                acompanantes=acompanantes,
                entrada_en=ahora,
                salida_prevista_en=ahora + timedelta(hours=1),
                registrado_por=persona,
            )
    persona_ajena = persona_factory()
    unidad_ajena = unidad_factory(conjunto_ajeno)
    with usar_conjunto(conjunto_ajeno.id):
        Ingreso.objects.create(
            area=area_ajena,
            persona=persona_ajena,
            unidad=unidad_ajena,
            acompanantes=5,
            entrada_en=ahora,
            salida_prevista_en=ahora + timedelta(hours=1),
            registrado_por=persona_ajena,
        )

    assert aforo_actual(conjunto.id, area.id) == 5


def test_fn_aforo_actual_rechaza_un_area_ajena(conjunto, conjunto_ajeno, area_factory):
    area_ajena = area_factory(conjunto_ajeno, modo=ModoDeUso.INGRESO)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            aforo_actual(conjunto.id, area_ajena.id)


def test_fn_aforo_actual_conserva_el_conteo_si_el_area_cambia_de_modo(
    conjunto, persona_factory, unidad_factory, area_factory
):
    area = area_factory(conjunto, modo=ModoDeUso.INGRESO)
    persona = persona_factory()
    unidad = unidad_factory(conjunto)
    ahora = timezone.now()
    with usar_conjunto(conjunto.id):
        Ingreso.objects.create(
            area=area,
            persona=persona,
            unidad=unidad,
            acompanantes=1,
            entrada_en=ahora,
            salida_prevista_en=ahora + timedelta(hours=1),
            registrado_por=persona,
        )
        area.modo_uso = ModoDeUso.RESERVA
        area.duracion_franja_minutos = 120
        area.permanencia_maxima_minutos = None
        area.save(update_fields=["modo_uso", "duracion_franja_minutos", "permanencia_maxima_minutos"])

    assert aforo_actual(conjunto.id, area.id) == 2


def test_sp_expirar_bloqueos_cambia_solo_los_vencidos_del_conjunto(
    conjunto, conjunto_ajeno, persona_factory, unidad_factory, area_factory
):
    persona = persona_factory()
    otra_persona = persona_factory()
    area = area_factory(conjunto)
    area_ajena = area_factory(conjunto_ajeno)
    unidad = unidad_factory(conjunto)
    unidad_ajena = unidad_factory(conjunto_ajeno)
    crear_solicitud(
        conjunto,
        area,
        persona,
        unidad,
        estado=EstadoSolicitud.EN_SOLICITUD,
        inicio=time(8),
        fin=time(10),
        vence=timezone.now() - timedelta(seconds=1),
    )
    vigente = crear_solicitud(
        conjunto,
        area,
        persona_factory(),
        unidad,
        estado=EstadoSolicitud.EN_SOLICITUD,
        inicio=time(10),
        fin=time(12),
        vence=timezone.now() + timedelta(minutes=3),
    )
    ajena = crear_solicitud(
        conjunto_ajeno,
        area_ajena,
        otra_persona,
        unidad_ajena,
        estado=EstadoSolicitud.EN_SOLICITUD,
        inicio=time(8),
        fin=time(10),
        vence=timezone.now() - timedelta(seconds=1),
    )

    with usar_conjunto(conjunto.id):
        expirar_bloqueos_vencidos(conjunto.id)
        assert Solicitud.objects.get(pk=vigente.id).estado == EstadoSolicitud.EN_SOLICITUD
        assert Solicitud.objects.filter(estado=EstadoSolicitud.EXPIRADA).count() == 1
    with usar_conjunto(conjunto_ajeno.id):
        assert Solicitud.objects.get(pk=ajena.id).estado == EstadoSolicitud.EN_SOLICITUD


def test_sp_expirar_bloqueos_rechaza_un_conjunto_nulo():
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            expirar_bloqueos_vencidos(None)
