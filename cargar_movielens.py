"""Carga por lotes el catálogo de DuckDB en Qdrant, conservando movieId."""
import sys
from contextlib import closing
from pathlib import Path

import duckdb
from qdrant_client import models

from src.motor import COLECCION, DIMENSION, cliente, obtener_modelo, texto_de_pelicula

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
    primera_id = None
    while True:
        filas = cursor.fetchmany(TAM_LOTE)
        if not filas:
            break

        peliculas = []
        textos = []
        for fila in filas:
            pelicula = limpiar_fila(fila)
            peliculas.append(pelicula)
            textos.append(texto_de_pelicula(pelicula))

        vectores = modelo.encode(
            textos,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        puntos = []
        for pelicula, vector in zip(peliculas, vectores, strict=True):
            punto = models.PointStruct(
                id=pelicula["movieId"],
                vector=vector.tolist(),
                payload=pelicula,
            )
            puntos.append(punto)

        db.upsert(collection_name=COLECCION, points=puntos, wait=True)
        if primera_id is None:
            primera_id = peliculas[0]["movieId"]
        procesadas += len(puntos)
    return procesadas, primera_id


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

        modelo = obtener_modelo()
        if modelo.get_embedding_dimension() != DIMENSION:
            raise RuntimeError(f"El modelo debe generar vectores de {DIMENSION} dimensiones.")
        with closing(cliente()) as db:
            preparar_coleccion(db)
            procesadas, primera_id = cargar_lotes(con, db, modelo)
            total = db.count(collection_name=COLECCION, exact=True).count
            if procesadas != esperado or total != esperado:
                raise RuntimeError(
                    f"DuckDB: {esperado}; procesadas: {procesadas}; Qdrant: {total}. "
                    "Revisa el catálogo; no se han borrado puntos sobrantes."
                )
            muestra = db.retrieve(
                collection_name=COLECCION,
                ids=[primera_id],
                with_payload=True,
                with_vectors=False,
            )
            if len(muestra) != 1:
                raise RuntimeError("No se ha encontrado la película de comprobación.")
            punto = muestra[0]
            pelicula = punto.payload or {}
            if punto.id != primera_id or pelicula.get("movieId") != primera_id:
                raise RuntimeError("No coincide el identificador del punto con el movieId.")
    print(f"Carga completada: {total} películas en '{COLECCION}'.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, duckdb.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
