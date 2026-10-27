from rest_framework import serializers

from apps.reservas import servicios
from apps.reservas.models import CATEGORIAS_DE_FONDO, CAUSALES_DE_FORMA, Campana, CategoriaDeRechazo, ComprobanteDePago
from apps.unidades.servicios import unidades_para_solicitar

_FECHA = serializers.DateTimeField()


def _fecha(valor):
    """Una fecha con hora como la escribe `DateTimeField`, para los campos que arma un método."""
    return _FECHA.to_representation(valor) if valor else None


def _nombre(persona):
    return f"{persona.nombres} {persona.apellidos}"


def _comprobantes_de(solicitud):
    """Los comprobantes sin su contenido: los de `con_comprobantes`, o una consulta que tampoco lo trae."""
    cargados = getattr(solicitud, "comprobantes_cargados", None)
    if cargados is not None:
        return cargados
    return list(
        ComprobanteDePago.objects.filter(solicitud=solicitud)
        .defer("contenido")
        .select_related("subido_por")
        .order_by("subido_en")
    )


class ConsultarFranjasSerializer(serializers.Serializer):
    area = serializers.UUIDField()
    fecha = serializers.DateField()


class FranjaSerializer(serializers.Serializer):
    hora_inicio = serializers.TimeField(format="%H:%M")
    hora_fin = serializers.TimeField(format="%H:%M")
    estado = serializers.CharField()


class CampanaSerializer(serializers.ModelSerializer):
    area = serializers.SerializerMethodField()
    fecha = serializers.DateField()
    hora_inicio = serializers.TimeField(format="%H:%M")
    hora_fin = serializers.TimeField(format="%H:%M")
    activa = serializers.BooleanField()

    class Meta:
        model = Campana
        fields = ("id", "area", "fecha", "hora_inicio", "hora_fin", "activa", "creada_en")

    def get_area(self, campana):
        return {"id": campana.area_id, "nombre": campana.area.nombre}


class TomarBloqueoSerializer(serializers.Serializer):
    area = serializers.UUIDField()
    fecha = serializers.DateField()
    hora_inicio = serializers.TimeField()


class MarcarDisponibilidadSerializer(serializers.Serializer):
    area = serializers.UUIDField()
    fecha = serializers.DateField()
    hora_inicio = serializers.TimeField()


class EnviarSolicitudSerializer(serializers.Serializer):
    unidad = serializers.UUIDField()
    motivo = serializers.CharField(max_length=200)
    asistentes = serializers.IntegerField(min_value=1)
    observaciones = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class DeclararPagoSerializer(serializers.Serializer):
    """El comprobante es opcional al declarar. El tipo y el peso los revisa `comprobantes`, no este campo."""

    archivo = serializers.FileField(required=False)


class SubirComprobanteSerializer(serializers.Serializer):
    archivo = serializers.FileField()


class RetirarPagoSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=1000, trim_whitespace=True)


def _opciones(categorias):
    return [(categoria.value, categoria.label) for categoria in categorias]


class DecisionDeSolicitudSerializer(serializers.Serializer):
    """La decisión de fondo. Qué campo es obligatorio depende de la decisión, y eso se ve en la petición."""

    decision = serializers.ChoiceField(choices=("RESERVADA", "RECHAZADA"))
    motivo = serializers.CharField(max_length=1000, trim_whitespace=True, required=False, allow_blank=True, default="")
    categoria = serializers.ChoiceField(
        choices=_opciones(CATEGORIAS_DE_FONDO), required=False, allow_blank=True, default=""
    )

    def validate(self, datos):
        if datos["decision"] == "RESERVADA":
            if not datos["motivo"]:
                raise serializers.ValidationError({"motivo": ["Escribe el motivo o las condiciones de la aprobación."]})
            datos["categoria"] = ""
        elif not datos["categoria"]:
            raise serializers.ValidationError({"categoria": ["Elige el motivo del rechazo."]})
        elif datos["categoria"] == CategoriaDeRechazo.OTRO and not datos["motivo"]:
            raise serializers.ValidationError({"motivo": ["Con «Otro motivo» hay que escribir cuál."]})
        return datos


class ConsultarBandejaSerializer(serializers.Serializer):
    """Los filtros de la pestaña Reservas (HU-22). Sin prioridad: entre reservas manda el orden de llegada."""

    estado = serializers.ChoiceField(choices=("APARTADA", "RESERVADA", "RECHAZADA"), required=False)
    area = serializers.UUIDField(required=False)
    vivienda = serializers.UUIDField(required=False)
    desde = serializers.DateField(required=False)
    hasta = serializers.DateField(required=False)
    solicitante = serializers.CharField(max_length=80, required=False, allow_blank=True, trim_whitespace=True)

    def validate(self, datos):
        if "desde" in datos and "hasta" in datos and datos["desde"] > datos["hasta"]:
            raise serializers.ValidationError({"hasta": ["La fecha final no puede ser anterior a la inicial."]})
        return datos


