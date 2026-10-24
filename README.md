# MovieMatch

Proyecto de **Agregación y Presentación de Datos en IoT**. DuckDB prepara MovieLens
y TMDB; Qdrant busca por significado y por similitud con favoritas; NebulaGraph
almacena usuarios, películas, géneros y valoraciones para obtener recomendaciones
colaborativas. Streamlit presenta los resultados en dos pestañas:

- **Buscar películas:** búsqueda semántica con filtros y Top 10 de la comunidad.
- **Para ti:** selector de usuario anónimo, recomendaciones por contenido,
  recomendaciones colaborativas y barras de géneros favoritos.

El catálogo local contiene 9.742 películas, 610 usuarios y 100.836 valoraciones;
Qdrant conserva las 9.494 películas con sinopsis válida, tengan o no valoraciones.
NebulaGraph conserva 9.476 películas con sinopsis válida **y al menos una valoración**,
los 610 usuarios, 100.244 valoraciones y 21.504 relaciones película–género (19 géneros).
Las tablas maestras de DuckDB siguen completas: 9.742 películas, 100.836 valoraciones
y 22.050 relaciones película–género. Todos los usuarios conservan historial válido.
`movieId` es la clave principal y el Point ID de Qdrant; `tmdbId` e `imdbId` son
identificadores externos. IMDb se conserva como texto, incluidos sus ceros.

## Preparación

Usa Python 3.11 (entorno comprobado), Docker Desktop y una conexión para las descargas
iniciales. Ejecuta los comandos desde la raíz del proyecto:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
docker compose up -d --wait
```

Si `.venv` ya existe, basta con activarlo. Las dependencias directas están
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
python scripts/preparar_datos.py
```

Este comando reconstruye las tablas de `datos/moviematch.duckdb` dentro de una
transacción y actualiza las exportaciones y `datos/reporte_etl.json`. No hace falta
repetirlo para buscar si ya dispones del catálogo preparado. El JOIN utiliza
`tmdbId`, descarta IMDb incompatibles y resuelve coincidencias duplicadas priorizando
IMDb, año y sinopsis. Conserva controles de claves, valoraciones y relaciones;
las filas de TMDB con errores de lectura se omiten.

En `datos/procesados/` genera `peliculas_qdrant.parquet` y cuatro CSV para el
grafo: `peliculas_nebula.csv`, `usuarios_nebula.csv`, `valoraciones_nebula.csv` y
`peliculas_generos_nebula.csv`. El importador del grafo utiliza estos cuatro CSV.
La selección del grafo parte de `peliculas_qdrant` y exige que exista una valoración.
Las valoraciones y relaciones con géneros se filtran por ese mismo conjunto; no se
aplican filtros adicionales por año, género o identificadores externos.

Para actualizar solo las exportaciones y el informe, sin reconstruir tablas ni
volver a descargar fuentes, abre DuckDB en modo de lectura:

```bash
python scripts/preparar_datos.py --solo-exportar
```

Las consultas académicas están en `scripts/sql/consultas_ejemplo.sql`.

## Carga y búsqueda

Para preparar Qdrant por primera vez o actualizarlo deliberadamente:

```bash
python cargar_movielens.py
```

La carga lee DuckDB y crea `peliculas_e5`: **9.494 películas, 768 dimensiones y
similitud coseno**, con índices sobre `generos` y `anio`. Conserva los IDs y payloads.
Lee lotes de 64 películas y genera embeddings de 8 en 8, adecuados para Apple Silicon
con 16 GB. Al repetirla, solo recalcula puntos ausentes o con metadatos distintos;
comprueba todos los IDs, payloads, dimensiones y normas al terminar. No borra puntos
ni colecciones. La colección anterior `peliculas_v2` se conserva temporalmente intacta
como respaldo. Si E5 ya está cargada, no necesitas repetir este paso.

