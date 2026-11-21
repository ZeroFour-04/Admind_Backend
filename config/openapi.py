ETIQUETAS_POR_RUTA = (
    ("/api/reportes/", "Reportes"),
    ("/auth/", "Cuentas"),
    ("/conjuntos/", "Conjuntos"),
    ("/unidades/", "Unidades"),
    ("/notificaciones/", "Notificaciones"),
    ("/anuncios/", "Anuncios"),
    ("/areas/", "Áreas"),
    ("/personas/", "Personas"),
    ("/reglas/", "Reglas"),
    ("/reservas/", "Reservas"),
    ("/ingresos/", "Ingresos"),
    ("/parqueaderos/", "Parqueaderos"),
    ("/pagos/", "Pagos"),
    ("/visitantes/", "Visitantes"),
    ("/documentos/", "Documentos"),
    ("/casos/", "Casos"),
    ("/citas/", "Citas"),
    ("/infracciones/", "Infracciones"),
)

TAGS = [
    {"name": nombre, "description": f"Operaciones de {nombre.lower()}."}
    for _, nombre in ETIQUETAS_POR_RUTA
]


def asignar_tags_por_app(result, generator, **kwargs):
    for ruta, operaciones in result.get("paths", {}).items():
        etiqueta = next(
            (nombre for prefijo, nombre in ETIQUETAS_POR_RUTA if ruta.startswith(prefijo)),
            None,
        )
        if etiqueta is None:
            continue
        for operacion in operaciones.values():
            if isinstance(operacion, dict) and "operationId" in operacion:
                operacion["tags"] = [etiqueta]
    return result
