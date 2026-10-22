"""Inserta las películas del JSON en la colección Qdrant."""
import json
from pathlib import Path
from qdrant_client import models
from src.motor import COLECCION, cliente, obtener_modelo, texto_de_pelicula

ARCHIVO = Path(__file__).parent / "datos" / "peliculas.json"

def main():
    peliculas = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    db = cliente()
    modelo = obtener_modelo()
    dimension = modelo.get_sentence_embedding_dimension()
    if not db.collection_exists(COLECCION):
        db.create_collection(
            collection_name=COLECCION,
            vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
        )
        print(f"Colección '{COLECCION}' creada ({dimension} dimensiones, similitud coseno).")
    else:
        info = db.get_collection(COLECCION)
        tam = info.config.params.vectors.size
        if tam != dimension:
            raise RuntimeError(f"La colección tiene {tam} dimensiones, el modelo utiliza {dimension}.")
    textos = [texto_de_pelicula(p) for p in peliculas]
    vectores = modelo.encode(textos, normalize_embeddings=True, show_progress_bar=True)
    puntos = [
        models.PointStruct(id=p["id"], vector=v.tolist(), payload={k: val for k, val in p.items() if k != "id"})
        for p, v in zip(peliculas, vectores)
    ]
    db.upsert(collection_name=COLECCION, points=puntos, wait=True)
    print(f"Cargadas/actualizadas {len(puntos)} películas en Qdrant.")

if __name__ == "__main__":
    main()
