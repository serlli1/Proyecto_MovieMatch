# MovieMatch

Buscador semántico para **Agregación y Presentación de Datos en IoT**. DuckDB integra
los CSV de MovieLens y TMDB mediante SQL. Qdrant almacena las sinopsis vectorizadas
y permite buscar por significado, con filtros de género y año. Streamlit ofrece
la interfaz y `buscar.py` permite consultar desde la terminal.

El catálogo local contiene 9.742 películas, 610 usuarios y 100.836 valoraciones;
9.494 películas tienen sinopsis válida para Qdrant. Las demás permanecen en DuckDB.
`movieId` es la clave principal y el Point ID de Qdrant; `tmdbId` e `imdbId` son
identificadores externos. IMDb se conserva como texto, incluidos sus ceros.

## Preparación

Usa Python 3.11 (entorno comprobado), Docker Desktop y una conexión para las descargas
iniciales. Ejecuta los comandos desde la raíz del proyecto:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
docker compose up -d
```

Si `.venv` ya existe, basta con activarlo. Las cuatro dependencias directas están
fijadas a las versiones comprobadas; las dependencias transitivas no están fijadas.
Qdrant conserva los datos en el volumen `qdrant_data` y solo publica el puerto local.
Panel: [Qdrant](http://localhost:6333/dashboard). Puedes detenerlo sin borrar datos
con `docker compose stop` y arrancarlo con `docker compose start`.

## Fuentes y ETL

Descarga [MovieLens Latest Small de GroupLens](https://grouplens.org/datasets/movielens/latest/)
y descomprime `ml-latest-small.zip` dentro de `datos/fuentes/`. Deben existir:

```text
datos/fuentes/ml-latest-small/movies.csv
datos/fuentes/ml-latest-small/links.csv
datos/fuentes/ml-latest-small/ratings.csv
```

El ETL descarga `movies_metadata.csv` del [depósito de Zenodo](https://zenodo.org/records/18099452)
si falta en `datos/fuentes/`, y comprueba el MD5 de la descarga. También puedes aportar
un CSV ya descargado mediante `--metadata /ruta/movies_metadata.csv`.

```bash
python scripts/03_etl_duckdb.py
```

Este comando reconstruye las tablas de `datos/moviematch.duckdb` dentro de una
transacción y actualiza las exportaciones y `datos/reporte_etl.json`. No hace falta
repetirlo para buscar si ya dispones del catálogo preparado. El JOIN utiliza
`tmdbId`, descarta IMDb incompatibles y resuelve coincidencias duplicadas priorizando
IMDb, año y sinopsis. Conserva controles de claves, valoraciones y relaciones;
las filas de TMDB con errores de lectura se omiten.

En `datos/procesados/` genera `peliculas_qdrant.parquet` y cuatro CSV para el futuro
grafo: `peliculas_nebula.csv`, `usuarios_nebula.csv`, `valoraciones_nebula.csv` y
`peliculas_generos_nebula.csv`. NebulaGraph no está implementado ni es necesario.
Las consultas académicas están en `scripts/sql/consultas_ejemplo.sql`.

## Carga y búsqueda

Para preparar Qdrant por primera vez o actualizarlo deliberadamente:

```bash
python cargar_movielens.py
```

La carga lee DuckDB, genera vectores por lotes y crea `peliculas_v2` solo si no
existe. Si existe, comprueba sus 384 dimensiones y distancia coseno, y actualiza
puntos por `movieId`. Mantiene índices sobre `generos` y `anio`; nunca elimina ni
recrea colecciones y avisa si el recuento final no coincide. Una interrupción puede
dejar una carga parcial: repetirla actualiza los mismos IDs. Si ya está cargada,
no necesitas ejecutar este paso para iniciar la aplicación.

Carga y consultas comparten `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
El modelo se descarga la primera vez que se utiliza. Las sinopsis son principalmente
inglesas; el modelo admite consultas en español. La similitud no es una probabilidad.

```bash
python -m streamlit run app.py
python buscar.py "aventuras en el espacio" --genero "Ciencia ficción"
python buscar.py "un viaje en el tiempo" --desde 1990 --hasta 2020 --limite 5
```

Streamlit guarda géneros y años en caché durante cinco minutos, sin descargar
sinopsis para construir los filtros. El intervalo completo incluye películas sin
año; al acotarlo se excluyen. En terminal, omitir `--desde` y `--hasta` incluye todos
los años. `QDRANT_URL` permite cambiar la dirección, por defecto `http://localhost:6333`.

## Archivos

- `app.py`, `buscar.py`: interfaz y terminal.
- `src/motor.py`: modelo, consultas y metadatos de Qdrant.
- `cargar_movielens.py`: carga de DuckDB a Qdrant.
- `scripts/03_etl_duckdb.py`, `scripts/sql/`: integración y consultas SQL.

Los datasets y las bases locales están excluidos de Git.
