"""Medición local sin modificar las bases: python scripts/medir_rendimiento.py."""
import argparse
from contextlib import closing
from pathlib import Path
import platform
from statistics import mean, median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qdrant_client import models
from src import grafo, motor

CONSULTAS = [
    "Un hombre descubre que vive en una realidad simulada",
    "Una familia lucha por sobrevivir a una invasión de zombis",
    "Una expedición espacial para salvar a la humanidad",
]
USUARIOS = [1, 2, 610]


def medir(nombre, operacion, repeticiones):
    inicio = perf_counter()
    operacion(0)
    primera = (perf_counter() - inicio) * 1000
    tiempos = []
    for indice in range(repeticiones):
        inicio = perf_counter()
        operacion(indice)
        tiempos.append((perf_counter() - inicio) * 1000)
    print(
        f"| {nombre} | {primera:.2f} | {mean(tiempos):.2f} | "
        f"{median(tiempos):.2f} | {min(tiempos):.2f} | {max(tiempos):.2f} |",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeticiones", type=int, default=6)
    args = parser.parse_args()
    if args.repeticiones < 1:
        parser.error("El número de repeticiones debe ser positivo.")
    print(f"Python {platform.python_version()} · {platform.platform()}", flush=True)
    inicio = perf_counter()
    modelo = motor.obtener_modelo()
    print(f"Carga del modelo: {perf_counter() - inicio:.3f} s; dispositivo: {modelo.device}.")
    print(f"{args.repeticiones} repeticiones posteriores por fila; tiempos en ms.")
    print("Primera = primera llamada medida, no arranque en frío del servidor.")
    print("Sin caché de resultados de Streamlit; incluye transporte y deserialización del cliente.")
    print("| Operación | Primera | Media | Mediana | Mínimo | Máximo |")
    print("|---|---:|---:|---:|---:|---:|")

    medir("Generar query E5 (modelo cargado, sin caché)", lambda i: modelo.encode(
        "query: " + CONSULTAS[i % len(CONSULTAS)],
        normalize_embeddings=True, show_progress_bar=False,
    ), args.repeticiones)

    # Aísla las búsquedas de la caché del usuario; no borra ni invalida sus entradas.
    cache_original = motor.CACHE_CONSULTAS
    try:
        with TemporaryDirectory(prefix="moviematch_medicion_") as temporal:
            motor.CACHE_CONSULTAS = Path(temporal) / "consultas.sqlite"
            for texto in CONSULTAS:
                inicio = perf_counter()
                motor.vectorizar(texto)
                print(f"Alta en caché vacía ({texto}): {(perf_counter()-inicio)*1000:.2f} ms")
            vectores = motor.vectorizar_consultas(CONSULTAS)
            medir("Recuperar query de SQLite", lambda i: motor.vectorizar(
                CONSULTAS[i % len(CONSULTAS)]), args.repeticiones)
            filtro = models.Filter(must=[
                models.FieldCondition(key="generos", match=models.MatchValue(value="Ciencia ficción")),
                models.FieldCondition(key="anio", range=models.Range(gte=1990, lte=2010)),
            ])
            with closing(motor.cliente()) as db:
                for nombre, condiciones in [("Sin filtros", None), ("Género y año", filtro)]:
                    medir(f"Qdrant {nombre} (vector preparado)", lambda i: db.query_points(
                        motor.COLECCION, query=vectores[i % len(vectores)],
                        query_filter=condiciones, limit=5, with_payload=True,
                    ), args.repeticiones)
            for nombre, opciones in [
                ("Sin filtros", {}),
                ("Género y año", {"genero": "Ciencia ficción", "desde": 1990, "hasta": 2010}),
            ]:
                medir(f"Búsqueda total {nombre} (query en caché)", lambda i: motor.buscar_semanticamente(
                    CONSULTAS[i % len(CONSULTAS)], **opciones,
                ), args.repeticiones)
    finally:
        motor.CACHE_CONSULTAS = cache_original

    medir("Recuperar 3 películas por ID (función completa)",
          lambda i: motor.obtener_peliculas([1, 2571, 79132]), args.repeticiones)
    perfiles = [grafo.perfil(usuario) for usuario in USUARIOS]
    # Las favoritas ya están en la caché persistente preparada por el cargador.
    medir("Contenido, perfiles 1/2/610 (sin consulta de perfil)",
          lambda i: motor.recomendar_contenido(perfiles[i % len(perfiles)]), args.repeticiones)
    medir("Nebula: Top 10", lambda i: grafo.top_comunidad(), args.repeticiones)
    medir("Nebula: perfil", lambda i: grafo.perfil(USUARIOS[i % len(USUARIOS)]), args.repeticiones)
    medir("Nebula: colaborativas (perfil preparado)", lambda i: grafo.colaborativas(
        USUARIOS[i % len(USUARIOS)], perfiles[i % len(perfiles)]), args.repeticiones)
    medir("Nebula: géneros favoritos", lambda i: grafo.generos_favoritos(
        USUARIOS[i % len(USUARIOS)]), args.repeticiones)
    print("Las filas de funciones incluyen conexión y procesamiento Python; no son tiempos internos del servidor.")


if __name__ == "__main__":
    main()
