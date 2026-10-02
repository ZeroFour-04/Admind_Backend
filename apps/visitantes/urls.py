from django.urls import path

from apps.visitantes.views import VisitantesView

urlpatterns = [
    path("", VisitantesView.as_view(), name="visitantes"),
]
