"""Prueba obligatoria del último cupo de una zona con ingreso (plan de zonas con ingreso, P9).

Corre contra PostgreSQL real: el aforo es una suma y lo decide la fila del área tomada con `select_for_update`.
"""
import threading
from datetime import datetime, time

import pytest
from django.db import connection
from django.utils import timezone

from apps.areas.models import Area
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.ingresos import servicios
from apps.ingresos.models import EstadoIngreso, Ingreso
from apps.personas.models import Persona, TipoDocumento
from apps.unidades.models import TipoVinculo, Unidad, VinculoUnidad

RESIDENTES = 10
AHORA = timezone.make_aware(datetime.combine(timezone.localdate(), time(10)))


def residentes_con_gimnasio(cantidad, aforo):
    """Un conjunto, una zona con ingreso de `aforo` puestos y `cantidad` residentes, cada uno en su vivienda."""
    torres = Conjunto.objects.create(nombre="Torres del Río")
    vigilante = Persona.objects.create(
        tipo_documento=TipoDocumento.CC, numero_documento="900000001", nombres="Vigilante", apellidos="Gómez"
    )
    parejas = []
    with usar_conjunto(torres.id):
        gimnasio = Area.objects.create(
            nombre="Gimnasio",
            modo_uso="ingreso",
            hora_apertura=time(5),
            hora_cierre=time(22),
            permanencia_maxima_minutos=60,
            aforo_maximo=aforo,
        )
        for numero in range(cantidad):
            persona = Persona.objects.create(
                tipo_documento=TipoDocumento.CC,
                numero_documento=str(1023456789 + numero),
                nombres=f"Residente {numero}",
                apellidos="Gómez",
            )
            unidad = Unidad.objects.create(nombre=f"Torre 1 – {101 + numero}")
            VinculoUnidad.objects.create(persona=persona, unidad=unidad, tipo=TipoVinculo.ARRENDATARIO, reside=True)
            parejas.append((persona, unidad))
    return torres, vigilante, gimnasio, parejas


@pytest.mark.django_db(transaction=True)
def test_n_registros_a_la_vez_sobre_el_ultimo_cupo_dejan_uno_solo_adentro():
    torres, vigilante, gimnasio, parejas = residentes_con_gimnasio(RESIDENTES, aforo=1)
    barrera = threading.Barrier(RESIDENTES)
    resultados = []
    candado = threading.Lock()

    def registrar(persona, unidad):
        try:
            # El conjunto activo es un ContextVar: no se hereda del hilo principal.
            with usar_conjunto(torres.id):
                barrera.wait()
                try:
                    servicios.registrar(vigilante, gimnasio.id, persona.id, unidad.id, 0, ahora=AHORA)
                    resultado = "entro"
                except servicios.IncumpleReglas:
                    resultado = "sin_cupo"
            with candado:
                resultados.append(resultado)
        finally:
            connection.close()

    hilos = [threading.Thread(target=registrar, args=pareja) for pareja in parejas]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(resultados) == ["entro"] + ["sin_cupo"] * (RESIDENTES - 1)
    with usar_conjunto(torres.id):
        assert Ingreso.objects.filter(estado=EstadoIngreso.ADENTRO).count() == 1
        assert servicios.ocupacion(gimnasio) == 1


@pytest.mark.django_db(transaction=True)
def test_la_misma_persona_en_dos_zonas_a_la_vez_queda_adentro_de_una_sola():
    torres, vigilante, gimnasio, parejas = residentes_con_gimnasio(1, aforo=5)
    with usar_conjunto(torres.id):
        piscina = Area.objects.create(
            nombre="Piscina",
            modo_uso="ingreso",
            hora_apertura=time(5),
            hora_cierre=time(22),
            permanencia_maxima_minutos=60,
            aforo_maximo=5,
        )
    persona, unidad = parejas[0]
    barrera = threading.Barrier(2)
    resultados = []
    candado = threading.Lock()

    def registrar(area):
        try:
            with usar_conjunto(torres.id):
                barrera.wait()
                try:
                    servicios.registrar(vigilante, area.id, persona.id, unidad.id, 0, ahora=AHORA)
                    resultado = "entro"
                except servicios.IncumpleReglas:
                    resultado = "rechazado"
            with candado:
                resultados.append(resultado)
        finally:
            connection.close()

    hilos = [threading.Thread(target=registrar, args=(area,)) for area in (gimnasio, piscina)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(resultados) == ["entro", "rechazado"]
    with usar_conjunto(torres.id):
        assert Ingreso.objects.filter(estado=EstadoIngreso.ADENTRO).count() == 1
