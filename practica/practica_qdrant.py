"""CRUD didáctico sobre un único punto de prueba, separado del catálogo MovieLens."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qdrant_client import models
from src.motor import DIMENSION, cliente, obtener_modelo, texto_de_pelicula, vectorizar

COLECCION_PRUEBA = "moviematch_practica"
ID_PRUEBA = 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accion", choices=["crear", "ver", "buscar", "actualizar", "eliminar"])
    parser.add_argument("--texto", default="Una expedición espacial busca un planeta habitable")
    parser.add_argument("--anio", type=int, default=2030, help="Nuevo año para actualizar")
    args = parser.parse_args()
    with closing(cliente()) as db:
        if not db.collection_exists(COLECCION_PRUEBA):
            if args.accion != "crear":
                parser.error("La colección de práctica no existe. Ejecuta primero crear.")
            db.create_collection(COLECCION_PRUEBA, vectors_config=models.VectorParams(
                size=DIMENSION, distance=models.Distance.COSINE,
            ))
        config = db.get_collection(COLECCION_PRUEBA).config.params.vectors
        if not isinstance(config, models.VectorParams) or config.size != DIMENSION or config.distance != models.Distance.COSINE:
            raise RuntimeError("La colección de práctica tiene una configuración incompatible.")
        puntos = db.retrieve(COLECCION_PRUEBA, ids=[ID_PRUEBA], with_payload=True)
        if puntos and (puntos[0].payload or {}).get("es_prueba") is not True:
            raise RuntimeError("El ID 1 no está marcado como prueba; no se modifica.")

        if args.accion == "crear":
            if puntos:
                parser.error("La película de prueba ya existe. Usa ver, actualizar o eliminar.")
            pelicula = {
                "movieId": ID_PRUEBA, "titulo": "PRUEBA — La misión del aula", "anio": 2026,
                "generos": ["Ciencia ficción"], "tmdbId": None, "imdbId": None,
                "sinopsis": "Una expedición espacial busca un planeta habitable para salvar a la humanidad.",
                "es_prueba": True,
            }
            vector = obtener_modelo().encode(
                "passage: " + texto_de_pelicula(pelicula),
                normalize_embeddings=True, show_progress_bar=False,
            )
            db.upsert(COLECCION_PRUEBA, points=[models.PointStruct(
                id=ID_PRUEBA, vector=vector.tolist(), payload=pelicula,
            )], wait=True)
            print("Película creada en moviematch_practica, ID 1 (no pertenece a MovieLens).")
        elif args.accion == "ver":
            print(json.dumps([p.payload for p in puntos], ensure_ascii=False, indent=2))
        elif args.accion == "buscar":
            texto = args.texto.strip()
            if not texto:
                parser.error("Escribe un texto no vacío.")
            resultados = db.query_points(
                COLECCION_PRUEBA, query=vectorizar(texto), limit=5, with_payload=True,
            ).points
            for punto in resultados:
                print(f"{punto.id}: {punto.payload['titulo']} ({punto.payload['anio']}) · {punto.score:.4f}")
            print(f"Resultados: {len(resultados)}")
        elif args.accion == "actualizar":
            if not puntos:
                parser.error("No existe la película de prueba. Ejecuta crear.")
            # El año no forma parte del texto vectorizado; no requiere otro embedding.
            db.set_payload(COLECCION_PRUEBA, payload={"anio": args.anio}, points=[ID_PRUEBA], wait=True)
            print(f"Año de la película de prueba actualizado a {args.anio}.")
        else:
            if puntos:
                db.delete(COLECCION_PRUEBA, points_selector=models.PointIdsList(points=[ID_PRUEBA]), wait=True)
            print("Película de prueba eliminada. La colección se conserva; ver debe mostrar [].")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
