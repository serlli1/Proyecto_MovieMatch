#!/usr/bin/env python3
"""Carga el catálogo normalizado de DuckDB en una nueva colección de Qdrant.

Ejecución (desde la raíz de MovieMatch):
    ./.venv/bin/python cargar_movielens.py

No elimina ni modifica la colección anterior `peliculas`.
Puedes volver a ejecutarlo: los puntos conservan su identificador movieId.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
from qdrant_client import models

from src.motor import cliente, obtener_modelo, texto_de_pelicula

RAIZ = Path(__file__).resolve().parent
RUTA_DUCKDB = RAIZ / "datos" / "moviematch.duckdb"
COLECCION_NUEVA = "peliculas_v2"
TAM_LOTE = 64


def preparar_coleccion(db, dimension: int) -> None:
    """Crea una colección independiente e índices sobre campos filtrables."""
    if not db.collection_exists(COLECCION_NUEVA):
        db.create_collection(
            collection_name=COLECCION_NUEVA,
            vectors_config=models.VectorParams(
                size=dimension, distance=models.Distance.COSINE
            ),
        )
        print(f"✓ Creada colección nueva '{COLECCION_NUEVA}' ({dimension} dimensiones).")
    else:
        config = db.get_collection(COLECCION_NUEVA).config.params.vectors
        if not isinstance(config, models.VectorParams) or config.size != dimension:
            raise RuntimeError(
                f"La colección '{COLECCION_NUEVA}' ya existe con otra configuración "
                "vectorial. No se ha modificado."
            )
        print(f"✓ Colección '{COLECCION_NUEVA}' existente; se actualizará por movieId.")

    # Crear los índices una sola vez; son los dos filtros empleados por app.py.
    schema = db.get_collection(COLECCION_NUEVA).payload_schema or {}
    for campo, tipo in (
        ("generos", models.PayloadSchemaType.KEYWORD),
        ("anio", models.PayloadSchemaType.INTEGER),
    ):
        if campo not in schema:
            db.create_payload_index(
                collection_name=COLECCION_NUEVA,
                field_name=campo,
                field_schema=tipo,
                wait=True,
            )
            print(f"✓ Índice de payload creado: {campo} ({tipo.value}).")


def limpiar_fila(fila: tuple) -> dict:
    """Normaliza los valores de DuckDB para generar un payload JSON válido."""
    movie_id, titulo, anio, generos, tmdb_id, imdb_id, sinopsis = fila
    if movie_id is None or not isinstance(sinopsis, str) or not sinopsis.strip():
        raise ValueError(f"Película sin ID o sinopsis: {movie_id!r}")

    return {
        "movieId": int(movie_id),
        "titulo": str(titulo),
        "anio": int(anio) if anio is not None else None,
        "generos": list(generos) if generos is not None else [],
        "tmdbId": int(tmdb_id) if tmdb_id is not None else None,
        "imdbId": str(imdb_id) if imdb_id is not None else None,
        "sinopsis": sinopsis.strip(),
    }


def main() -> None:
    if not RUTA_DUCKDB.is_file():
        raise FileNotFoundError(
            f"No existe {RUTA_DUCKDB}. Ejecuta primero scripts/03_etl_duckdb.py."
        )

    con = duckdb.connect(str(RUTA_DUCKDB), read_only=True)
    try:
        esperado = int(con.execute("SELECT COUNT(*) FROM peliculas_qdrant").fetchone()[0])
        if esperado < 100:
            raise RuntimeError(
                f"La tabla 'peliculas_qdrant' solo tiene {esperado} filas. "
                "Revisa el reporte del ETL antes de importar."
            )

        print(f"Películas listas en DuckDB: {esperado}")
        print("Cargando modelo de embeddings...")
        modelo = obtener_modelo()
        dimension = modelo.get_sentence_embedding_dimension()
        if not isinstance(dimension, int) or dimension <= 0:
            raise RuntimeError("No se ha podido determinar la dimensión del modelo.")

        db = cliente()
        preparar_coleccion(db, dimension)

        # Procesar en lotes: evita tener los 9.494 vectores en memoria a la vez.
        cursor = con.execute(
            """
            SELECT movieId, titulo, anio, generos, tmdbId, imdbId, sinopsis
            FROM peliculas_qdrant
            ORDER BY movieId
            """
        )

        procesadas = 0
        primera_id = None
        while True:
            filas = cursor.fetchmany(TAM_LOTE)
            if not filas:
                break
            peliculas = [limpiar_fila(fila) for fila in filas]
            textos = [texto_de_pelicula(p) for p in peliculas]
            vectores = modelo.encode(
                textos,
                batch_size=32,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            puntos = [
                models.PointStruct(
                    id=p["movieId"],
                    vector=v.tolist(),
                    payload=p,
                )
                for p, v in zip(peliculas, vectores)
            ]
            db.upsert(
                collection_name=COLECCION_NUEVA,
                points=puntos,
                wait=True,
            )
            if primera_id is None:
                primera_id = peliculas[0]["movieId"]
            procesadas += len(peliculas)
            print(f"\rVectorizadas e insertadas: {procesadas}/{esperado}", end="", flush=True)

        print()
        if procesadas != esperado:
            raise RuntimeError(f"Procesadas {procesadas} películas; DuckDB contenía {esperado}.")

        # Qdrant puede conservar registros de una ejecución anterior de v2;
        # una diferencia en el recuento indica que debe revisarse antes de activar la app.
        total = db.count(collection_name=COLECCION_NUEVA, exact=True).count
        if total != esperado:
            raise RuntimeError(
                f"Qdrant contiene {total} puntos, mientras que DuckDB tiene {esperado}. "
                "Revisa la colección antes de cambiar el buscador."
            )
        muestra = db.retrieve(
            collection_name=COLECCION_NUEVA,
            ids=[primera_id],
            with_payload=True,
            with_vectors=False,
        )
        if len(muestra) != 1 or int(muestra[0].payload.get("movieId", -1)) != primera_id:
            raise RuntimeError("No coincide el identificador del punto con el movieId.")

        print("\n=== QDRANT | CATÁLOGO MOVIELENS ===")
        print(f"Colección nueva:          {COLECCION_NUEVA}")
        print(f"Películas en DuckDB:      {esperado}")
        print(f"Puntos en Qdrant:         {total}")
        print(f"Dimensión de embeddings:  {dimension}")
        print("Índices:                  generos (keyword), anio (integer)")
        print("Identificador:            Point ID = movieId")
        print("Estado:                   OK")
        print("\nLa colección anterior 'peliculas' sigue intacta.")
        print("Tras verificar la carga, cambia COLECCION a 'peliculas_v2' en src/motor.py.")
    finally:
        con.close()


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, RuntimeError, ValueError, duckdb.Error) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
