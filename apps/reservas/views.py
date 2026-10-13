"""Franjas y solicitudes de reserva del conjunto activo (HU-11). Cada vista valida, exige su permiso y llama al servicio."""
from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.areas.models import Area
from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.comun.archivos import comprobantes
from apps.permisos.views import exigir_permiso, tiene_permiso_en_conjunto
from apps.reservas import pago, servicios
from apps.reservas.serializers import (
    CampanaSerializer,
    ConsultarFranjasSerializer,
    DecisionDeSolicitudSerializer,
    DeclararPagoSerializer,
    DescarteDeSolicitudSerializer,
    DetalleDeSolicitudSerializer,
    EnviarSolicitudSerializer,
    FranjaSerializer,
    MarcarDisponibilidadSerializer,
    RetirarPagoSerializer,
    SolicitudSerializer,
    SolicitudParaAdministrarSerializer,
    SubirComprobanteSerializer,
    TomarBloqueoSerializer,
)

MENSAJE_NO_EN_TRAMITE = {"detail": "Esta solicitud ya no está en trámite."}
MENSAJE_YA_DECIDIDA = {"detail": "Solo se pueden decidir solicitudes que estén apartadas."}
EXTENSION_POR_TIPO = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}


def area_del_conjunto(area_id):
    """Un área de otro conjunto, o que no existe, responde 404 sin detalle."""
    area = Area.objects.filter(pk=area_id).first()
    if area is None:
        raise NotFound()
    return area


def solicitud_propia(request, solicitud_id):
    """Solo las propias: la de otra persona o de otro conjunto responde 404."""
    solicitud = servicios.detalle(request.user.persona, solicitud_id)
    if solicitud is None:
        raise NotFound()
    return solicitud


class FranjasView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "reserva.solicitar", "reserva.ver_todas")
        consulta = ConsultarFranjasSerializer(data=request.query_params)
        consulta.is_valid(raise_exception=True)
        area = area_del_conjunto(consulta.validated_data["area"])
        fecha = consulta.validated_data["fecha"]
        franjas = servicios.franjas(request.user.persona, area, fecha)
        return Response(
            {
                "area": {"id": area.id, "nombre": area.nombre},
                "fecha": fecha,
                "franjas": FranjaSerializer(franjas, many=True).data,
            }
        )


