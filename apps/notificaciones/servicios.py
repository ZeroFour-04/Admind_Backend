"""La bandeja de notificaciones. No sabe nada de HTTP."""
from apps.notificaciones.models import Notificacion

LIMITE_DE_LA_BANDEJA = 100


def bandeja(persona):
    """Los avisos más recientes de la persona en el conjunto activo."""
    return Notificacion.objects.filter(persona=persona).order_by("-creada_en")[:LIMITE_DE_LA_BANDEJA]
