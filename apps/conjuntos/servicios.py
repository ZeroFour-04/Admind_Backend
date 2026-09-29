"""Asistente de creación de conjuntos (HU-03). No sabe nada de HTTP: eso es de las vistas.

El asistente guarda cada paso apenas se completa, así que un conjunto a medio configurar ya
existe en la base, pero no queda operativo hasta cumplir todos los requisitos.
"""
import hashlib
from dataclasses import asdict, dataclass

from django.db import transaction

from apps.areas.models import Area
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.imagenes import dimensiones
from apps.conjuntos.models import Conjunto, LogoDeConjunto
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.permisos.servicios import conjuntos_disponibles, es_superusuario
from apps.reglas.models import Regla

TAMANO_MAXIMO_LOGO = 512 * 1024  # bytes

# Los primeros bytes de cada formato admitido. SVG no entra: puede llevar código adentro.
FIRMAS_DE_IMAGEN = {
    "image/png": lambda inicio: inicio.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": lambda inicio: inicio.startswith(b"\xff\xd8\xff"),
    "image/webp": lambda inicio: inicio[:4] == b"RIFF" and inicio[8:12] == b"WEBP",
}


class ConjuntoIncompleto(Exception):
    """El conjunto no cumple los mínimos para quedar operativo."""

    def __init__(self, faltantes):
        super().__init__(faltantes)
        self.faltantes = faltantes


class LogoInvalido(Exception):
    """El archivo no sirve como logo. Trae el mensaje para quien lo subió."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


@dataclass(frozen=True)
class Requisito:
    clave: str
    descripcion: str
    cumplido: bool
    # Falso mientras el módulo que lo cumple no esté construido.
    disponible: bool = True

    def como_dict(self):
        return asdict(self)


def crear_conjunto(persona, nombre, direccion="", acento=None, color_personalizado=""):
    """Paso 1 del asistente: los datos básicos. El conjunto nace activo y no operativo.

    Quien lo crea desde un rol de conjunto queda como su Administración: así el conjunto no nace
    sin gobierno y quien lo creó puede terminar el asistente. El Superusuario no, porque no opera
    dentro de los conjuntos (maestro §5.3): le asigna un administrador en el paso 2.
    """
    datos = {"nombre": nombre, "direccion": direccion}
    if acento:
        datos["acento"] = acento
        datos["color_personalizado"] = color_personalizado
    with transaction.atomic():
        conjunto = Conjunto.objects.create(**datos)
        if not es_superusuario(persona):
            Asignacion.objects.create(persona=persona, rol=Rol.ADMINISTRACION, conjunto=conjunto)
    return conjunto


def editar_datos(conjunto, **datos):
    for campo, valor in datos.items():
        setattr(conjunto, campo, valor)
    conjunto.save(update_fields=list(datos))
    return conjunto


def administradores(conjunto):
    """Personas con rol Administración vigente en el conjunto."""
    return (
        Asignacion.objects.vigentes()
        .filter(conjunto=conjunto, rol=Rol.ADMINISTRACION)
        .select_related("persona")
        .order_by("persona__apellidos", "persona__nombres")
    )


def requisitos_para_operar(conjunto):
    """Lo que el maestro §3.1 exige antes de dejar operativo un conjunto.

    El reglamento todavía no tiene módulo (HU-33). Mientras no exista cuenta como no cumplido, así
    que ningún conjunto puede quedar operativo: el invariante se mantiene aunque el asistente esté
    incompleto. Las áreas se cumplen con al menos una activa (HU-09) y las reglas beta, con al
    menos una vigente (HU-10).
    """
    return [
        Requisito(
            "datos_basicos",
            "Datos básicos: nombre y dirección",
            bool(conjunto.nombre.strip() and conjunto.direccion.strip()),
        ),
        Requisito(
            "administracion",
            "Al menos una persona con rol Administración",
            administradores(conjunto).exists(),
        ),
        Requisito("areas", "Catálogo de áreas comunes", Area.objects.filter(activo=True).exists()),
        Requisito("reglamento", "Reglamento cargado", False, disponible=False),
        Requisito("reglas_beta", "Reglas beta de reserva", Regla.objects.vigentes().exists()),
    ]


def activar(conjunto):
    faltantes = [requisito for requisito in requisitos_para_operar(conjunto) if not requisito.cumplido]
    if faltantes:
        raise ConjuntoIncompleto(faltantes)
    conjunto.operativo = True
    conjunto.save(update_fields=["operativo"])
    return conjunto


# Foto del conjunto (HU-21), guardada como su logo. Es cuadrada (1:1): el navegador la recorta
# antes de subirla y aquí se comprueba. El color no pasa por aquí.


def tipo_real_de_imagen(contenido):
    """El formato según la firma del archivo, o None si no es PNG, JPG ni WebP.

    El nombre y el tipo que manda el navegador no cuentan: un texto renombrado a .png se rechaza.
    """
    for tipo, tiene_la_firma in FIRMAS_DE_IMAGEN.items():
        if tiene_la_firma(contenido[:12]):
            return tipo
    return None


def guardar_logo(conjunto, contenido):
    """Guarda o reemplaza la foto del conjunto activo. La huella cambia con la imagen."""
    if not contenido:
        raise LogoInvalido("El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO_LOGO:
        raise LogoInvalido(f"La foto no puede pesar más de {TAMANO_MAXIMO_LOGO // 1024} KB.")
    tipo = tipo_real_de_imagen(contenido)
    if tipo is None:
        raise LogoInvalido("El archivo no es una imagen PNG, JPG o WebP.")
    tamano = dimensiones(contenido, tipo)
    if tamano is None:
        raise LogoInvalido("No se pudo leer el tamaño de la imagen.")
    ancho, alto = tamano
    if ancho != alto:
        raise LogoInvalido(f"La foto debe ser cuadrada (1:1). Esta mide {ancho} × {alto} px.")
    with transaction.atomic():
        LogoDeConjunto.objects.update_or_create(conjunto=conjunto, defaults={"contenido": contenido, "tipo": tipo})
        conjunto.logo_huella = hashlib.sha256(contenido).hexdigest()
        conjunto.save(update_fields=["logo_huella"])
    return conjunto


def quitar_logo(conjunto):
    """Sin foto, la interfaz muestra un marcador con las iniciales del conjunto."""
    with transaction.atomic():
        LogoDeConjunto.objects.filter(conjunto=conjunto).delete()
        conjunto.logo_huella = ""
        conjunto.save(update_fields=["logo_huella"])
    return conjunto


def logo_por_huella(persona, huella):
    """El logo con esa huella, si es de un conjunto donde la persona puede operar; si no, None.

    El selector muestra el logo de conjuntos que todavía no son el activo, así que aquí se
    fija a mano el conjunto del logo, después de comprobar que la persona tiene acceso a él.
    """
    conjunto = conjuntos_disponibles(persona).filter(logo_huella=huella).first()
    if conjunto is None:
        return None
    with usar_conjunto(conjunto.id):
        return LogoDeConjunto.objects.filter(conjunto=conjunto).first()
