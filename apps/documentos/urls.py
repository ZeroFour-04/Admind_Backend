from django.urls import path

from apps.documentos.views import ArchivoDelReglamentoView, ReglamentoView

urlpatterns = [
    path("reglamento/", ReglamentoView.as_view(), name="reglamento"),
    path("reglamento/archivo/", ArchivoDelReglamentoView.as_view(), name="reglamento-archivo"),
]
