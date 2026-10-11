"""Pruebas obligatorias del flujo de reserva (maestro §5.1, HU-11, R7).

Corren contra PostgreSQL real: el índice único parcial es quien decide, y en SQLite no existe.
"""
import threading
from datetime import time, timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apps.areas.models import Area
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.reglas.models import Regla
from apps.reservas import servicios
from apps.reservas.models import BLOQUEANTES, EstadoSolicitud, Solicitud
from apps.unidades.models import TipoVinculo, Unidad, VinculoUnidad
from apps.unidades.servicios import unidades_para_solicitar

RESIDENTES = 10
MANANA = timezone.localdate() + timedelta(days=1)
OCHO = time(8)


def residentes_con_area(cantidad):
    """Un conjunto, un área y `cantidad` residentes, cada uno viviendo en su propio apartamento."""
    torres = Conjunto.objects.create(nombre="Torres del Río")
    personas = []
    with usar_conjunto(torres.id):
        salon = Area.objects.create(
            nombre="Salón comunal", hora_apertura=time(8), hora_cierre=time(22), duracion_franja_minutos=240,
            aforo_maximo=50,
        )
        for numero in range(cantidad):
            persona = Persona.objects.create(
                tipo_documento=TipoDocumento.CC, numero_documento=str(1023456789 + numero),
                nombres=f"Residente {numero}", apellidos="Gómez",
            )
            Asignacion.objects.create(persona=persona, rol=Rol.RESIDENTE, conjunto=torres)
            unidad = Unidad.objects.create(nombre=f"Torre 1 – {101 + numero}")
            VinculoUnidad.objects.create(persona=persona, unidad=unidad, tipo=TipoVinculo.ARRENDATARIO, reside=True)
            personas.append(persona)
    return torres, salon, personas


@pytest.mark.django_db(transaction=True)
def test_n_residentes_sobre_la_misma_franja_producen_exactamente_un_bloqueo():
    """También es «la apertura de la ventana con N residentes en el mismo segundo no duplica»:
    todos llegan a la vez, liberados por la misma barrera.
    """
    torres, salon, personas = residentes_con_area(RESIDENTES)
    barrera = threading.Barrier(RESIDENTES)
    resultados = []
    candado = threading.Lock()

    def reservar(persona):
        try:
            # El conjunto activo es un ContextVar: no se hereda del hilo principal.
            with usar_conjunto(torres.id):
                barrera.wait()
                try:
                    servicios.tomar_bloqueo(persona, salon, MANANA, OCHO)
                    resultado = "bloqueo"
                except servicios.FranjaOcupada:
                    resultado = "ocupada"
            with candado:
                resultados.append(resultado)
        finally:
            connection.close()

    hilos = [threading.Thread(target=reservar, args=(persona,)) for persona in personas]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(resultados) == ["bloqueo"] + ["ocupada"] * (RESIDENTES - 1)
    with usar_conjunto(torres.id):
        assert Solicitud.objects.filter(area=salon, fecha=MANANA, hora_inicio=OCHO, estado__in=BLOQUEANTES).count() == 1


@pytest.mark.django_db(transaction=True)
def test_con_una_reserva_al_dia_tres_envios_a_la_vez_dejan_una_sola_apartada():
    """Cada residente tiene su propia franja del mismo día, así que el índice de la franja no decide:
    decide que `enviar` bloquea la fila del área y evalúa un envío después del otro.
    """
    torres, salon, personas = residentes_con_area(3)
    with usar_conjunto(torres.id):
        Regla.objects.create(area=salon, tipo="UNA_RESERVA_POR_DIA", parametros={}, creada_por=personas[0])
        en_tramite = [
            (persona, servicios.tomar_bloqueo(persona, salon, MANANA, time(hora)).id, unidades_para_solicitar(persona).get().id)
            for persona, hora in zip(personas, (8, 12, 16))
        ]
    barrera = threading.Barrier(len(en_tramite))
    resultados = []
    candado = threading.Lock()

    def enviar(persona, solicitud_id, unidad_id):
        try:
            with usar_conjunto(torres.id):
                barrera.wait()
                try:
                    servicios.enviar(persona, solicitud_id, unidad_id=unidad_id, motivo="Cumpleaños", asistentes=20)
                    resultado = "apartada"
                except servicios.IncumpleReglas:
                    resultado = "rechazada"
            with candado:
                resultados.append(resultado)
        finally:
            connection.close()

    hilos = [threading.Thread(target=enviar, args=datos) for datos in en_tramite]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(resultados) == ["apartada", "rechazada", "rechazada"]
    with usar_conjunto(torres.id):
        assert Solicitud.objects.filter(area=salon, fecha=MANANA, estado=EstadoSolicitud.APARTADA).count() == 1


@pytest.mark.django_db
def test_un_bloqueo_vencido_no_bloquea():
    torres, salon, (primera, segunda) = residentes_con_area(2)
    with usar_conjunto(torres.id):
        vencida = servicios.tomar_bloqueo(primera, salon, MANANA, OCHO)
        Solicitud.objects.filter(pk=vencida.pk).update(bloqueo_vence_en=timezone.now() - timedelta(seconds=1))

        nueva = servicios.tomar_bloqueo(segunda, salon, MANANA, OCHO)

        vencida.refresh_from_db()
        assert vencida.estado == EstadoSolicitud.EXPIRADA
        assert nueva.estado == EstadoSolicitud.EN_SOLICITUD


@pytest.mark.django_db
def test_uno_liberado_a_mano_no_expira_dos_veces():
    torres, salon, (persona,) = residentes_con_area(1)
    with usar_conjunto(torres.id):
        solicitud = servicios.tomar_bloqueo(persona, salon, MANANA, OCHO)
        servicios.liberar(persona, solicitud)
        Solicitud.objects.filter(pk=solicitud.pk).update(bloqueo_vence_en=timezone.now() - timedelta(seconds=1))

        primera = servicios.expirar_vencidas()
        segunda = servicios.expirar_vencidas()

        solicitud.refresh_from_db()
        assert (primera, segunda) == (0, 0)
        assert solicitud.estado == EstadoSolicitud.LIBERADA
