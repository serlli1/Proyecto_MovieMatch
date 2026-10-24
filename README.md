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

La edición de referencia es **Latest Small de septiembre de 2018** ([GroupLens](https://www.grouplens.org/datasets/movielens/)).
El enlace «latest» puede cambiar y no es un archivo de versiones inmutables. Estas
huellas SHA-256 identifican exactamente los CSV usados en esta entrega:

<details>
<summary>Huellas de las fuentes MovieLens</summary>

```text
movies.csv: 5a5f32dd9bb3797b8e728a1b98958789d2b13f294a69fdfbc5727f8a9611aa07
links.csv: 97ad18e4e56a09363c65676b6cb3482ce3e2cea2372a24620c1599c843325f31
ratings.csv: aa289ca83157595d0df6aea1be6a4ded676ddc4385472e8313a8ed9805352646
```

</details>

El ETL descarga `movies_metadata.csv` del [depósito de Zenodo](https://zenodo.org/records/18099452)
si falta en `datos/fuentes/`, y comprueba el MD5 de la descarga. También puedes aportar
un CSV ya descargado mediante `--metadata /ruta/movies_metadata.csv`.
Es una copia de metadatos de [TMDB](https://developer.themoviedb.org/docs/getting-started),
no una consulta a su API: no se necesita clave. Referencia estable de la copia:
[DOI 10.5281/zenodo.18099452](https://doi.org/10.5281/zenodo.18099452),
MD5 `42bf3ef8c208a01a4776955875978b1e`.

```bash
python scripts/preparar_datos.py
```

Este comando reconstruye las tablas de `datos/moviematch.duckdb` dentro de una
transacción y actualiza las exportaciones y `datos/reporte_etl.json`. No hace falta
repetirlo para buscar si ya dispones del catálogo preparado. El JOIN utiliza
`tmdbId`, descarta IMDb incompatibles y resuelve coincidencias duplicadas priorizando
IMDb, año y sinopsis. Conserva controles de claves, valoraciones y relaciones;
las filas de TMDB con errores de lectura se omiten. Una sinopsis válida tiene al
menos 40 caracteres tras normalizar espacios y no es un marcador de ausencia.
Este criterio se aplica una sola vez en el SQL y se reutiliza para ambas bases.

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

**Mantenimiento:** la reanudación compara payloads, no detecta cambios de estrategia.
La representación de `peliculas_e5` queda fijada por el modelo, sinopsis + géneros,
prefijos, normalización y límite de 512 tokens. Si se cambia alguno, se debe preparar
otra colección y otra ruta `CACHE_CONSULTAS`, validarlas antes de activar la nueva
configuración y conservar las anteriores. No reutilizar esta colección o caché
esperando que el cargador detecte ese cambio; no hay recodificación masiva automática.

Carga y consultas comparten [Multilingual E5-base](https://huggingface.co/intfloat/multilingual-e5-base)
(`intfloat/multilingual-e5-base`), con vectores normalizados y un máximo de 512 tokens
(los textos más largos se truncan). El modelo se descarga la primera vez. Los textos
almacenados llevan `passage: `; las búsquedas y las favoritas usadas como consulta
llevan `query: `, tanto en español como en inglés. Las películas se representan mediante
su sinopsis y sus géneros. La similitud coseno no es una probabilidad ni un porcentaje
de acierto; no se aplica un umbral arbitrario. E5 es la elección definitiva tras
una evaluación cualitativa manual que produjo resultados más relevantes; no se ha
medido una mejora estadística ni se atribuyen porcentajes de precisión.

La carga prepara también los vectores de consulta de las películas y los guarda en
`datos/consultas_e5.sqlite`, una caché local por modelo y texto excluida de Git. Así,
cambiar de perfil no vuelve a codificar sus favoritas. Si falta una entrada, se calcula
cuando se necesita. La colección activa y el modelo se definen en `src/motor.py`.

```bash
python -m streamlit run app.py --server.address 127.0.0.1
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

En un **clon nuevo**, las bases y los CSV no están incluidos. Tras preparar el entorno,
arrancar Docker y ubicar las fuentes como se explica arriba, ejecuta en este orden:

```bash
python scripts/preparar_datos.py
python cargar_movielens.py
python cargar_nebula.py
python -m streamlit run app.py --server.address 127.0.0.1
```

Con las bases ya cargadas, el arranque habitual es únicamente:

```bash
source .venv/bin/activate
docker compose up -d --wait
python -m streamlit run app.py --server.address 127.0.0.1
```

No repitas el ETL ni los importadores para iniciar la aplicación. Si solo faltan las
exportaciones y DuckDB existe, usa `python scripts/preparar_datos.py --solo-exportar`.

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
`root` / `nebula`, credenciales solo para la práctica local, inadecuadas para
un despliegue público. El cliente admite `NEBULA_HOST`, `NEBULA_PORT`, `NEBULA_USER` y
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

## Validación y resultados (24 de octubre de 2026)

Auditoría sobre las bases locales: claves únicas y válidas, escala de notas, referencias,
ausencia de duplicados y de relaciones huérfanas. Se contrastaron todos los IDs,
payloads y vectores E5 (768 dimensiones y norma unitaria), los CSV y el grafo,
incluido `SHOW STATS`: **10.105 vértices y 121.748 aristas**. Las cifras del inicio
quedaron confirmadas; DuckDB y los datos de ambas colecciones y del grafo se conservaron.

Se comprobaron búsquedas en español e inglés, filtros separados y combinados, límites
y consultas vacías; recomendaciones con los perfiles 1, 2, 414, 442 y 610, favoritas
ausentes y perfiles vacíos. Un cálculo independiente sobre los CSV coincidió con
vecinos, afinidad, apoyos, ordenación, Top 10 y géneros de NebulaGraph. El perfil 442
no tiene favoritas con nota ≥4 y devuelve correctamente cero recomendaciones.
Streamlit pasó las comprobaciones con `AppTest`: pestañas, cambio de perfil, filtros,
años sin duplicar y errores desplegables. Se simularon conexiones rechazadas sin
parar servicios; la parte de la aplicación que usa la otra base siguió funcionando.

El ETL se reprodujo **en memoria** a partir de las fuentes locales y sus cinco
exportaciones temporales coincidieron con las actuales. Se validaron dependencias
(`pip check`), configuración de Docker, SQL de ejemplo, CLI y arranque HTTP de
Streamlit en localhost. No se ejecutó una instalación desde cero con nuevas descargas
y volúmenes vacíos, ni una revisión visual
en navegador: la validación de interfaz se realizó con `AppTest`.

Ejemplos reales, respetando el texto y las mayúsculas de la consulta:

| Consulta | Primeros tres resultados |
|---|---|
| Un hombre descubre que vive en una realidad simulada | World on a Wire (Welt am Draht); Anomalisa; Man with the Movie Camera, The (Chelovek s kino-apparatom) |
| Una familia lucha por sobrevivir a una invasión de zombis | Land of the Dead; Wyrmwood; Dawn of the Dead |
| Una expedición espacial para salvar a la humanidad | Voyage to the Bottom of the Sea; Sunshine; Absolutely Anything |
| a man discovers that his reality is a computer simulation | Thirteenth Floor, The; World on a Wire (Welt am Draht); Man of the Year |

Hay coincidencias temáticas útiles y resultados menos precisos; estos ejemplos no
constituyen una medida de precisión. No se repitió la comparación con MiniLM.

Para repetir las mediciones sin cambiar las bases ni los índices:

```bash
python scripts/medir_rendimiento.py --repeticiones 6
```

Mac Apple Silicon, 16 GB, macOS 15.5, Python 3.11.17, E5 en MPS. Tres consultas
(las primeras de la tabla) y perfiles 1, 2 y 610, alternados dos veces en seis
repeticiones por operación. Sin caché de resultados de Streamlit. Tiempos en **ms**:

| Operación | Primera | Media posterior | Mediana | Mín.–máx. |
|---|---:|---:|---:|---:|
| Generar query E5, modelo cargado | 1089,55 | 43,98 | 14,48 | 13,48–191,81 |
| Recuperar query SQLite | 0,28 | 0,25 | 0,25 | 0,24–0,26 |
| Qdrant sin filtros, vector preparado | 40,15 | 8,73 | 8,53 | 7,84–10,06 |
| Qdrant con género y año, vector preparado | 11,42 | 4,76 | 4,67 | 3,21–7,24 |
| Búsqueda completa sin filtros, query en caché | 18,18 | 18,08 | 17,95 | 17,19–19,60 |
| Búsqueda completa con filtros, query en caché | 16,56 | 16,46 | 16,44 | 14,95–18,04 |
| Recuperar tres películas por ID | 16,38 | 15,03 | 14,78 | 14,02–16,89 |
| Contenido, perfil preparado | 613,95 | 854,78 | 525,65 | 64,25–2204,01 |
| Nebula: Top 10 | 425,00 | 363,67 | 358,41 | 305,62–437,10 |
| Nebula: perfil | 14,71 | 19,91 | 13,25 | 8,24–41,00 |
| Nebula: colaborativas, perfil preparado | 123,94 | 132,15 | 125,09 | 69,68–198,97 |
| Nebula: géneros favoritos | 17,38 | 18,73 | 13,29 | 9,41–33,10 |

La carga inicial del modelo desde disco tardó **8,044 s**; no está incluida en la
inferencia de la tabla. Tras calentar el modelo, generar y guardar cada una de las
tres consultas en una caché temporal vacía tardó 18,15, 14,76 y 16,54 ms.
«Primera» es la primera llamada medida de cada operación, no un servidor recién
arrancado. Las filas Qdrant con vector preparado usan una conexión reutilizada;
incluyen transporte y deserialización. Las funciones completas incluyen creación de
conexión y procesamiento Python; las de contenido y colaborativas excluyen obtener
el perfil, ya preparado. El contenido utiliza la caché persistente de favoritas.
Los tiempos dependen del historial y del estado del equipo. No se midió el efecto
causal de los índices: la diferencia entre búsquedas filtradas y no filtradas no
permite atribuirles una mejora de rendimiento.

## Limitaciones

El resultado depende del catálogo y de la calidad de sus sinopsis, principalmente
en inglés; E5 trunca a 512 tokens. Las preferencias y vecinos se limitan a los
usuarios de MovieLens. Las películas sin historial pueden aparecer por contenido,
pero no disponen de señal colaborativa; un usuario sin favoritas no recibe
recomendaciones por contenido. La similitud coseno no es una probabilidad.

## Referencias técnicas

Fuentes y modelo enlazados en sus secciones. Documentación adicional:
[DuckDB: CSV](https://duckdb.org/docs/stable/data/csv/overview),
[Qdrant: índices](https://qdrant.tech/documentation/manage-data/indexing/),
[NebulaGraph: MATCH](https://docs.nebula-graph.io/3.8.0/3.ngql-guide/7.general-query-statements/2.match/)
y [Streamlit: AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).

## Archivos

- `app.py`, `buscar.py`: interfaz y terminal.
- `src/motor.py`: búsqueda, metadatos y recomendaciones de contenido en Qdrant.
- `src/grafo.py`: consultas nGQL y conexión con NebulaGraph.
- `cargar_movielens.py`, `cargar_nebula.py`: importadores de cada base de datos.
- `scripts/preparar_datos.py`, `scripts/sql/`: integración y consultas SQL.
- `scripts/medir_rendimiento.py`: mediciones reproducibles con `perf_counter`.

Los datasets y las bases locales están excluidos de Git.
