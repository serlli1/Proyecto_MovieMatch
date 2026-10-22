"""Buscador Streamlit: python -m streamlit run app.py."""
import streamlit as st

from src.motor import buscar_semanticamente, obtener_metadatos

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


def tarjeta_pelicula(pelicula, puesto, similitud):
    """Muestra título, géneros, sinopsis y similitud de un resultado."""
    titulo = str(pelicula.get("titulo", "Sin título"))
    anio = pelicula.get("anio") or "—"
    generos = ", ".join(pelicula.get("generos", [])) or "Sin género"

    with st.container(border=True):
        cabecera, marcador = st.columns([5, 1.4], vertical_alignment="center")
        with cabecera:
            st.markdown(f"**{puesto:02d} · {titulo} ({anio})**")
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


@st.cache_data(ttl=300, show_spinner=False)
def metadatos_catalogo():
    return obtener_metadatos()


try:
    total, generos_catalogo, anios = metadatos_catalogo()
except Exception as exc:
    st.error("No se ha podido conectar con Qdrant o recuperar el catálogo.")
    st.info("Comprueba que Docker Desktop está iniciado y que has ejecutado `docker compose up -d`.")
    st.info("Si falta el catálogo, ejecuta `python cargar_movielens.py` después del ETL.")
    with st.expander("Detalles técnicos"):
        st.exception(exc)
    st.stop()

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
        value="alguien descubre que su mundo es una simulación",
        placeholder="Ej.: una exploradora viaja al pasado para cambiar su destino",
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
            st.stop()

    st.caption(f"{len(resultados)} resultados · búsqueda semántica · similitud coseno")
    if resultados:
        for puesto, resultado in enumerate(resultados, 1):
            tarjeta_pelicula(resultado.payload or {}, puesto, similitud=resultado.score)
    else:
        st.info("No se encontraron películas con estos filtros. Prueba otros criterios.")
    st.caption("La similitud coseno no es una probabilidad ni un porcentaje de acierto.")
else:
    st.info("Prueba a buscar: «viajar a otro planeta», «amor imposible» o «realidad simulada».")
