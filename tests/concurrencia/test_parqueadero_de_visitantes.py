"""Prueba obligatoria del último parqueadero de visitantes (HU-28, criterio 5; recurso limitado, R1).

Corre contra PostgreSQL real: no se pregunta si el puesto está libre antes de guardar la visita; el
índice único parcial `visitante_parqueadero_ocupado_unico` acepta a una sola.
"""
import threading

import pytest
from django.db import connection

from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.parqueaderos.models import Parqueadero
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.unidades.models import Unidad
from apps.visitantes import servicios
from apps.visitantes.models import Visitante

VIGILANTES = 10


def conjunto_con_un_puesto():
    """Un conjunto, un vigilante, un apartamento visitado y un solo parqueadero de visitantes."""
    torres = Conjunto.objects.create(nombre="Torres del Río")
    vigilante = Persona.objects.create(
        tipo_documento=TipoDocumento.CC, numero_documento="900000001", nombres="Vigilante", apellidos="Gómez"
    )
    Asignacion.objects.create(persona=vigilante, rol=Rol.VIGILANCIA, conjunto=torres)
    with usar_conjunto(torres.id):
        unidad = Unidad.objects.create(nombre="Torre 1 – 101")
        puesto = Parqueadero.objects.create(codigo="V-01", tipo="visitantes", creado_por=vigilante)
    return torres, vigilante, unidad, puesto


@pytest.mark.django_db(transaction=True)
def test_n_registros_a_la_vez_sobre_el_mismo_puesto_dejan_a_una_sola_visita_con_el_parqueadero():
    torres, vigilante, unidad, puesto = conjunto_con_un_puesto()
    barrera = threading.Barrier(VIGILANTES)
    resultados = []
    candado = threading.Lock()

    def registrar(numero):
        try:
            # El conjunto activo es un ContextVar: no se hereda del hilo principal.
            with usar_conjunto(torres.id):
                barrera.wait()
                try:
                    servicios.registrar_ingreso(
                        vigilante,
                        torres.id,
                        nombre=f"Visitante {numero}",
                        cedula=str(1000 + numero),
                        placa_vehiculo=f"ABC{numero:03d}",
                        tipo_vehiculo="Auto",
                        unidad_id=unidad.id,
                        parqueadero_id=puesto.id,
                    )
                    resultado = "ocupo"
                except servicios.ParqueaderoOcupado:
                    resultado = "ocupado"
            with candado:
                resultados.append(resultado)
        finally:
            connection.close()

    hilos = [threading.Thread(target=registrar, args=(numero,)) for numero in range(VIGILANTES)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(resultados) == ["ocupado"] * (VIGILANTES - 1) + ["ocupo"]
    with usar_conjunto(torres.id):
        # Los nueve rechazados no dejaron fila: una sola visita, y es la del puesto.
        assert Visitante.objects.count() == 1
        assert Visitante.objects.filter(parqueadero=puesto, hora_salida__isnull=True).count() == 1

