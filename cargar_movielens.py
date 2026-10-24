"""Carga por lotes el catálogo de DuckDB en Qdrant, conservando movieId."""
import sys
import math
import time
from contextlib import closing
from pathlib import Path

import duckdb
from qdrant_client import models

from src.motor import (
    COLECCION, DIMENSION, TAM_EMBEDDINGS, cliente, obtener_modelo,
    texto_de_pelicula, vectorizar_consultas,
)

RUTA_DUCKDB = Path(__file__).resolve().parent / "datos" / "moviematch.duckdb"
TAM_LOTE = 64


def preparar_coleccion(db):
    indices = {
        "generos": models.PayloadSchemaType.KEYWORD,
        "anio": models.PayloadSchemaType.INTEGER,
    }
    esquema = {}
    if db.collection_exists(COLECCION):
        info = db.get_collection(COLECCION)
        config = info.config.params.vectors
        if (
            not isinstance(config, models.VectorParams)
            or config.size != DIMENSION
            or config.distance != models.Distance.COSINE
        ):
            raise RuntimeError(
                f"La colección '{COLECCION}' requiere vectores de {DIMENSION} "
                "dimensiones y distancia coseno. No se ha modificado."
            )
        esquema = info.payload_schema or {}
        for campo, tipo in indices.items():
            if campo in esquema and esquema[campo].data_type != tipo:
                raise RuntimeError(f"El índice '{campo}' debe ser de tipo {tipo.value}.")
    else:
        db.create_collection(
            collection_name=COLECCION,
            vectors_config=models.VectorParams(
                size=DIMENSION, distance=models.Distance.COSINE
            ),
        )

    for campo, tipo in indices.items():
        if campo not in esquema:
            db.create_payload_index(
                collection_name=COLECCION,
                field_name=campo,
                field_schema=tipo,
                wait=True,
            )


def limpiar_fila(fila):
    movie_id, titulo, anio, generos, tmdb_id, imdb_id, sinopsis = fila
    if movie_id is None or not isinstance(sinopsis, str) or not sinopsis.strip():
        raise ValueError(f"Película sin ID o sinopsis: {movie_id!r}")
    if anio is not None:
        anio = int(anio)
    if generos is None:
        generos = []
    if tmdb_id is not None:
        tmdb_id = int(tmdb_id)
    if imdb_id is not None:
        imdb_id = str(imdb_id)

    return {
        "movieId": int(movie_id),
        "titulo": str(titulo),
        "anio": anio,
        "generos": list(generos),
        "tmdbId": tmdb_id,
        "imdbId": imdb_id,
        "sinopsis": sinopsis.strip(),
    }


def cargar_lotes(con, db, modelo):
    cursor = con.execute("""
        SELECT movieId, titulo, anio, generos, tmdbId, imdbId, sinopsis
        FROM peliculas_qdrant ORDER BY movieId
    """)
    procesadas = 0
    ultimo_aviso = time.monotonic()
    while True:
        filas = cursor.fetchmany(TAM_LOTE)
        if not filas:
            break

        peliculas = []
        for fila in filas:
            pelicula = limpiar_fila(fila)
            peliculas.append(pelicula)

        existentes = db.retrieve(
            COLECCION, ids=[p["movieId"] for p in peliculas],
            with_payload=True, with_vectors=False,
        )
        guardadas = {}
        for punto in existentes:
            guardadas[punto.id] = punto.payload
        pendientes = []
        textos = []
        for pelicula in peliculas:
            if guardadas.get(pelicula["movieId"]) != pelicula:
                pendientes.append(pelicula)
                textos.append("passage: " + texto_de_pelicula(pelicula))
        # Prepara también query: para que las favoritas no se codifiquen en cada perfil.
        vectorizar_consultas([texto_de_pelicula(p) for p in peliculas])
        if not pendientes:
            procesadas += len(peliculas)
            continue

        vectores = modelo.encode(
            textos,
            batch_size=TAM_EMBEDDINGS,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        puntos = []
        for pelicula, vector in zip(pendientes, vectores, strict=True):
            punto = models.PointStruct(
                id=pelicula["movieId"],
                vector=vector.tolist(),
                payload=pelicula,
            )
            puntos.append(punto)

        db.upsert(collection_name=COLECCION, points=puntos, wait=True)
        procesadas += len(peliculas)
        if time.monotonic() - ultimo_aviso >= 30:
            print(f"\rPelículas procesadas: {procesadas}", end="", flush=True)
            ultimo_aviso = time.monotonic()
    return procesadas


def validar_carga(con, db):
    filas = con.execute("""
        SELECT movieId, titulo, anio, generos, tmdbId, imdbId, sinopsis
        FROM peliculas_qdrant
    """).fetchall()
    esperadas = {}
    for fila in filas:
        pelicula = limpiar_fila(fila)
        esperadas[pelicula["movieId"]] = pelicula
    ids = set()
    offset = None
    while True:
        puntos, offset = db.scroll(
            COLECCION, limit=128, offset=offset, with_payload=True, with_vectors=True
        )
        for punto in puntos:
            if punto.id in ids or punto.payload != esperadas.get(punto.id):
                raise RuntimeError(f"ID o metadatos incorrectos: {punto.id}")
            if len(punto.vector) != DIMENSION:
                raise RuntimeError(f"Dimensión incorrecta: {punto.id}")
            norma = math.sqrt(sum(valor * valor for valor in punto.vector))
            if not math.isfinite(norma) or abs(norma - 1) > 0.001:
                raise RuntimeError(f"Vector no normalizado: {punto.id}")
            ids.add(punto.id)
        if offset is None:
            break
    if ids != set(esperadas):
        raise RuntimeError("Los IDs de Qdrant no coinciden con DuckDB.")
    return len(ids)


def main():
    if not RUTA_DUCKDB.is_file():
        raise FileNotFoundError(
            f"No existe {RUTA_DUCKDB}. Ejecuta primero scripts/preparar_datos.py."
        )
    with duckdb.connect(str(RUTA_DUCKDB), read_only=True) as con:
        esperado, ids_unicos, validas = con.execute("""
            SELECT count(*), count(DISTINCT movieId),
                   count(*) FILTER (WHERE movieId >= 0 AND titulo IS NOT NULL
                                    AND sinopsis IS NOT NULL AND trim(sinopsis) <> '')
            FROM peliculas_qdrant
        """).fetchone()
        if esperado < 100:
            raise RuntimeError(
                f"Solo hay {esperado} películas para Qdrant. Revisa el informe del ETL."
            )
        if ids_unicos != esperado or validas != esperado:
            raise RuntimeError("Catálogo con IDs duplicados, IDs inválidos o textos ausentes.")

        print(f"Catálogo preparado: {esperado} películas.", flush=True)
        modelo = obtener_modelo()
        if modelo.get_embedding_dimension() != DIMENSION:
            raise RuntimeError(f"El modelo debe generar vectores de {DIMENSION} dimensiones.")
        with closing(cliente()) as db:
            preparar_coleccion(db)
            procesadas = cargar_lotes(con, db, modelo)
            total = validar_carga(con, db)
            if procesadas != esperado:
                raise RuntimeError("No se han procesado todas las películas.")
    print(f"\nCarga completada: {total} películas en '{COLECCION}'.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, duckdb.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
