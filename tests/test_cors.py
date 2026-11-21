from django.test import Client, override_settings


FRONTEND_ORIGIN = "http://127.0.0.1:8001"
OTHER_ORIGIN = "https://otro-sitio.example"


@override_settings(CORS_ALLOWED_ORIGINS=[FRONTEND_ORIGIN])
def test_preflight_permite_solo_el_origen_del_frontend():
    response = Client().options(
        "/",
        HTTP_ORIGIN=FRONTEND_ORIGIN,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
    )

    assert response["Access-Control-Allow-Origin"] == FRONTEND_ORIGIN
    assert "Access-Control-Allow-Credentials" not in response


@override_settings(CORS_ALLOWED_ORIGINS=[FRONTEND_ORIGIN])
def test_preflight_no_permite_un_origen_ajeno():
    response = Client().options(
        "/",
        HTTP_ORIGIN=OTHER_ORIGIN,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
    )

    assert "Access-Control-Allow-Origin" not in response