class SolicitudesView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "reserva.solicitar", "reserva.ver_todas")
        return Response(SolicitudSerializer(servicios.solicitudes_de(request.user.persona), many=True).data)

    def post(self, request):
        """Toma el bloqueo de la franja: 3 minutos exclusivos para llenar y enviar la solicitud."""
        exigir_permiso(request, "reserva.solicitar")
        datos = TomarBloqueoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        campos = datos.validated_data
        area = area_del_conjunto(campos["area"])
        try:
            solicitud = servicios.tomar_bloqueo(request.user.persona, area, campos["fecha"], campos["hora_inicio"])
        except servicios.AreaSinReserva:
            return Response(
                {"detail": "Esta área no se reserva: el ingreso se registra en portería."},
                status=status.HTTP_409_CONFLICT,
            )
        except servicios.SinUnidadParaSolicitar:
            return Response(
                {"detail": "Para reservar necesitas vivir en un apartamento del conjunto."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except servicios.FranjaInvalida:
            return Response(
                {"hora_inicio": ["Esa franja no está en el horario del área o ya empezó."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except servicios.AreaNoDisponible:
            return Response(
                {"detail": "Esta área no está disponible para reservas en este momento."},
                status=status.HTTP_409_CONFLICT,
            )
        except servicios.FranjaOcupada:
            return Response(
                {"detail": "Otra persona está tramitando esta franja en este momento."},
                status=status.HTTP_409_CONFLICT,
            )
        except servicios.YaTienesUnBloqueo as bloqueo:
            return Response(
                {
                    "detail": "Ya tienes otra solicitud en trámite. Envíala o cancélala antes de tomar otra franja.",
                    "solicitud": bloqueo.solicitud_id,
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(DetalleDeSolicitudSerializer(solicitud).data, status=status.HTTP_201_CREATED)


class MarcarDisponibilidadView(VistaDeConjunto):
    def post(self, request):
        exigir_permiso(request, "reserva.solicitar")
        datos = MarcarDisponibilidadSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        area = area_del_conjunto(datos.validated_data["area"])
        try:
            campana = servicios.activar_campana(
                request.user.persona,
                area,
                datos.validated_data["fecha"],
                datos.validated_data["hora_inicio"],
            )
        except servicios.FranjaInvalida:
            return Response(
                {"hora_inicio": ["Esa franja no está en el horario del área o ya empezó."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(CampanaSerializer(campana).data, status=status.HTTP_201_CREATED)


class SolicitudesDeAreaView(VistaDeConjunto):
    def get(self, request, area_id):
        exigir_permiso(request, "reserva.ver_todas", "reserva.aprobar", "reserva.rechazar")
        area = area_del_conjunto(area_id)
        return Response(
            SolicitudParaAdministrarSerializer(servicios.solicitudes_para_area(area), many=True).data
        )


class BandejaDeSolicitudesView(VistaDeConjunto):
    def get(self, request):
        """La pestaña Reservas del dashboard: Administración y Secretaría. Vigilancia no entra."""
        exigir_permiso(request, "solicitud.bandeja_ver")
        return Response(
            SolicitudParaAdministrarSerializer(servicios.solicitudes_para_bandeja(), many=True).data
        )


class DecidirSolicitudView(VistaDeConjunto):
    def post(self, request, solicitud_id):
        exigir_permiso(request, "reserva.aprobar", "reserva.rechazar")
        datos = DecisionDeSolicitudSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        decision = datos.validated_data["decision"]
        permiso = "reserva.aprobar" if decision == "RESERVADA" else "reserva.rechazar"
        exigir_permiso(request, permiso)
        try:
            solicitud = servicios.decidir_solicitud(
                request.user.persona,
                solicitud_id,
                decision,
                datos.validated_data["motivo"],
                datos.validated_data["categoria"],
            )
        except servicios.SolicitudNoEncontrada:
            raise NotFound()
        except servicios.DecisionNoPermitida:
            return Response(MENSAJE_YA_DECIDIDA, status=status.HTTP_409_CONFLICT)
        return Response(SolicitudParaAdministrarSerializer(solicitud).data)


class DescartarSolicitudView(VistaDeConjunto):
    def post(self, request, solicitud_id):
        """Secretaría descarta por causal formal. No aprueba: esa operación es de Administración."""
        exigir_permiso(request, "solicitud.rechazar_formal")
        datos = DescarteDeSolicitudSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            solicitud = servicios.descartar_solicitud(
                request.user.persona,
                solicitud_id,
                datos.validated_data["causal"],
                datos.validated_data["comentario"],
            )
        except servicios.SolicitudNoEncontrada:
            raise NotFound()
        except servicios.DecisionNoPermitida:
            return Response(MENSAJE_YA_DECIDIDA, status=status.HTTP_409_CONFLICT)
        return Response(SolicitudParaAdministrarSerializer(solicitud).data)


class DetalleDeSolicitudView(VistaDeConjunto):
    def get(self, request, solicitud_id):
        exigir_permiso(request, "reserva.solicitar", "reserva.ver_todas")
        return Response(DetalleDeSolicitudSerializer(solicitud_propia(request, solicitud_id)).data)


class LiberarSolicitudView(VistaDeConjunto):
    def post(self, request, solicitud_id):
        """Soltar el bloqueo a propósito: al cerrar o cancelar el formulario."""
        exigir_permiso(request, "reserva.solicitar")
        solicitud = solicitud_propia(request, solicitud_id)
        try:
            servicios.liberar(request.user.persona, solicitud)
        except servicios.NoEstaEnTramite:
            return Response(MENSAJE_NO_EN_TRAMITE, status=status.HTTP_409_CONFLICT)
        return Response(DetalleDeSolicitudSerializer(solicitud).data)


class EnviarSolicitudView(VistaDeConjunto):
    def post(self, request, solicitud_id):
        """Envía la solicitud: se evalúa contra todas las reglas, pase o no por la pantalla de confirmación."""
        exigir_permiso(request, "reserva.solicitar")
        datos = EnviarSolicitudSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        campos = datos.validated_data
        try:
            solicitud = servicios.enviar(
                request.user.persona,
                solicitud_id,
                unidad_id=campos["unidad"],
                motivo=campos["motivo"],
                asistentes=campos["asistentes"],
                observaciones=campos["observaciones"],
            )
        except servicios.SolicitudNoEncontrada:
            raise NotFound()
        except servicios.UnidadNoEncontrada:
            return Response({"unidad": ["Esa unidad no existe en este conjunto."]}, status=status.HTTP_400_BAD_REQUEST)
        except servicios.BloqueoVencido:
            return Response(
                {"detail": "Se venció el tiempo. La franja quedó libre."}, status=status.HTTP_409_CONFLICT
            )
        except servicios.NoEstaEnTramite:
            return Response(MENSAJE_NO_EN_TRAMITE, status=status.HTTP_409_CONFLICT)
        except servicios.IncumpleReglas as incumple:
            return Response(
                {"detail": "La solicitud no cumple las reglas del conjunto.", "motivos": incumple.motivos},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(DetalleDeSolicitudSerializer(solicitud).data)


def leer_archivo(archivo):
    """`(nombre, contenido)` del archivo subido, o `(None, None)` si no llegó.

    Se lee un byte más del límite: basta para saber que se pasa, sin cargar un archivo enorme.
    """
    if archivo is None:
        return None, None
    return archivo.name, archivo.read(comprobantes.TAMANO_MAXIMO_DE_COMPROBANTE + 1)


def archivo_invalido(error):
    return Response({"archivo": [error.mensaje]}, status=status.HTTP_400_BAD_REQUEST)


def demasiados_comprobantes():
    return Response(
        {"detail": f"Esta solicitud ya tiene {pago.MAXIMO_DE_COMPROBANTES} comprobantes: es el máximo."},
        status=status.HTTP_409_CONFLICT,
    )


class PagoDeSolicitudView(VistaDeConjunto):
    def post(self, request, solicitud_id):
        """Administración declara que recibió el pago, con un comprobante opcional (HU-16). No valida el dinero."""
        exigir_permiso(request, "reserva.declarar_pago")
        datos = DeclararPagoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        nombre, contenido = leer_archivo(datos.validated_data.get("archivo"))
        try:
            solicitud = pago.declarar(request.user.persona, solicitud_id, nombre, contenido)
        except servicios.SolicitudNoEncontrada:
            raise NotFound()
        except comprobantes.ArchivoInvalido as error:
            return archivo_invalido(error)
        except pago.PagoNoPermitido:
            return Response(
                {"detail": "Solo se puede declarar el pago de una solicitud apartada o reservada."},
                status=status.HTTP_409_CONFLICT,
            )
        except pago.PagoYaDeclarado:
            return Response(
                {"detail": "El pago de esta solicitud ya está declarado."}, status=status.HTTP_409_CONFLICT
            )
        except pago.DemasiadosComprobantes:
            return demasiados_comprobantes()
        return Response(SolicitudParaAdministrarSerializer(solicitud).data)


class RetirarPagoDeSolicitudView(VistaDeConjunto):
    def post(self, request, solicitud_id):
        """Administración retira una declaración hecha por error. El motivo es obligatorio y queda auditado."""
        exigir_permiso(request, "reserva.declarar_pago")
        datos = RetirarPagoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            solicitud = pago.retirar_declaracion(request.user.persona, solicitud_id, datos.validated_data["motivo"])
        except servicios.SolicitudNoEncontrada:
            raise NotFound()
        except pago.PagoNoDeclarado:
            return Response(
                {"detail": "El pago de esta solicitud no está declarado."}, status=status.HTTP_409_CONFLICT
            )
        return Response(SolicitudParaAdministrarSerializer(solicitud).data)


class ComprobantesDeSolicitudView(VistaDeConjunto):
    def post(self, request, solicitud_id):
        """El residente sube un comprobante a una solicitud suya. Subirlo no declara el pago."""
        exigir_permiso(request, "reserva.solicitar")
        datos = SubirComprobanteSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        nombre, contenido = leer_archivo(datos.validated_data["archivo"])
        try:
            solicitud = pago.subir_comprobante(request.user.persona, solicitud_id, nombre, contenido)
        except servicios.SolicitudNoEncontrada:
            raise NotFound()
        except comprobantes.ArchivoInvalido as error:
            return archivo_invalido(error)
        except pago.PagoNoPermitido:
            return Response(
                {"detail": "Esta solicitud ya no admite comprobantes."}, status=status.HTTP_409_CONFLICT
            )
        except pago.PagoYaDeclarado:
            return Response(
                {"detail": "El pago ya está declarado por la administración: no se pueden subir más comprobantes."},
                status=status.HTTP_409_CONFLICT,
            )
        except pago.DemasiadosComprobantes:
            return demasiados_comprobantes()
        return Response(DetalleDeSolicitudSerializer(solicitud).data, status=status.HTTP_201_CREATED)


class ComprobanteDeSolicitudView(VistaDeConjunto):
    def get(self, request, comprobante_id):
        """El archivo del comprobante, solo por esta ruta. Quien no puede verlo recibe 404, no 403 (plan P8)."""
        # `reserva.ver_todas` entra para que Vigilancia reciba 404 y no 403: no se le confirma que existe.
        exigir_permiso(
            request, "reserva.solicitar", "reserva.ver_todas", "solicitud.bandeja_ver", "reserva.declarar_pago"
        )
        # Quien entra al dashboard los ve aunque no apruebe: es el caso de Secretaría.
        puede_gestionar = tiene_permiso_en_conjunto(request, "reserva.declarar_pago") or tiene_permiso_en_conjunto(
            request, "solicitud.bandeja_ver"
        )
        comprobante = pago.comprobante_para(request.user.persona, puede_gestionar, comprobante_id)
        if comprobante is None:
            raise NotFound()
        respuesta = HttpResponse(bytes(comprobante.contenido), content_type=comprobante.tipo)
        # El nombre de la cabecera se fabrica aquí: el que escribió quien subió el archivo no viaja en ella.
        extension = EXTENSION_POR_TIPO.get(comprobante.tipo, "bin")
        respuesta["Content-Disposition"] = f'inline; filename="comprobante-{comprobante.huella[:8]}.{extension}"'
        respuesta["X-Content-Type-Options"] = "nosniff"
        return respuesta