Carga y consultas comparten [Multilingual E5-base](https://huggingface.co/intfloat/multilingual-e5-base)
(`intfloat/multilingual-e5-base`), con vectores normalizados y un máximo de 512 tokens
(los textos más largos se truncan). El modelo se descarga la primera vez. Los textos
almacenados llevan `passage: `; las búsquedas y las favoritas usadas como consulta
llevan `query: `, tanto en español como en inglés. Las películas se representan mediante
su sinopsis y sus géneros. La similitud coseno no es una probabilidad ni un porcentaje
de acierto; no se aplica un umbral arbitrario.

La carga prepara también los vectores de consulta de las películas y los guarda en
`datos/consultas_e5.sqlite`, una caché local por modelo y texto excluida de Git. Así,
cambiar de perfil no vuelve a codificar sus favoritas. Si falta una entrada, se calcula
cuando se necesita. La colección activa y el modelo se definen en `src/motor.py`.

```bash
python -m streamlit run app.py
python buscar.py "aventuras en el espacio" --genero "Ciencia ficción"
python buscar.py "un viaje en el tiempo" --desde 1990 --hasta 2020 --limite 5
```

Streamlit guarda géneros y años en caché durante cinco minutos, sin descargar
sinopsis para construir los filtros. El intervalo completo incluye películas sin
año; al acotarlo se excluyen. En terminal, omitir `--desde` y `--hasta` incluye todos
los años. `QDRANT_URL` permite cambiar la dirección, por defecto `http://localhost:6333`.

## NebulaGraph y recomendaciones

Se usa NebulaGraph **3.8.0**, con un servicio `metad`, un `storaged` y un `graphd`.
Las tres imágenes oficiales incluyen **linux/arm64**, comprobado en sus manifiestos
y en Docker Desktop sobre Apple Silicon. No hace falta emulación. Véanse el
[despliegue oficial](https://vesoft-inc.github.io/nebula-docker-compose/)
y las [consultas MATCH](https://docs.nebula-graph.io/3.8.0/3.ngql-guide/7.general-query-statements/2.match/).
Los volúmenes `nebula_meta` y `nebula_storage` conservan el grafo. El primer arranque
puede tardar varios minutos; `--wait` espera a que los servicios estén disponibles.

Con los CSV y Qdrant actuales, solo necesitas:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
docker compose up -d --wait
python cargar_nebula.py
python -m streamlit run app.py
```

No hace falta repetir el ETL ni la carga de Qdrant. Si faltan los CSV, ejecuta antes
`python scripts/preparar_datos.py` siguiendo la sección de fuentes.

El importador crea el espacio `moviematch`, sin borrar otros espacios. Comprueba
los CSV antes de escribir y contrasta los datos importados, no solo sus cantidades.
Puede repetirse: los mismos IDs y parejas de relaciones se actualizan sin duplicarse.
La carga normal no elimina registros sobrantes; la validación los detecta.
Para aplicar el filtro al grafo existente:

```bash
python scripts/preparar_datos.py --solo-exportar
python cargar_nebula.py --depurar
```

`--depurar` guarda una copia de los datos actuales en `datos/respaldos_nebula/FECHA/`,
la relee y contrasta antes de borrar. Solo elimina las películas ausentes de los CSV
actuales, junto con sus relaciones entrantes y salientes. No elimina espacios ni
usuarios. La lista exacta queda en `descartadas.json` dentro del respaldo.
La validación final compara registros y estadísticas de almacenamiento para detectar
relaciones huérfanas. No ejecutes otras escrituras al grafo durante la depuración.

La migración descartó 248 películas sin sinopsis válida y 18 con sinopsis pero sin
valoraciones: 266 películas, 592 valoraciones y 546 relaciones con géneros en total.
No había películas sin sinopsis y sin valoraciones simultáneamente.

Para recuperar el estado anterior a esta depuración, sin borrar el espacio:

```bash
python cargar_nebula.py --fuentes datos/respaldos_nebula/FECHA
```

Sustituye `FECHA` por el directorio del respaldo. Esta recuperación repone los registros
eliminados y valida el resultado; no elimina posibles registros añadidos después.
Una operación interrumpida puede recuperarse desde el respaldo antes de repetirla.
Después de cambiar los datos, reinicia Streamlit o espera sus cinco minutos de caché.

El esquema es:

```text
Usuario(userId) --VALORA(puntuacion, fecha)--> Pelicula(movieId, titulo, anio)
Pelicula --PERTENECE_A--> Genero(nombre)
```

Los IDs usan los prefijos `usuario:`, `pelicula:` y `genero:`. Las películas sin
sinopsis válida permanecen únicamente en el catálogo maestro de DuckDB. El `movieId` coincide con el Point ID de Qdrant.
El puerto `9669` se publica solo en localhost; el despliegue local utiliza
`root` / `nebula`. El cliente admite `NEBULA_HOST`, `NEBULA_PORT`, `NEBULA_USER` y
`NEBULA_PASSWORD` mediante variables de entorno. Cambiar la variable de contraseña
no cambia por sí mismo la contraseña almacenada en NebulaGraph.

Reglas de recomendación:

- **Porque te gustó:** favoritas con nota ≥4 presentes en Qdrant. Se consulta cada
  favorita por separado, excluyendo todas las películas ya valoradas. Para cada
  candidata se conserva su mayor similitud y la favorita que la produjo. Se muestran
  las cinco primeras con títulos distintos, excluyendo también títulos ya valorados.
  Cada consulta utiliza el texto de la favorita con `query: ` y su vector en caché;
  no se promedian vectores ni se usa el vector `passage: ` del punto como consulta.
- **A usuarios como tú:** al menos tres favoritas compartidas con nota ≥4 en ambos
  perfiles. Se toman hasta 30 vecinos por número de coincidencias. Cada vecino que
  puntúa una candidata con ≥4 aporta ese número de coincidencias a su puntuación.
  Se excluyen las ya valoradas y se ordena por suma, número de apoyos y nota media.
  Todos los recorridos y agregaciones se ejecutan en NebulaGraph.
- **Géneros favoritos:** media por género con al menos cinco películas valoradas;
  desempate por cantidad. Se muestran hasta cinco, sin rellenar resultados ausentes.
- **Top 10:** media global con al menos 20 valoraciones; desempate por cantidad.

Los resultados se guardan en caché cinco minutos y el perfil seleccionado forma
parte de la clave. No se usan carteles externos: las tarjetas incluyen un marcador
🎬. Las sinopsis colaborativas se recuperan de Qdrant cuando existen; si faltan se
indica expresamente. Si NebulaGraph no está disponible, la búsqueda semántica sigue
funcionando. Los filtros laterales corresponden únicamente al buscador.

## Archivos

- `app.py`, `buscar.py`: interfaz y terminal.
- `src/motor.py`: búsqueda, metadatos y recomendaciones de contenido en Qdrant.
- `src/grafo.py`: consultas nGQL y conexión con NebulaGraph.
- `cargar_movielens.py`, `cargar_nebula.py`: importadores de cada base de datos.
- `scripts/preparar_datos.py`, `scripts/sql/`: integración y consultas SQL.

Los datasets y las bases locales están excluidos de Git.
