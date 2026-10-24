"""Modelo y acceso a Qdrant compartidos por la carga y los buscadores."""
import os
import json
import sqlite3
from pathlib import Path
from contextlib import closing
from functools import lru_cache

from qdrant_client import QdrantClient, models

# Representación fija: cambiar texto, prefijos o tokenización exige colección y caché nuevas.
COLECCION = "peliculas_e5"
MODELO = "intfloat/multilingual-e5-base"
DIMENSION = 768
TAM_EMBEDDINGS = 8
CACHE_CONSULTAS = Path(__file__).resolve().parents[1] / "datos" / "consultas_e5.sqlite"
URL_QDRANT = os.getenv("QDRANT_URL", "http://localhost:6333")


@lru_cache(maxsize=1)
def obtener_modelo():
    from sentence_transformers import SentenceTransformer

    modelo = SentenceTransformer(MODELO)
    modelo.max_seq_length = 512
    return modelo


def cliente():
    return QdrantClient(url=URL_QDRANT, timeout=30)


def vectorizar(texto):
    return vectorizar_consultas([texto])[0]


def vectorizar_consultas(textos):
    """Conserva las consultas E5 por modelo y texto para reutilizarlas entre perfiles."""
    CACHE_CONSULTAS.parent.mkdir(parents=True, exist_ok=True)
    vectores = [None] * len(textos)
    pendientes = []
    with closing(sqlite3.connect(CACHE_CONSULTAS, timeout=30)) as cache, cache:
        cache.execute("""
            CREATE TABLE IF NOT EXISTS consultas (
                modelo TEXT, texto TEXT, vector TEXT,
                PRIMARY KEY (modelo, texto)
            )
        """)
        for indice, texto in enumerate(textos):
            fila = cache.execute(
                "SELECT vector FROM consultas WHERE modelo=? AND texto=?",
                (MODELO, texto),
            ).fetchone()
            if fila is None:
                pendientes.append(indice)
            else:
                vectores[indice] = json.loads(fila[0])
        if pendientes:
            consultas = []
            for indice in pendientes:
                consultas.append("query: " + textos[indice])
            nuevos = obtener_modelo().encode(
                consultas, batch_size=TAM_EMBEDDINGS,
                normalize_embeddings=True, show_progress_bar=False,
            )
            for indice, vector in zip(pendientes, nuevos, strict=True):
                vectores[indice] = vector.tolist()
                cache.execute(
                    "INSERT OR REPLACE INTO consultas VALUES (?, ?, ?)",
                    (MODELO, textos[indice], json.dumps(vectores[indice])),
                )
    return vectores


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
            COLECCION, ids=favoritas, with_payload=["titulo", "sinopsis", "generos"], with_vectors=False
        )
        # Los lotes agrupan consultas independientes: no se promedian vectores.
        for inicio in range(0, len(referencias), 32):
            lote = referencias[inicio:inicio + 32]
            textos = []
            for referencia in lote:
                textos.append(texto_de_pelicula(referencia.payload))
            vectores = vectorizar_consultas(textos)
            consultas = []
            for vector in vectores:
                consultas.append(models.QueryRequest(
                    query=vector, filter=filtro, limit=10, with_payload=True
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
    recomendaciones = []
    titulos = set()
    for pelicula in ordenadas:
        titulo = pelicula["titulo"].strip().casefold()
        if titulo in titulos:
            continue
        titulos.add(titulo)
        recomendaciones.append(pelicula)
        if len(recomendaciones) == 5:
            break
    return recomendaciones


def obtener_peliculas(ids):
    if not ids:
        return {}
    with closing(cliente()) as db:
        puntos = db.retrieve(COLECCION, ids=ids, with_payload=True, with_vectors=False)
    peliculas = {}
    for punto in puntos:
        peliculas[punto.id] = punto.payload or {}
    return peliculas
