"""Buscador Streamlit: python -m streamlit run app.py."""
import streamlit as st

from src import grafo
from src.motor import (
    COLECCION, buscar_semanticamente, obtener_metadatos, obtener_peliculas,
    recomendar_contenido,
)

st.set_page_config(
    page_title="MovieMatch · Descubre tu película",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1150px;}
[data-testid="stSidebar"] {background-color: #111827;}
[data-testid="stSidebar"] * {color: #f3f4f6;}
.movie-hero {
  padding: 2rem 2.2rem; border-radius: 20px;
  background: linear-gradient(115deg, #20143c 0%, #45235f 54%, #98344e 100%);
  color: white; margin-bottom: 1rem;
}
.movie-hero h1 {color: #fff; font-weight: 760; margin: 0; font-size: 2.4rem;}
.movie-hero p {color: #f1dce9; font-size: 1.1rem; margin: .6rem 0 0 0;}
.movie-hero .tag {font-size: .8rem; letter-spacing: .12em; text-transform: uppercase; color: #f9b4d2;}
</style>
""", unsafe_allow_html=True)


def titulo_con_anio(pelicula):
    titulo = str(pelicula.get("titulo", "Sin título")).strip()
    anio = pelicula.get("anio")
    if anio is None or titulo.endswith(f"({anio})"):
        return titulo
    return f"{titulo} ({anio})"


def tarjeta_pelicula(pelicula, puesto, similitud):
    """Muestra título, géneros, sinopsis y similitud de un resultado."""
    titulo = titulo_con_anio(pelicula)
    generos = ", ".join(pelicula.get("generos", [])) or "Sin género"

    with st.container(border=True):
        cabecera, marcador = st.columns([5, 1.4], vertical_alignment="center")
        with cabecera:
            st.markdown(f"**{puesto:02d} · {titulo}**")
            st.caption(generos)
        with marcador:
            st.metric("Similitud", f"{similitud:.4f}")
        st.write(pelicula.get("sinopsis", ""))


st.markdown("""
<div class="movie-hero">
    <div class="tag">Qdrant · Embeddings · Python</div>
    <h1>🎬 MovieMatch</h1>
    <p>Encuentra películas por el significado de sus historias.</p>
</div>
""", unsafe_allow_html=True)


# La colección forma parte de las claves de caché de Qdrant.
@st.cache_data(ttl=300, show_spinner=False)
def metadatos_catalogo(coleccion):
    return obtener_metadatos()


def mostrar_buscador():
    try:
        total, generos_catalogo, anios = metadatos_catalogo(COLECCION)
    except Exception as exc:
        st.error("No se ha podido conectar con Qdrant o recuperar el catálogo.")
        st.info("Comprueba que Docker Desktop está iniciado y que has ejecutado `docker compose up -d`.")
        st.info("Si falta el catálogo, ejecuta `python cargar_movielens.py` después del ETL.")
        with st.expander("Detalles técnicos"):
            st.exception(exc)
        return

    minimo = None
    maximo = None
    if anios:
        minimo = min(anios)
        maximo = max(anios)

    with st.sidebar:
        st.title("⚙️ Panel de búsqueda")
        st.success("● Qdrant conectado")
        st.metric("Películas", total)
        st.subheader("Filtros")
        genero_elegido = st.selectbox("Género", ["Todos"] + generos_catalogo)
        if anios and minimo < maximo:
            anos_elegidos = st.slider(
                "Año de estreno", min_value=minimo, max_value=maximo,
                value=(minimo, maximo), step=1,
            )
        else:
            if anios:
                st.caption(f"Año disponible: {minimo}")
            else:
                st.caption("Sin años disponibles")
            anos_elegidos = (minimo, maximo)
        st.caption("El intervalo completo incluye películas sin año; al acotarlo, se excluyen.")
        limite = st.slider("Número de resultados", min_value=3, max_value=15, value=5)

    genero = None
    if genero_elegido != "Todos":
        genero = genero_elegido
    desde, hasta = anos_elegidos
    if anos_elegidos == (minimo, maximo):
        desde, hasta = None, None

    st.subheader("¿Qué te apetece ver hoy?")
    st.caption("Describe una trama, situación o temática. No necesitas conocer el título de la película.")

    with st.form("form_buscar"):
        consulta = st.text_input(
            "Describe la película",
            placeholder="Escribe la historia de la película que buscas...",
        )
        enviar = st.form_submit_button(
            "🔎 Buscar por significado", type="primary", use_container_width=True
        )

    if enviar:
        st.session_state.ultima_consulta = consulta.strip()
        if not st.session_state.ultima_consulta:
            st.warning("Escribe un texto para buscar.")

    if st.session_state.get("ultima_consulta"):
        texto = st.session_state.ultima_consulta
        with st.spinner("Buscando películas..."):
            try:
                resultados = buscar_semanticamente(
                    texto, genero=genero, desde=desde, hasta=hasta, limite=limite
                )
            except Exception as exc:
                st.error("No se pudo completar la búsqueda semántica.")
                with st.expander("Detalles técnicos"):
                    st.exception(exc)
                return

        st.caption(f"{len(resultados)} resultados · búsqueda semántica · similitud coseno")
        if resultados:
            for puesto, resultado in enumerate(resultados, 1):
                tarjeta_pelicula(resultado.payload or {}, puesto, similitud=resultado.score)
        else:
            st.info("No se encontraron películas con estos filtros. Prueba otros criterios.")
        st.caption("La similitud coseno no es una probabilidad ni un porcentaje de acierto.")


@st.cache_data(ttl=300, show_spinner=False)
def usuarios_disponibles():
    return grafo.usuarios()


@st.cache_data(ttl=300, show_spinner=False)
def top_comunidad():
    return grafo.top_comunidad()


@st.cache_data(ttl=300, show_spinner=False)
def perfil_usuario(usuario):
    return grafo.perfil(usuario)


@st.cache_data(ttl=300, show_spinner=False)
def contenido_usuario(usuario, coleccion):
    return recomendar_contenido(perfil_usuario(usuario))


@st.cache_data(ttl=300, show_spinner=False)
def colaborativas_usuario(usuario):
    return grafo.colaborativas(usuario, perfil_usuario(usuario))


@st.cache_data(ttl=300, show_spinner=False)
def generos_usuario(usuario):
    return grafo.generos_favoritos(usuario)


def tarjeta_recomendacion(pelicula, motivo):
    with st.container(border=True):
        imagen, detalle = st.columns([1, 6])
        with imagen:
            st.markdown("## 🎬")
        with detalle:
            titulo = titulo_con_anio(pelicula)
            st.markdown(f"**{titulo}**")
            st.caption(", ".join(pelicula.get("generos", [])) or "Sin género")
            sinopsis = pelicula.get("sinopsis")
            if sinopsis:
                if len(sinopsis) > 350:
                    sinopsis = sinopsis[:347].rsplit(" ", 1)[0] + "…"
                st.write(sinopsis)
            else:
                st.caption("Sin sinopsis disponible.")
            st.caption(motivo)


def mostrar_top():
    st.subheader("Top 10 de la comunidad")
    st.caption("Nota media · al menos 20 valoraciones por película")
    try:
        peliculas = top_comunidad()
    except Exception as exc:
        st.info("El Top 10 no está disponible. Comprueba que NebulaGraph está iniciado y cargado.")
        with st.expander("Detalles técnicos"):
            st.exception(exc)
        return
    if not peliculas:
        st.info("Todavía no hay suficientes valoraciones para elaborar la clasificación.")
    for puesto, pelicula in enumerate(peliculas, 1):
        titulo = titulo_con_anio(pelicula)
        st.markdown(f"**{puesto}. {titulo}**")
        st.caption(f"★ {pelicula['media']:.2f}/5 · {pelicula['votos']} valoraciones")


def mostrar_perfil():
    try:
        usuarios = usuarios_disponibles()
    except Exception as exc:
        st.info("Los perfiles no están disponibles. Comprueba que NebulaGraph está iniciado y cargado.")
        with st.expander("Detalles técnicos"):
            st.exception(exc)
        return
    if not usuarios:
        st.info("Importa los datos del grafo para disponer de perfiles.")
        return
    usuario = st.selectbox("Tu perfil", usuarios, format_func=lambda numero: f"Usuario {numero}")
    st.caption("Perfiles anónimos de MovieLens. Se excluyen las películas que ya has valorado.")

    st.subheader("Porque te gustó...")
    try:
        with st.spinner("Buscando películas similares a tus favoritas..."):
            peliculas = contenido_usuario(usuario, COLECCION)
        for pelicula in peliculas:
            tarjeta_recomendacion(pelicula, pelicula["motivo"])
        if not peliculas:
            st.info("No hay recomendaciones disponibles a partir de tus favoritas con sinopsis.")
    except Exception as exc:
        st.info("Las recomendaciones por contenido no están disponibles en este momento.")
        with st.expander("Detalles técnicos"):
            st.exception(exc)

    st.subheader("A usuarios como tú...")
    try:
        peliculas = colaborativas_usuario(usuario)
        ids = [pelicula["movieId"] for pelicula in peliculas]
        detalles = {}
        try:
            detalles = obtener_peliculas(ids)
        except Exception as exc:
            st.caption("Las sinopsis no están disponibles en este momento.")
            with st.expander("Detalles técnicos"):
                st.exception(exc)
        for pelicula in peliculas:
            pelicula = dict(pelicula)
            pelicula["sinopsis"] = detalles.get(pelicula["movieId"], {}).get("sinopsis")
            motivo = (
                f"{pelicula['apoyos']} usuarios con gustos similares "
                "la valoraron con 4 estrellas o más."
            )
            tarjeta_recomendacion(pelicula, motivo)
        if not peliculas:
            st.info("No hay suficientes coincidencias para recomendar películas de otros usuarios.")
    except Exception as exc:
        st.info("Las recomendaciones de otros usuarios no están disponibles en este momento.")
        with st.expander("Detalles técnicos"):
            st.exception(exc)

    st.subheader("Tus géneros favoritos")
    st.caption("Ordenados por nota media, con al menos 5 películas valoradas en cada género.")
    try:
        generos = generos_usuario(usuario)
        for genero in generos:
            etiqueta = (
                f"{genero['genero']} · {genero['media']:.2f}/5 "
                f"· {genero['peliculas']} películas valoradas"
            )
            st.progress(genero["media"] / 5, text=etiqueta)
        if not generos:
            st.info("Todavía no hay géneros con suficientes valoraciones.")
    except Exception as exc:
        st.info("Tus géneros favoritos no están disponibles en este momento.")
        with st.expander("Detalles técnicos"):
            st.exception(exc)


buscar, para_ti = st.tabs(["Buscar películas", "Para ti"])
with buscar:
    mostrar_buscador()
    st.divider()
    mostrar_top()
with para_ti:
    mostrar_perfil()
