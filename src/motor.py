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


def recomendar_contenido(valoraciones):
    """Busca por cada favorita y conserva la mejor similitud por candidata."""
    favoritas = []
    valoradas = []
    titulos_valorados = set()
    for pelicula in valoraciones:
        valoradas.append(int(pelicula["movieId"]))
        titulo = (pelicula.get("titulo") or "").strip().casefold()
        if titulo:
            titulos_valorados.add(titulo)
        if pelicula["puntuacion"] >= 4:
            favoritas.append(pelicula["movieId"])
    if not favoritas:
        return []

    ids_valorados = set(valoradas)
    candidatas = {}
    filtro = models.Filter(must_not=[models.HasIdCondition(has_id=valoradas)])
    with closing(cliente()) as db:
        referencias = db.retrieve(
            COLECCION, ids=favoritas, with_payload=["titulo"], with_vectors=False
        )
        # Los lotes agrupan consultas independientes: no se promedian vectores.
        for inicio in range(0, len(referencias), 32):
            lote = referencias[inicio:inicio + 32]
            consultas = []
            for referencia in lote:
                consultas.append(models.QueryRequest(
                    query=referencia.id, filter=filtro, limit=10, with_payload=True
                ))
            respuestas = db.query_batch_points(COLECCION, requests=consultas)
            for referencia, respuesta in zip(lote, respuestas, strict=True):
                for punto in respuesta.points:
                    titulo = (punto.payload or {}).get("titulo", "").strip().casefold()
                    titulo_origen = (referencia.payload or {}).get("titulo", "").strip().casefold()
                    if int(punto.id) in ids_valorados:
                        continue
                    if titulo and (titulo in titulos_valorados or titulo == titulo_origen):
                        continue

                    anterior = candidatas.get(punto.id)
                    if anterior is None or punto.score > anterior["similitud"]:
                        pelicula = dict(punto.payload or {})
                        pelicula["movieId"] = punto.id
                        pelicula["similitud"] = punto.score
                        pelicula["motivo"] = (
                            f"Similar a {referencia.payload['titulo']}, "
                            "una de tus películas favoritas."
                        )
                        pelicula["referencia"] = referencia.id
                        candidatas[punto.id] = pelicula
    ordenadas = sorted(
        candidatas.values(), key=lambda p: (-p["similitud"], p["movieId"])
    )
    return ordenadas[:5]


def obtener_peliculas(ids):
    if not ids:
        return {}
    with closing(cliente()) as db:
        puntos = db.retrieve(COLECCION, ids=ids, with_payload=True, with_vectors=False)
    peliculas = {}
    for punto in puntos:
        peliculas[punto.id] = punto.payload or {}
    return peliculas
