from django.urls import path

from apps.areas.views import AreasView, DesactivarAreaView, DetalleDeAreaView

urlpatterns = [
    path("", AreasView.as_view(), name="areas"),
    path("<uuid:area_id>/", DetalleDeAreaView.as_view(), name="area-detalle"),
    path("<uuid:area_id>/desactivar/", DesactivarAreaView.as_view(), name="area-desactivar"),
]
