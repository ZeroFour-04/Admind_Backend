# scripts

Herramientas del repositorio que no son parte de la aplicación.

- `bloquear_dependencias.py`: genera `requirements.lock` desde `requirements.txt`, con el hash SHA-256 de cada wheel publicada en PyPI. El CI instala desde el lock con `--require-hashes --only-binary :all:`.

## Al cambiar una dependencia

1. Edita `requirements.txt` con la versión fija (`paquete==versión`). Si el paquete trae dependencias nuevas, agrégalas también con su versión.
2. Corre `./.venv/Scripts/python.exe scripts/bloquear_dependencias.py` y sube `requirements.lock` en el mismo commit.
3. Si no lo haces, el paso *Check dependency lock* del CI falla y dice qué no coincide.