class DescarteDeSolicitudSerializer(serializers.Serializer):
    """El descarte de Secretaría: causal de lista cerrada y comentario para el residente, los dos obligatorios."""

    causal = serializers.ChoiceField(choices=_opciones(CAUSALES_DE_FORMA))
    comentario = serializers.CharField(max_length=1000, trim_whitespace=True)


class SolicitudSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    area = serializers.SerializerMethodField()
    fecha = serializers.DateField()
    hora_inicio = serializers.TimeField(format="%H:%M")
    hora_fin = serializers.TimeField(format="%H:%M")
    estado = serializers.CharField()
    estado_nombre = serializers.CharField(source="get_estado_display")
    bloqueo_vence_en = serializers.DateTimeField()
    segundos_restantes = serializers.SerializerMethodField()
    motivo_liberacion = serializers.CharField()
    unidad = serializers.SerializerMethodField()
    motivo = serializers.CharField()
    asistentes = serializers.IntegerField()
    observaciones = serializers.CharField()
    creada_en = serializers.DateTimeField()
    enviada_en = serializers.DateTimeField()
    # Qué reglas se evaluaron y con qué resultado (HU-13, plan P10).
    evaluacion = serializers.JSONField()
    evaluada_en = serializers.DateTimeField()
    motivo_decision = serializers.CharField()
    categoria_rechazo = serializers.CharField()
    categoria_rechazo_nombre = serializers.CharField(source="get_categoria_rechazo_display")
    decidida_en = serializers.DateTimeField(allow_null=True)
    # Aprobada y con la franja ya terminada. No es un estado guardado.
    completada = serializers.SerializerMethodField()
    # Si el pago está declarado y con qué comprobantes. Sin el nombre de quien lo declaró (plan P9).
    pago = serializers.SerializerMethodField()

    def get_pago(self, solicitud):
        return self.pago_de(solicitud, para_gestion=False)

    @staticmethod
    def pago_de(solicitud, para_gestion):
        comprobantes = []
        for comprobante in _comprobantes_de(solicitud):
            item = {
                "id": comprobante.id,
                "nombre": comprobante.nombre,
                "subido_en": _fecha(comprobante.subido_en),
                "del_residente": comprobante.subido_por_id == solicitud.persona_id,
            }
            if para_gestion:
                item["subido_por"] = _nombre(comprobante.subido_por)
            comprobantes.append(item)
        pago = {
            "declarado": solicitud.pago_declarado_por_id is not None,
            "declarado_en": _fecha(solicitud.pago_declarado_en),
            "comprobantes": comprobantes,
        }
        if para_gestion:
            declarante = solicitud.pago_declarado_por
            pago["declarado_por"] = _nombre(declarante) if declarante else None
        return pago

    def get_area(self, solicitud):
        return {
            "id": solicitud.area_id,
            "nombre": solicitud.area.nombre,
            "condiciones_alquiler": solicitud.area.condiciones_alquiler,
        }

    def get_completada(self, solicitud):
        return servicios.completada(solicitud)

    def get_segundos_restantes(self, solicitud):
        return servicios.segundos_restantes(solicitud)

    def get_unidad(self, solicitud):
        return {"id": solicitud.unidad_id, "nombre": solicitud.unidad.nombre} if solicitud.unidad else None


class SolicitudParaAdministrarSerializer(SolicitudSerializer):
    residente = serializers.SerializerMethodField()
    motivo_decision = serializers.CharField()
    decidida_por = serializers.SerializerMethodField()
    decidida_en = serializers.DateTimeField()

    def get_residente(self, solicitud):
        return {
            "id": solicitud.persona_id,
            "nombre": f"{solicitud.persona.nombres} {solicitud.persona.apellidos}",
        }

    def get_pago(self, solicitud):
        # Gestión sí ve quién declaró y quién subió cada comprobante.
        return self.pago_de(solicitud, para_gestion=True)

    def get_decidida_por(self, solicitud):
        if not solicitud.decidida_por:
            return None
        return {
            "id": solicitud.decidida_por_id,
            "nombre": f"{solicitud.decidida_por.nombres} {solicitud.decidida_por.apellidos}",
        }


class DetalleDeSolicitudSerializer(SolicitudSerializer):
    """Con las unidades a cuyo nombre puede solicitar y los avisos del panel, mientras está en trámite."""

    unidades_para_solicitar = serializers.SerializerMethodField()
    avisos = serializers.SerializerMethodField()

    def get_avisos(self, solicitud):
        return servicios.avisos(solicitud)

    def get_unidades_para_solicitar(self, solicitud):
        if solicitud.estado != "EN_SOLICITUD":
            return []
        return [{"id": unidad.id, "nombre": unidad.nombre} for unidad in unidades_para_solicitar(solicitud.persona)]
