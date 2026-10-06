"""Pruebas del generador de la estructura de viviendas (HU-39). No usan la base: son funciones puras."""
import pytest

from apps.unidades.estructura import clave, generar, limpiar

SEIS_TORRES = {
    "tipo_vivienda": "apartamento",
    "etiqueta": "torre",
    "patron": "piso_consecutivo",
    "agrupaciones": [{"nombre": str(numero), "pisos": 10, "por_piso": 4} for numero in range(1, 7)],
}
DOS_MANZANAS = {
    "tipo_vivienda": "casa",
    "etiqueta": "Manzana",
    "agrupaciones": [{"nombre": "A", "cantidad": 10}, {"nombre": "B", "cantidad": 15}],
}


def total(agrupaciones):
    return sum(len(agrupacion.viviendas) for agrupacion in agrupaciones)


@pytest.mark.parametrize(
    ("texto", "esperado"), [("  torre ", "Torre"), ("Súper   manzana", "Súper manzana"), ("", "")]
)
def test_limpiar_quita_espacios_y_pone_la_primera_mayuscula(texto, esperado):
    assert limpiar(texto) == esperado


@pytest.mark.parametrize(("uno", "otro"), [("Torre Ágata", "torre agata"), ("TORRE  1", "torre 1")])
def test_la_clave_no_distingue_tildes_ni_mayusculas(uno, otro):
    assert clave(uno) == clave(otro)


def test_seis_torres_de_diez_pisos_con_cuatro_por_piso_son_240_apartamentos():
    torres = generar(SEIS_TORRES)

    assert [torre.nombre_completo for torre in torres] == [f"Torre {numero}" for numero in range(1, 7)]
    assert total(torres) == 240
    assert torres[0].viviendas[0].nombre == "Torre 1 – Apto 101"
    assert torres[5].viviendas[-1].nombre == "Torre 6 – Apto 1004"
    assert torres[0].viviendas[4].piso == 2


def test_con_consecutivo_cada_manzana_vuelve_a_empezar_en_uno():
    manzanas = generar({**DOS_MANZANAS, "patron": "consecutivo"})

    assert manzanas[0].viviendas[0].nombre == "Manzana A – Casa 1"
    assert manzanas[1].viviendas[0].nombre == "Manzana B – Casa 1"
    assert manzanas[1].viviendas[-1].nombre == "Manzana B – Casa 15"
    assert total(manzanas) == 25


def test_con_corrido_la_numeracion_sigue_de_una_manzana_a_la_siguiente():
    manzanas = generar({**DOS_MANZANAS, "patron": "corrido"})

    assert manzanas[0].viviendas[0].nombre == "Manzana A – Casa 1"
    assert manzanas[1].viviendas[0].nombre == "Manzana B – Casa 11"
    assert manzanas[1].viviendas[-1].nombre == "Manzana B – Casa 25"
    assert total(manzanas) == 25


def test_con_lista_los_numeros_son_los_que_se_escriben():
    descripcion = {
        "tipo_vivienda": "apartamento",
        "etiqueta": "Torre",
        "patron": "lista",
        "numeros": ["1", "2", "ph"],
        "agrupaciones": [{"nombre": "1"}],
    }

    (torre,) = generar(descripcion)

    assert torre.viviendas[0].nombre == "Torre 1 – Apto 1"
    assert torre.viviendas[-1].nombre == "Torre 1 – Apto Ph"
    assert total([torre]) == 3


def test_sin_agrupacion_las_casas_solo_llevan_su_numero():
    descripcion = {
        "tipo_vivienda": "casa",
        "etiqueta": "",
        "patron": "consecutivo",
        "agrupaciones": [{"nombre": "", "cantidad": 120}],
    }

    (grupo,) = generar(descripcion)

    assert grupo.nombre_completo == ""
    assert grupo.viviendas[0].nombre == "Casa 1"
    assert grupo.viviendas[-1].nombre == "Casa 120"
    assert total([grupo]) == 120


def test_el_primer_piso_puede_no_tener_apartamentos():
    descripcion = {
        "tipo_vivienda": "apartamento",
        "etiqueta": "Torre",
        "patron": "piso_consecutivo",
        "primer_piso": 2,
        "agrupaciones": [{"nombre": "1", "pisos": 3, "por_piso": 2}],
    }

    (torre,) = generar(descripcion)

    assert torre.viviendas[0].nombre == "Torre 1 – Apto 201"
    assert torre.viviendas[-1].nombre == "Torre 1 – Apto 402"
    assert total([torre]) == 6
