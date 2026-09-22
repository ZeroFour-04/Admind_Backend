from django.urls import path

from apps.unidades.views import UnidadesView

urlpatterns = [
    path("", UnidadesView.as_view(), name="unidades"),
]
