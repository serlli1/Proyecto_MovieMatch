"""Funciones reutilizables para CLI y futura interfaz Streamlit."""
import os
from functools import lru_cache
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

COLECCION = "peliculas"
MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
URL_QDRANT = os.getenv("QDRANT_URL", "http://localhost:6333")

@lru_cache(maxsize=1)
def obtener_modelo():
    return SentenceTransformer(MODELO)

def cliente():
    return QdrantClient(url=URL_QDRANT, timeout=30)

def vectorizar(texto):
    return obtener_modelo().encode(texto, normalize_embeddings=True).tolist()

def texto_de_pelicula(pelicula):
    return f"{pelicula['sinopsis']} Géneros: {', '.join(pelicula['generos'])}."

def buscar_semanticamente(texto, genero=None, desde=None, hasta=None, limite=5):
    condiciones = []
    if genero:
        condiciones.append(models.FieldCondition(key="generos", match=models.MatchValue(value=genero)))
    if desde is not None or hasta is not None:
        condiciones.append(models.FieldCondition(key="anio", range=models.Range(gte=desde, lte=hasta)))
    filtro = models.Filter(must=condiciones) if condiciones else None
    return cliente().query_points(
        collection_name=COLECCION,
        query=vectorizar(texto),
        query_filter=filtro,
        with_payload=True,
        limit=limite,
    ).points
