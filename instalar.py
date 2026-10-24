"""Instalación inicial y arranque de MovieMatch (Python 3.11)."""
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from contextlib import closing
from io import BytesIO
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ENTORNO = RAIZ / ".venv"
PYTHON = ENTORNO / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
REQUISITOS = RAIZ / "requirements.txt"
MARCA = ENTORNO / "requisitos.sha256"
FUENTES = RAIZ / "datos" / "fuentes" / "ml-latest-small"
URL_MOVIELENS = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
HUELLAS = {
    "movies.csv": "5a5f32dd9bb3797b8e728a1b98958789d2b13f294a69fdfbc5727f8a9611aa07",
    "links.csv": "97ad18e4e56a09363c65676b6cb3482ce3e2cea2372a24620c1599c843325f31",
    "ratings.csv": "aa289ca83157595d0df6aea1be6a4ded676ddc4385472e8313a8ed9805352646",
}


def ejecutar(*comando):
    subprocess.run(comando, cwd=RAIZ, check=True)


def preparar_python():
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError("Se necesita Python 3.11. Instálalo y vuelve a ejecutar el instalador.")
    if not PYTHON.is_file():
        print("Creando entorno virtual...")
        ejecutar(sys.executable, "-m", "venv", str(ENTORNO))
    huella = hashlib.sha256(REQUISITOS.read_bytes()).hexdigest()
    if not MARCA.is_file() or MARCA.read_text(encoding="utf-8").strip() != huella:
        print("Instalando dependencias de Python...")
        ejecutar(str(PYTHON), "-m", "pip", "install", "-r", str(REQUISITOS))
        MARCA.write_text(huella + "\n", encoding="utf-8")


def comprobar_docker():
    if not shutil.which("docker"):
        raise RuntimeError("Instala Docker Desktop, ábrelo y repite la instalación.")
    prueba = subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, check=False)
    if prueba.returncode:
        raise RuntimeError("Docker Desktop está instalado, pero su motor no está iniciado.")


def comprobar_movielens():
    faltan = []
    for nombre, huella in HUELLAS.items():
        archivo = FUENTES / nombre
        if not archivo.is_file():
            faltan.append(nombre)
        elif hashlib.sha256(archivo.read_bytes()).hexdigest() != huella:
            raise RuntimeError(f"El archivo {archivo} no coincide con MovieLens 2018. Revísalo.")
    if not faltan:
        print("MovieLens ya está preparado.")
        return

    print("Descargando MovieLens Latest Small...")
    peticion = urllib.request.Request(URL_MOVIELENS, headers={"User-Agent": "MovieMatch/1.0"})
    with urllib.request.urlopen(peticion, timeout=120) as respuesta:
        contenido = respuesta.read()
    with zipfile.ZipFile(BytesIO(contenido)) as comprimido:
        # Extraemos únicamente los tres CSV que utiliza el ETL.
        archivos = {}
        for nombre in faltan:
            datos = comprimido.read("ml-latest-small/" + nombre)
            if hashlib.sha256(datos).hexdigest() != HUELLAS[nombre]:
                raise RuntimeError(f"No coincide la huella SHA-256 de {nombre}.")
            archivos[nombre] = datos
    FUENTES.mkdir(parents=True, exist_ok=True)
    for nombre, datos in archivos.items():
        (FUENTES / nombre).write_bytes(datos)


def qdrant_listo():
    from qdrant_client import models
    from src.motor import COLECCION, DIMENSION, cliente

    try:
        with closing(cliente()) as db:
            if not db.collection_exists(COLECCION):
                return False
            info = db.get_collection(COLECCION)
            vector = info.config.params.vectors
            return (isinstance(vector, models.VectorParams)
                    and vector.size == DIMENSION
                    and vector.distance == models.Distance.COSINE
                    and {"generos", "anio"}.issubset(info.payload_schema or {})
                    and db.count(COLECCION, exact=True).count == 9494)
    except Exception:
        return False


def nebula_lista():
    from src.grafo import conectar, ejecutar as consulta

    esperados = {"Usuario": 610, "Pelicula": 9476, "Genero": 19,
                 "VALORA": 100244, "PERTENECE_A": 21504,
                 "vertices": 10105, "edges": 121748}
    try:
        with conectar() as sesion:
            filas = consulta(sesion, "SHOW STATS")
        return {fila["Name"]: fila["Count"] for fila in filas} == esperados
    except Exception:
        return False


def preparar_datos():
    qdrant_ok = qdrant_listo()
    nebula_ok = nebula_lista()
    if qdrant_ok and nebula_ok:
        print("Las dos bases de datos ya están cargadas; se omite el ETL.")
        return

    comprobar_movielens()
    print("Preparando datos con DuckDB (TMDB se descarga automáticamente si falta)...")
    ejecutar(sys.executable, "scripts/preparar_datos.py")
    if not qdrant_ok:
        print("Cargando Qdrant con E5-base (la primera vez puede requerir bastantes recursos)...")
        ejecutar(sys.executable, "cargar_movielens.py")
        if not qdrant_listo():
            raise RuntimeError("La carga de Qdrant no pasó la comprobación final.")
    if not nebula_ok:
        print("Cargando NebulaGraph...")
        ejecutar(sys.executable, "cargar_nebula.py")
        if not nebula_lista():
            raise RuntimeError("La carga de NebulaGraph no pasó la comprobación final.")


def main():
    os.chdir(RAIZ)
    comprobar_docker()
    preparar_python()
    if Path(sys.prefix).resolve() != ENTORNO.resolve():
        # En macOS, el binario del entorno puede ser un enlace al Python global.
        return subprocess.call([str(PYTHON), str(RAIZ / "instalar.py")], cwd=RAIZ)
    print("Iniciando las bases de datos con Docker...")
    ejecutar("docker", "compose", "up", "-d", "--wait")
    preparar_datos()
    print("\nMovieMatch preparado. Iniciando Streamlit en http://127.0.0.1:8501")
    ejecutar(sys.executable, "-m", "streamlit", "run", "app.py", "--server.address", "127.0.0.1")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile,
            KeyError, subprocess.CalledProcessError) as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nMovieMatch detenido.")
