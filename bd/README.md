# bd

Lo que vive en PostgreSQL y no se expresa con modelos de Django. PostgreSQL desde el día 1, nunca SQLite (§7.1).

## Qué va aquí

- Creación de los **dos usuarios de base**: el dueño, que corre las migraciones, y el de aplicación, sin `UPDATE` ni `DELETE` sobre auditoría y sin DDL
- Procedimiento de **respaldo y restauración**, probado al menos una vez antes de cualquier migración destructiva

## Lo que no va

Las FK compuestas, el índice único parcial y los privilegios sobre auditoría. Esos van en migraciones con `RunSQL` dentro de su app, para que viajen con el esquema (§7.1, §7.2).

## Con qué se conecta

- `config/`: la aplicación se conecta con el usuario de aplicación
- `apps/auditoria/`: sus privilegios suponen que estos dos usuarios existen
- `apps/importacion_respaldo/`
- `tests/esquema/`

## Referencias

Maestro §5.4, §5.11, §7.1, §7.2

## Pendiente

- Decidir los dos usuarios y cómo crea `pytest-django` la base de pruebas (§11.5)
- §7.1 pide Docker Compose; hoy la máquina de desarrollo usa PostgreSQL 18 nativo, sin Docker
