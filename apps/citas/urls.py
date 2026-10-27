from django.urls import path

from apps.citas.views import AgendaDeCitasView, CitasDeAdministracionView, HorarioDeAtencionView

urlpatterns = [
    path("horario/", HorarioDeAtencionView.as_view(), name="cita-horario"),
    path("agenda/", AgendaDeCitasView.as_view(), name="cita-agenda"),
    path("bandeja/", CitasDeAdministracionView.as_view(), name="cita-bandeja"),
]
