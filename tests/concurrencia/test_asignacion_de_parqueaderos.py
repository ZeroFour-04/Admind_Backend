"""Pruebas de concurrencia de la asignación de parqueaderos de residentes (HU-34; recurso limitado, R1).

Corren contra PostgreSQL real. El puesto se bloquea con `select_for_update` y el índice único parcial
`asignacion_parqueadero_vigente_unica` es la última palabra; el tope por vivienda se protege bloqueando
también la vivienda.
"""
import threading

import pytest
from django.db import connection

from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.parqueaderos import servicios
from apps.parqueaderos.models import AsignacionParqueadero, Parqueadero
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.reglas.models import Regla
from apps.unidades.models import Unidad

HILOS = 10


def conjunto_con_administrador():
    torres = Conjunto.objects.create(nombre="Torres del Río")
    admin = Persona.objects.create(
        tipo_documento=TipoDocumento.CC, numero_documento="900000001", nombres="Laura", apellidos="Gómez"
    )
    Asignacion.objects.create(persona=admin, rol=Rol.ADMINISTRACION, conjunto=torres)
    return torres, admin


def correr_a_la_vez(torres, tareas):
    """Lanza cada tarea en su hilo, todas a la vez, y devuelve lo que contestó cada una."""
    barrera = threading.Barrier(len(tareas))
    resultados = []
    candado = threading.Lock()

    def correr(tarea):
        try:
            # El conjunto activo es un ContextVar: no se hereda del hilo principal.
            with usar_conjunto(torres.id):
                barrera.wait()
                try:
                    tarea()
                    resultado = "asigno"
                except (servicios.YaAsignadoAEsaUnidad, servicios.TopeDeVehiculosAlcanzado) as error:
                    resultado = type(error).__name__
            with candado:
                resultados.append(resultado)
        finally:
            connection.close()

    hilos = [threading.Thread(target=correr, args=(tarea,)) for tarea in tareas]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    return resultados


@pytest.mark.django_db(transaction=True)
def test_n_asignaciones_a_la_vez_sobre_un_puesto_libre_dejan_una_sola_vigente():
    torres, admin = conjunto_con_administrador()
    with usar_conjunto(torres.id):
        puesto = Parqueadero.objects.create(codigo="R-01", tipo="residentes", creado_por=admin)
        viviendas = [Unidad.objects.create(nombre=f"Torre 1 – {100 + n}") for n in range(HILOS)]

    resultados = correr_a_la_vez(
        torres, [lambda unidad=unidad: servicios.asignar(admin, puesto.id, unidad.id) for unidad in viviendas]
    )

    # Todas triunfan porque cada una reasigna sobre la anterior, pero nunca quedan dos vigentes.
    assert set(resultados) == {"asigno"}
    with usar_conjunto(torres.id):
        assert AsignacionParqueadero.objects.filter(parqueadero=puesto, vigencia_hasta__isnull=True).count() == 1
        assert AsignacionParqueadero.objects.filter(parqueadero=puesto).count() == HILOS


@pytest.mark.django_db(transaction=True)
def test_n_asignaciones_a_la_vez_a_una_vivienda_respetan_el_tope():
    torres, admin = conjunto_con_administrador()
    with usar_conjunto(torres.id):
        vivienda = Unidad.objects.create(nombre="Torre 1 – 101")
        puestos = [
            Parqueadero.objects.create(codigo=f"R-{n:02d}", tipo="residentes", creado_por=admin) for n in range(HILOS)
        ]
        Regla.objects.create(
            tipo="PARQUEADEROS_POR_VIVIENDA", parametros={"carro": 2, "moto": 0, "bicicleta": 0}, creada_por=admin
        )

    resultados = correr_a_la_vez(
        torres, [lambda puesto=puesto: servicios.asignar(admin, puesto.id, vivienda.id) for puesto in puestos]
    )

    assert sorted(resultados) == ["TopeDeVehiculosAlcanzado"] * (HILOS - 2) + ["asigno"] * 2
    with usar_conjunto(torres.id):
        assert AsignacionParqueadero.objects.filter(unidad=vivienda, vigencia_hasta__isnull=True).count() == 2
