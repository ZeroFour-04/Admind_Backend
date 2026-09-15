"""URLs para correr las pruebas: las de siempre más los endpoints de apoyo de tests/aislamiento."""
from django.urls import include, path

from config.urls import urlpatterns as urlpatterns_del_proyecto

urlpatterns = [
    *urlpatterns_del_proyecto,
    path("pruebas/", include("tests.aislamiento.urls")),
]
