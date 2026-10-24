# MovieMatch 🎬

Buscador y recomendador de películas desarrollado para **Agregación y Presentación de Datos en IoT**.
Integra datos de MovieLens y TMDB con **DuckDB**, utiliza **Qdrant** para buscar por significado mediante **Multilingual E5-base** y **NebulaGraph** para recomendaciones colaborativas. La interfaz está hecha en **Streamlit**.

## Instalar y ejecutar desde cero

Necesitas **[Python 3.11](https://www.python.org/downloads/)**, **[Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado y abierto** y conexión a Internet. No necesitas descargar los datasets ni preparar las bases manualmente. Docker Desktop incluye Docker Compose.

1. Clona el repositorio:

   ```bash
   git clone https://github.com/serlli1/Proyecto_MovieMatch.git
   cd Proyecto_MovieMatch
   ```
2. Ejecuta el instalador adecuado:
   - **macOS:** `bash instalar.command`.
   - **Windows:** abre `instalar.bat` (o ejecútalo desde la terminal).
3. Abre **http://127.0.0.1:8501** si el navegador no se abre automáticamente.

El instalador crea `.venv`, instala las dependencias, inicia los contenedores, descarga y verifica las fuentes, ejecuta el ETL, llena Qdrant y NebulaGraph y arranca Streamlit. La primera ejecución descarga también el modelo E5 y genera miles de embeddings; requiere tiempo y espacio en disco. **No interrumpas esa primera carga salvo que sea necesario.** Las descargas HTTPS validan el certificado con los almacenes del sistema y de Mozilla; ante errores de certificados, revisa la configuración de Windows, VPN o antivirus. Puedes repetir el instalador si falla: reutiliza las bases ya completas y no elimina datos.

**Siguientes ejecuciones:** utiliza el mismo `instalar.command` o `instalar.bat`. Si las bases ya están completas, no repite las descargas ni las cargas.

## Qué hace cada tecnología

| Componente | Función |
|---|---|
| DuckDB | Combina MovieLens con las sinopsis de TMDB y prepara las cargas |
| Qdrant | Busca películas semánticamente con E5-base (768 dimensiones y coseno) |
| NebulaGraph | Relaciona usuarios, películas, valoraciones y géneros |
| Streamlit | Muestra búsquedas, filtros, Top 10 y recomendaciones personalizadas |

La versión de referencia contiene **9.742 películas** en DuckDB, **9.494** en Qdrant y **9.476** en NebulaGraph, con **610 usuarios** y **100.244 valoraciones** en el grafo. Qdrant usa la colección `peliculas_e5`; las búsquedas llevan `query: ` y los documentos `passage: `.

Los datos locales, las bases y la caché no se suben a Git. Qdrant y NebulaGraph persisten en los volúmenes Docker. **No ejecutes `docker compose down -v` ni borres los volúmenes** si quieres conservar sus datos.

## Comandos útiles

```bash
# Detener los contenedores sin borrar datos:
docker compose stop

# Consultar películas desde terminal (con el entorno activado):
python buscar.py "una aventura espacial" --limite 5

# Repetir mediciones de rendimiento:
python scripts/medir_rendimiento.py --repeticiones 6
```

En macOS, activa el entorno con `source .venv/bin/activate`; en Windows, con `.venv\Scripts\activate`. Para ejecutar la interfaz normalmente basta con volver a usar el instalador.

## Fuentes y límites

- **MovieLens Latest Small** (GroupLens, 2018): [dataset](https://grouplens.org/datasets/movielens/latest/). El instalador comprueba los SHA-256 de `movies.csv`, `links.csv` y `ratings.csv` para garantizar la versión utilizada.
- **Sinopsis TMDB**: [copia de Zenodo](https://doi.org/10.5281/zenodo.18099452), verificada mediante MD5 durante el ETL.
- **Modelo de lenguaje:** [intfloat/multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base).

Las sinopsis son principalmente inglesas y E5 procesa como máximo 512 tokens. Las recomendaciones dependen del historial disponible; la similitud coseno no representa un porcentaje de acierto. La instalación está pensada para **uso local**, no para exposición pública.
