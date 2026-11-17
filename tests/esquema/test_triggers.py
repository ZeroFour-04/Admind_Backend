from datetime import date, time

import pytest
from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.casos.models import Caso
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.infracciones.models import RegistroDeInfraccion
from apps.pagos.models import PagoDeAdministracion
from apps.reservas.models import EstadoSolicitud, Solicitud

pytestmark = pytest.mark.django_db


def test_los_cuatro_triggers_impiden_borrar_fisicamente(
    conjunto, persona_factory, unidad_factory, area_factory
):
    persona = persona_factory()
    unidad = unidad_factory(conjunto)
    area = area_factory(conjunto)
    with usar_conjunto(conjunto.id):
        solicitud = Solicitud.objects.create(
            area=area,
            unidad=unidad,
            persona=persona,
            fecha=date(2026, 11, 16),
            hora_inicio=time(8),
            hora_fin=time(10),
            estado=EstadoSolicitud.EN_SOLICITUD,
            bloqueo_vence_en=timezone.now(),
        )
        pago = PagoDeAdministracion.objects.create(unidad=unidad, periodo=date(2026, 11, 1))
        caso = Caso.objects.create(titulo="Caso", cuerpo="Detalle", autor=persona)
        infraccion = RegistroDeInfraccion.objects.create(
            unidad=unidad,
            descripcion_hecho="Hecho registrado",
            fecha_hecho=date(2026, 11, 15),
            registrado_por=persona,
            fecha_notificacion=timezone.now(),
        )

        for objeto in (solicitud, pago, caso, infraccion):
            with pytest.raises(DatabaseError):
                with transaction.atomic():
                    objeto.delete()

        assert Solicitud.objects.filter(pk=solicitud.pk).exists()
        assert PagoDeAdministracion.objects.filter(pk=pago.pk).exists()
        assert Caso.objects.filter(pk=caso.pk).exists()
        assert RegistroDeInfraccion.objects.filter(pk=infraccion.pk).exists()


def test_el_trigger_solo_impide_actualizar_la_infraccion_si_ya_estaba_anulada(
    conjunto, persona_factory, unidad_factory
):
    persona = persona_factory()
    unidad = unidad_factory(conjunto)
    with usar_conjunto(conjunto.id):
        infraccion = RegistroDeInfraccion.objects.create(
            unidad=unidad,
            descripcion_hecho="Hecho registrado",
            fecha_hecho=date(2026, 11, 15),
            registrado_por=persona,
            fecha_notificacion=timezone.now(),
        )
        RegistroDeInfraccion.objects.filter(pk=infraccion.pk).update(descripcion_hecho="Hecho corregido")
        RegistroDeInfraccion.objects.filter(pk=infraccion.pk).update(
            anulado=True,
            anulacion_motivo="Registro duplicado",
            anulado_por_id=persona.id,
            anulado_en=timezone.now(),
        )

        with pytest.raises(DatabaseError):
            with transaction.atomic():
                RegistroDeInfraccion.objects.filter(pk=infraccion.pk).update(
                    anulacion_motivo="Intento de edición"
                )

        infraccion.refresh_from_db()
        assert infraccion.anulado is True
        assert infraccion.anulacion_motivo == "Registro duplicado"
