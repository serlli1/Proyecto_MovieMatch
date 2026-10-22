"""Modelo y acceso a Qdrant compartidos por la carga y los buscadores."""
import os
from contextlib import closing
from functools import lru_cache

from qdrant_client import QdrantClient, models

COLECCION = "peliculas_v2"
MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIMENSION = 384
URL_QDRANT = os.getenv("QDRANT_URL", "http://localhost:6333")


@lru_cache(maxsize=1)
def obtener_modelo():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODELO)


def cliente():
    return QdrantClient(url=URL_QDRANT, timeout=30)


def vectorizar(texto):
    modelo = obtener_modelo()
    vector = modelo.encode(texto, normalize_embeddings=True, show_progress_bar=False)
    return vector.tolist()


def texto_de_pelicula(pelicula):
    generos = ", ".join(pelicula["generos"])
    return f"{pelicula['sinopsis']} Géneros: {generos}."


def obtener_metadatos():
    """Recorre toda la colección sin descargar sinopsis ni vectores."""
    generos = set()
    anios = set()
    total = 0
    offset = None
    with closing(cliente()) as db:
        while True:
            pagina, offset = db.scroll(
                collection_name=COLECCION,
                offset=offset,
                limit=256,
                with_payload=["generos", "anio"],
                with_vectors=False,
            )
            total += len(pagina)
            for punto in pagina:
                pelicula = punto.payload or {}
                generos.update(pelicula.get("generos") or [])
                if pelicula.get("anio") is not None:
                    anios.add(pelicula["anio"])
            if offset is None:
                break
    return total, sorted(generos), sorted(anios)


def buscar_semanticamente(texto, genero=None, desde=None, hasta=None, limite=5):
    texto = texto.strip()
    if not texto:
        raise ValueError("Escribe un texto para buscar.")
    if limite < 1:
        raise ValueError("El límite de resultados debe ser positivo.")
    if desde is not None and hasta is not None and desde > hasta:
        raise ValueError("El año mínimo no puede superar al máximo.")

    condiciones = []
    if genero:
        condiciones.append(models.FieldCondition(
            key="generos", match=models.MatchValue(value=genero)
        ))
    if desde is not None or hasta is not None:
        condiciones.append(models.FieldCondition(
            key="anio", range=models.Range(gte=desde, lte=hasta)
        ))
    filtro = None
    if condiciones:
        filtro = models.Filter(must=condiciones)
    vector = vectorizar(texto)
    with closing(cliente()) as db:
        respuesta = db.query_points(
            collection_name=COLECCION,
            query=vector,
            query_filter=filtro,
            with_payload=True,
            limit=limite,
        )
    return respuesta.points
