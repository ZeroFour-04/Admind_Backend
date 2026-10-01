# Admind_Backend — router para agentes de IA

API de AdMind: Django 5.2 + Django REST Framework + PostgreSQL. Es el único servidor que toca la base de datos. Rama de trabajo: `desarrollo`.

**La documentación del proyecto no vive en este repositorio.** Vive en el repositorio hermano `Admind_Documentacion`, que en el espacio de trabajo local queda en `../../Documentacion/Admind_Documentacion/`.

Antes de tocar código:

1. Lee su `AGENTS.md` (el router completo, con las reglas que no se saltan) y su `README.md` (el índice).
2. Abre solo las notas que la tarea necesita. Para ubicar código: `02_Arquitectura/mapa_codigo.md`. Antes de crear una tabla o un endpoint: `03_Reglas/invariantes.md`.
3. Lee el `README.md` de la carpeta de este repositorio que vas a tocar.

Comandos (Git Bash, desde esta carpeta):

```bash
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
./.venv/Scripts/python.exe manage.py runserver 8000
```
