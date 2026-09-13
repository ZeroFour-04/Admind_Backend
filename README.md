# Admind_Backend

API de AdMind: Django 5.2 LTS + Django REST Framework + PostgreSQL (maestro §7.1). Es el único servidor que toca la base de datos. El frontend (`Admind_Front-End`) le pide todo por HTTP.

> [!NOTE]
> Por ahora este repositorio solo tiene carpetas y un `README.md` en cada una, que dice qué va a vivir ahí y con qué se conecta. Todavía no hay código.

## Mapa

| Carpeta | Qué va |
|---|---|
| `config/` | Proyecto Django: ajustes, URLs raíz, arranque del servidor |
| `apps/` | Una app de Django por módulo del producto |
| `apps/comun/` | Mecanismos compartidos: aislamiento por conjunto, bloqueo, modelos base |
| `bd/` | Lo que vive en PostgreSQL y no en Django: usuarios de base, respaldo |
| `tests/` | Pruebas transversales: intruso, esquema, concurrencia |

## Módulos

**Núcleo (§3.1):** `cuentas`, `conjuntos`, `personas`, `permisos`, `unidades`, `areas`, `reglas`, `reservas`, `notificaciones`, `auditoria`.

**Comprometido (§3.2), puede quedar parcial:** `visitantes`, `casos`, `infracciones`, `citas`, `triage`, `anuncios`, `documentos`, `parqueaderos`, `pagos`, `importacion_respaldo`.

Lo condicional (§3.3) no tiene carpeta. Se crea si llega a entrar.

## Reglas que aplican a todas las carpetas

- `conjunto_id NOT NULL` en toda tabla, salvo la lista cerrada de tablas globales (§5.4, R12)
- Ninguna vista acepta `conjunto_id` como parámetro: el conjunto activo sale de la sesión (§5.4)
- Sin borrado físico y ninguna FK con `ON DELETE CASCADE` (§5.11)
- Commits sobre `desarrollo` con el ID de la historia: `feat(reservas): agregar bloqueo de 3 minutos [HU-11]` (§8.4, §8.5)

## Documentación

La fuente de verdad es `Admin_Master.md`, en el repositorio de documentación. Si un README de aquí lo contradice, manda el maestro.
