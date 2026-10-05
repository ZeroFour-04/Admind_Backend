from django.urls import path

from apps.anuncios.views import AnunciosView, DetalleDeAnuncioView, FotoDeAnuncioView

urlpatterns = [
    path("", AnunciosView.as_view(), name="anuncios"),
    path("<uuid:anuncio_id>/", DetalleDeAnuncioView.as_view(), name="anuncio-detalle"),
    path("<uuid:anuncio_id>/fotos/<uuid:foto_id>/", FotoDeAnuncioView.as_view(), name="anuncio-foto"),
]
