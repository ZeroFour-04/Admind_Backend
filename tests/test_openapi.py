import json

from django.test import Client, override_settings


@override_settings(ROOT_URLCONF="config.urls")
def test_documentacion_openapi_es_publica_y_no_abre_la_api():
    cliente = Client()
    schema = cliente.get(
        "/api/schema/",
        HTTP_ACCEPT="application/vnd.oai.openapi+json",
    )
    docs = cliente.get("/api/docs/")
    endpoint_protegido = cliente.get("/notificaciones/")

    assert schema.status_code == 200
    assert docs.status_code == 200
    assert endpoint_protegido.status_code == 401


@override_settings(ROOT_URLCONF="config.urls")
def test_esquema_asigna_tags_por_app_y_documenta_el_token():
    respuesta = Client().get(
        "/api/schema/",
        HTTP_ACCEPT="application/vnd.oai.openapi+json",
    )
    esquema = json.loads(respuesta.content)
    tags = {tag["name"] for tag in esquema["tags"]}
    esquemas_de_seguridad = esquema["components"]["securitySchemes"]

    assert respuesta.status_code == 200
    assert len(tags) == 18
    assert {"Cuentas", "Reportes", "Áreas"} <= tags
    assert "TokenAuth" in esquemas_de_seguridad
    assert esquemas_de_seguridad["TokenAuth"]["name"] == "Authorization"
    assert 'prefix "Token"' in esquemas_de_seguridad["TokenAuth"]["description"]
    assert esquema["paths"]["/notificaciones/"]["get"]["security"] == [{"TokenAuth": []}]
