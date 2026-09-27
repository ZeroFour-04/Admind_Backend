from django.urls import path

from apps.unidades.views import CerrarVinculoView, DetalleDeUnidadView, UnidadesView, VinculosDeUnidadView

urlpatterns = [
    path("", UnidadesView.as_view(), name="unidades"),
    path("<uuid:unidad_id>/", DetalleDeUnidadView.as_view(), name="unidad-detalle"),
    path("<uuid:unidad_id>/vinculos/", VinculosDeUnidadView.as_view(), name="unidad-vinculos"),
    path(
        "<uuid:unidad_id>/vinculos/<uuid:vinculo_id>/cerrar/",
        CerrarVinculoView.as_view(),
        name="vinculo-cerrar",
    ),
]
