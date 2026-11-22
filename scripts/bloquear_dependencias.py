"""Genera requirements.lock: las versiones de requirements.txt con el hash SHA-256 de cada wheel publicada en PyPI.

El CI instala desde este archivo con `--require-hashes --only-binary :all:` (reglas de Sonar
githubactions:S8544 y S8541): pip solo acepta un archivo si su hash está en la lista, así que un
paquete cambiado en PyPI no entra, y como solo instala wheels nunca ejecuta el `setup.py` de nadie.

requirements.txt sigue siendo el archivo que se edita; tiene que traer también las dependencias de
las dependencias, con su versión fija (si falta una, el CI falla en «Install dependencies»).

Uso, desde la raíz del repositorio:
    python scripts/bloquear_dependencias.py          regenera requirements.lock (consulta PyPI)
    python scripts/bloquear_dependencias.py --check  falla si el lock no coincide con requirements.txt (sin red)
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REQUISITOS = RAIZ / "requirements.txt"
LOCK = RAIZ / "requirements.lock"
ENCABEZADO = "# Generado por scripts/bloquear_dependencias.py desde requirements.txt. No editar a mano.\n"


def normalizar(nombre):
    return re.sub(r"[-_.]+", "-", nombre).lower()


def leer_fijados(ruta):
    """Devuelve {nombre normalizado: (nombre, versión)} de las líneas `paquete==versión`."""
    fijados = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.split("#")[0].strip().rstrip("\\").strip()
        if not linea or linea.startswith("--"):
            continue
        if "==" not in linea:
            sys.exit(f"{ruta.name}: «{linea}» no tiene versión fija (paquete==versión).")
        nombre, version = (parte.strip() for parte in linea.split("==", 1))
        fijados[normalizar(nombre)] = (nombre, version)
    return fijados


def hashes_de_wheels(nombre, version):
    url = f"https://pypi.org/pypi/{nombre}/{version}/json"
    with urllib.request.urlopen(url, timeout=30) as respuesta:
        datos = json.load(respuesta)
    hashes = sorted(
        archivo["digests"]["sha256"]
        for archivo in datos["urls"]
        if archivo["packagetype"] == "bdist_wheel" and not archivo.get("yanked")
    )
    if not hashes:
        sys.exit(f"{nombre}=={version} no publica wheels: no se puede instalar con --only-binary :all:.")
    return hashes


def generar():
    bloques = []
    for _, (nombre, version) in sorted(leer_fijados(REQUISITOS).items()):
        hashes = hashes_de_wheels(nombre, version)
        lineas = [f"{nombre}=={version}"] + [f"    --hash=sha256:{h}" for h in hashes]
        bloques.append(" \\\n".join(lineas))
        print(f"{nombre}=={version}: {len(hashes)} wheels")
    LOCK.write_text(ENCABEZADO + "\n".join(bloques) + "\n", encoding="utf-8")


def comprobar():
    if not LOCK.exists():
        sys.exit("Falta requirements.lock: corre python scripts/bloquear_dependencias.py")
    pedidos = {k: v[1] for k, v in leer_fijados(REQUISITOS).items()}
    bloqueados = {k: v[1] for k, v in leer_fijados(LOCK).items()}
    if pedidos != bloqueados:
        distintos = sorted(set(pedidos.items()) ^ set(bloqueados.items()))
        sys.exit(
            "requirements.lock no coincide con requirements.txt "
            f"({', '.join(f'{n}=={v}' for n, v in distintos)}). "
            "Corre python scripts/bloquear_dependencias.py y súbelo."
        )
    print("requirements.lock coincide con requirements.txt.")


if __name__ == "__main__":
    comprobar() if "--check" in sys.argv else generar()
