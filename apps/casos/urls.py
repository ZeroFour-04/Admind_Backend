from django.urls import path

from apps.casos.views import CasosView, FotoDeCasoView, GestionarCasoView

urlpatterns = [
    path("", CasosView.as_view(), name="casos"),
    path("<uuid:caso_id>/rechazar/", GestionarCasoView.as_view(), {"accion": "rechazar"}, name="caso-rechazar"),
    path("<uuid:caso_id>/redirigir/", GestionarCasoView.as_view(), {"accion": "redirigir"}, name="caso-redirigir"),
    path("<uuid:caso_id>/fotos/<uuid:foto_id>/", FotoDeCasoView.as_view(), name="caso-foto"),
]
