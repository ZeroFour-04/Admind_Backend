"""Cómo sale cada fila de pagos. Ni la cédula ni el contenido del archivo salen de aquí (plan P8)."""
from rest_framework import serializers

from apps.pagos import periodos
from apps.pagos.servicios import estado_de

_FECHA = serializers.DateTimeField()


def _fecha(valor):
    """Una fecha con hora como la escribe `DateTimeField`, para los campos que arma una función."""
    return _FECHA.to_representation(valor) if valor else None


def _nombre(persona):
    return f"{persona.nombres} {persona.apellidos}" if persona else None


def _comprobante_vigente(pago):
    """El más reciente, sin su contenido; `None` si el pago no tiene ninguno (plan P5)."""
    cargados = getattr(pago, "comprobantes_cargados", None) or []
    if not cargados:
        return None
    comprobante = cargados[0]  # vienen del más reciente al más antiguo
    return {"id": comprobante.id, "nombre": comprobante.nombre, "subido_en": _fecha(comprobante.subido_en)}


def datos_del_pago(pago):
    """Lo que se sabe del pago de un mes, con la forma que comparten la tabla y «Mis pagos»."""
    return {
        "estado": estado_de(pago),
        "reportado_por": _nombre(pago.reportado_por) if pago else None,
        "reportado_en": _fecha(pago.reportado_en) if pago else None,
        "confirmado_por": _nombre(pago.confirmado_por) if pago else None,
        "confirmado_en": _fecha(pago.confirmado_en) if pago else None,
        "comprobante": _comprobante_vigente(pago) if pago else None,
    }


def fila_de_gestion(fila):
    """Una vivienda con quién tiene vínculo vigente (nombre y tipo, sin documento) y el pago de su mes."""
    unidad = fila["unidad"]
    return {
        "unidad": {"id": unidad.id, "nombre": unidad.nombre},
        "personas": [
            {"nombre": _nombre(vinculo.persona), "tipo": vinculo.tipo}
            for vinculo in getattr(unidad, "vinculos_de_hoy", [])
        ],
        **datos_del_pago(fila["pago"]),
    }


def vivienda_del_residente(vivienda):
    return {
        "unidad": {"id": vivienda["unidad"].id, "nombre": vivienda["unidad"].nombre},
        "periodos": [
            {"periodo": periodos.texto_de(item["periodo"]), **datos_del_pago(item["pago"])}
            for item in vivienda["periodos"]
        ],
    }


class ConsultarPagosSerializer(serializers.Serializer):
    periodo = serializers.CharField(required=False, allow_blank=True, default="")
    buscar = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")


class ConfirmacionSerializer(serializers.Serializer):
    confirmado = serializers.BooleanField()


class ReportarPagoSerializer(serializers.Serializer):
    unidad = serializers.UUIDField()
    periodo = serializers.CharField()
    archivo = serializers.FileField()
