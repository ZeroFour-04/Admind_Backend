from django.urls import path

from apps.anuncios.views import AnunciosView, DetalleDeAnuncioView

urlpatterns = [
    path("", AnunciosView.as_view(), name="anuncios"),
    path("<uuid:anuncio_id>/", DetalleDeAnuncioView.as_view(), name="anuncio-detalle"),
]
