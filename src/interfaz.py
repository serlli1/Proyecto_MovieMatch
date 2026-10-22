"""Operaciones de MovieMatch usadas por la interfaz Streamlit.

Las búsquedas textuales se ejecutan contra el catálogo real de Qdrant
(no solo contra el archivo JSON inicial).
"""
import re
import unicodedata
from uuid import uuid4

from qdrant_client import models

from src.motor import COLECCION, cliente, texto_de_pelicula, vectorizar

STOPWORDS = {
    "que", "una", "uno", "con", "para", "los", "las", "del", "por", "sobre",
    "como", "quiero", "ver", "pelicula", "peliculas", "algo", "donde",
    "alguien", "esta", "hay", "sus", "dos", "muy", "entre", "tipo",
}

def palabras(texto):
    """Tokenización mínima para una baseline educativa, NO es BM25."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return {p for p in re.findall(r"[a-z]+", texto)
            if len(p) > 2 and p not in STOPWORDS}

def obtener_catalogo(maximo=10000):
    """Lee películas reales de Qdrant utilizando scroll paginado.

    maximo evita descargar sin aviso millones de payloads al navegador.
    """
    db = cliente()
    peliculas = []
    offset = None
    while len(peliculas) < maximo:
        pagina, offset = db.scroll(
            collection_name=COLECCION,
            offset=offset,
            limit=min(128, maximo-len(peliculas)),
            with_payload=True,
            with_vectors=False,
        )
        for punto in pagina:
            payload = dict(punto.payload or {})
            if payload.get("titulo"):
                peliculas.append(payload)
        if offset is None or not pagina:
            break
    return peliculas

def pasa_filtros(pelicula, genero=None, desde=None, hasta=None):
    generos = pelicula.get("generos", [])
    anio = pelicula.get("anio")
    if genero and genero not in generos:
        return False
    if desde is not None and (anio is None or anio < desde):
        return False
    if hasta is not None and (anio is None or anio > hasta):
        return False
    return True

def buscar_lexicamente(texto, peliculas, genero=None, desde=None, hasta=None, limite=5):
    """Ordena por número de palabras distintas coincidentes con la sinopsis/géneros."""
    consulta = palabras(texto)
    resultados = []
    for peli in peliculas:
        if not pasa_filtros(peli, genero, desde, hasta):
            continue
        doc = palabras(peli.get("sinopsis", "") + " " + " ".join(peli.get("generos", [])))
        coincidencias = sorted(consulta & doc)
        if coincidencias:
            resultados.append({
                "pelicula": peli,
                "coincidencias": coincidencias,
                "puntuacion": len(coincidencias),
            })
    resultados.sort(key=lambda r: (-r["puntuacion"], r["pelicula"]["titulo"].lower()))
    return resultados[:limite]

def insertar_pelicula(titulo, anio, generos, sinopsis):
    pelicula = {
        "titulo": titulo.strip(),
        "anio": int(anio),
        "generos": [g.strip() for g in generos if g.strip()],
        "sinopsis": sinopsis.strip(),
    }
    if not pelicula["titulo"] or not pelicula["sinopsis"] or not pelicula["generos"]:
        raise ValueError("El título, al menos un género y la sinopsis son obligatorios.")
    identificador = str(uuid4())
    cliente().upsert(
        collection_name=COLECCION,
        points=[models.PointStruct(
            id=identificador,
            vector=vectorizar(texto_de_pelicula(pelicula)),
            payload=pelicula,
        )],
        wait=True,
    )
    return identificador
