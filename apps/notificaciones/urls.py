from django.urls import path

from apps.notificaciones.views import BandejaView

urlpatterns = [
    path("", BandejaView.as_view(), name="notificaciones"),
]
