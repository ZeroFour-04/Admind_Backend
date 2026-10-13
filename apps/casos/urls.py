from django.urls import path

from apps.casos.views import (
    CasosView,
    DescartarCasoView,
    DetalleDeCasoView,
    FotoDeCasoView,
    PriorizarCasoView,
    RechazarCasoView,
    RedirigirCasoView,
    ResponderCasoView,
    TomarCasoView,
)

urlpatterns = [
    path("", CasosView.as_view(), name="casos"),
    path("<uuid:caso_id>/", DetalleDeCasoView.as_view(), name="caso-detalle"),
    path("<uuid:caso_id>/tomar/", TomarCasoView.as_view(), name="caso-tomar"),
    path("<uuid:caso_id>/prioridad/", PriorizarCasoView.as_view(), name="caso-prioridad"),
    path("<uuid:caso_id>/redirigir/", RedirigirCasoView.as_view(), name="caso-redirigir"),
    path("<uuid:caso_id>/descartar/", DescartarCasoView.as_view(), name="caso-descartar"),
    path("<uuid:caso_id>/responder/", ResponderCasoView.as_view(), name="caso-responder"),
    path("<uuid:caso_id>/rechazar/", RechazarCasoView.as_view(), name="caso-rechazar"),
    path("<uuid:caso_id>/fotos/<uuid:foto_id>/", FotoDeCasoView.as_view(), name="caso-foto"),
]
