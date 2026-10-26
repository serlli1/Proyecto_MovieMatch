# MovieMatch 🎬

## 1. Qué vamos a construir

Práctica de **Agregación y Presentación de Datos en IoT**: una aplicación que busca
películas por su historia y recomienda títulos según preferencias de MovieLens.
**El alumno ejecuta y entiende cada etapa; los scripts automatizan el trabajo repetitivo de cada una.**

| Componente | Función |
|---|---|
| MovieLens y metadatos TMDB | Catálogo, valoraciones, identificadores y sinopsis |
| DuckDB | Integra y limpia los CSV; genera el catálogo maestro y las exportaciones |
| Qdrant | Almacena películas y vectores E5; búsqueda semántica con filtros |
| NebulaGraph | Relaciona usuarios, películas y géneros; calcula recomendaciones colaborativas |
| Streamlit | Dos pestañas: búsqueda y Top 10; recomendaciones y géneros favoritos |

Los datos no vienen incluidos en el clon. Sigue las etapas en orden, desde la raíz
del repositorio. Después podrás realizar los [ejercicios de terminal](docs/practica_terminal.md).

## 2. Requisitos previos

Necesitas Internet para descargar fuentes, imágenes Docker, dependencias y E5.
Reserva espacio para estos archivos y memoria para Docker y el modelo; el proyecto
se ha usado en un Mac con 16 GB. Una CPU sin aceleración compatible tardará más.

**macOS (Terminal):**

- Instala Git siguiendo [Git para macOS](https://git-scm.com/install/mac).
  Si no está disponible, `xcode-select --install` abre la instalación de las herramientas de Apple.
- Instala Python **3.11**, con el paquete de macOS de [Python.org](https://www.python.org/downloads/release/python-3119/).
  Esa página contiene los instaladores tradicionales de 3.11.9; también sirve otra versión 3.11 ya instalada.
- Instala [Docker Desktop para Mac](https://docs.docker.com/desktop/setup/install/mac-install/),
  eligiendo Apple Silicon o Intel según tu equipo. Ábrelo y espera a que arranque el motor.

**Windows (PowerShell):**

- Instala [Git para Windows](https://git-scm.com/install/windows), habilitando su uso desde la terminal.
- Instala Python **3.11 de 64 bits** desde [Python.org](https://www.python.org/downloads/release/python-3119/),
  incluyendo el lanzador `py`. Abre una nueva PowerShell después de instalarlo.
- Instala [Docker Desktop para Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
  con backend WSL 2 y **contenedores Linux**. Sigue los requisitos de Windows y WSL de esa guía.
  Activar WSL o la virtualización puede necesitar permisos de administrador y reinicio;
  los comandos de esta práctica se ejecutan después en una PowerShell normal.

Docker Desktop incluye Compose; no instales el antiguo comando `docker-compose`.
Comprueba en ambos sistemas:

```text
git --version
docker --version
docker compose version
docker info
```

Comprueba Python con `python3.11 --version` en macOS y `py -3.11 --version` en Windows.
Debe indicar `3.11.x`. `docker info` debe mostrar información del servidor, no un error
de conexión. No continúes hasta que las herramientas respondan.

## 3. Clonar el repositorio

Los mismos comandos en Terminal o PowerShell:

```text
git clone https://github.com/serlli1/Proyecto_MovieMatch.git
cd Proyecto_MovieMatch
```

Aquí deben estar `requirements.txt`, `docker-compose.yml` y `app.py`.

## 4. Preparar Python

El entorno `.venv` mantiene las bibliotecas de la práctica separadas del Python global.

**macOS:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

**Windows (PowerShell):**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Si PowerShell bloquea la activación, puedes permitir scripts locales **solo en esa sesión**:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

No requiere elevación ni cambia la política permanente ([documentación de Microsoft](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.security/set-executionpolicy)).
Si una política del centro lo impide, no la eludas: sustituye cada `python` posterior
por `.\.venv\Scripts\python.exe`; activar el entorno es opcional.

**Ambos sistemas, tras activar:**

```text
python --version
python -c "import sys; print(sys.executable)"
python -m pip check
```

El ejecutable debe estar dentro de `.venv`; `pip check` debe responder
`No broken requirements found.` No instales las bibliotecas una a una.

## 5. Arrancar Qdrant y NebulaGraph

Ejecuta cada línea y comprueba que termine correctamente:

```text
docker compose up -d
docker compose up -d --wait metad graphd
python cargar_nebula.py --registrar-hosts
docker compose up -d --wait
docker compose ps
docker ps
```

**El orden importa en el primer arranque.** Primero arrancan todos los procesos,
pero solo se espera a `metad` y `graphd`. El comando Python ejecuta, si es necesario,
`ADD HOSTS "storaged":9779` y espera a que el host esté `ONLINE`. También reintenta
la conexión durante el arranque, porque el estado healthy puede adelantarse al cliente Python. No necesita datasets,
no crea el espacio de películas y no carga registros. Solo entonces se espera a todos
los servicios. No uses `up -d --wait` como primer paso sobre almacenamiento vacío:
`storaged` puede estar esperando precisamente ese registro.

| Servicio | Responsabilidad | Estado esperado al terminar |
|---|---|---|
| `qdrant` | Base vectorial | Up/running (sin healthcheck en este Compose) |
| `metad` | Metadatos y coordinación del grafo | healthy |
| `storaged` | Almacenamiento de vértices y aristas | healthy |
| `graphd` | Consultas y conexión del cliente | healthy |

Si algo falla, revisa `docker compose ps -a`. NebulaGraph escribe parte de sus
registros en archivos internos, por lo que `docker compose logs` puede aparecer vacío.
Para ver los errores de `storaged` en macOS o PowerShell:

```text
docker compose exec -T storaged tail -n 80 /logs/nebula-storaged.ERROR
```

La secuencia puede repetirse: el registro detecta el host existente.
Véanse [Storage Hosts de NebulaGraph](https://docs.nebula-graph.io/3.8.0/4.deployment-and-installation/manage-storage-host/)
y [orden de arranque de Compose](https://docs.docker.com/compose/how-tos/startup-order/).
Qdrant publica `127.0.0.1:6333` y Graph Service `127.0.0.1:9669`.

## 6. Obtener los datasets

### MovieLens: descarga explícita del alumno

Abre [MovieLens Latest Small](https://grouplens.org/datasets/movielens/latest/),
descarga **ml-latest-small.zip** y guárdalo en Descargas. La referencia de esta práctica
es la edición de septiembre de 2018. No elijas el dataset completo.

**macOS**, si está en `~/Downloads`:

```bash
mkdir -p datos/fuentes
unzip "$HOME/Downloads/ml-latest-small.zip" -d datos/fuentes
```

**Windows (PowerShell)**, si está en la carpeta habitual Downloads:

```powershell
New-Item -ItemType Directory -Force datos/fuentes
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\ml-latest-small.zip" -DestinationPath datos/fuentes
```

Si tu navegador usa otra carpeta, sustituye la ruta. También puedes descomprimir
con Finder o el Explorador. Comprueba que no haya una carpeta duplicada intermedia:

```text
datos/fuentes/ml-latest-small/movies.csv
datos/fuentes/ml-latest-small/links.csv
datos/fuentes/ml-latest-small/ratings.csv
```

No hace falta usar `tags.csv`. Las huellas de la edición de referencia y un comando
para compararlas están en la [práctica](docs/practica_terminal.md#1-identificar-las-fuentes).

### Sinopsis TMDB: descarga dentro de la etapa ETL

Al ejecutar la etapa 7, el ETL descargará `movies_metadata.csv` si falta, desde
[Zenodo, DOI 10.5281/zenodo.18099452](https://doi.org/10.5281/zenodo.18099452),
y lo guardará en `datos/fuentes/movies_metadata.csv`. Comprueba el MD5 de la descarga:
`42bf3ef8c208a01a4776955875978b1e`. Se reutiliza si ya existe,
y el ETL comprueba también su integridad cuando se ha descargado manualmente.

Alternativa manual: descarga ese archivo desde Zenodo con el navegador y colócalo
en la misma ruta. Para otra ubicación, utiliza `python scripts/preparar_datos.py --metadata RUTA`
(con la ruta entre comillas si contiene espacios). No se necesita una clave de TMDB:
usamos una copia del dataset, no su API.

La descarga del ETL usa `scripts/https_seguro.py`, con verificación TLS y almacenes
Python, sistema y Mozilla; `truststore` y `certifi` están en `requirements.txt`.
Si todos fallan, revisa fecha/hora y certificados del equipo; ante un proxy del centro,
consulta al administrador. **No desactives SSL ni uses hosts de confianza para eludirlo.**
Este helper cubre Zenodo; las descargas del modelo se gestionan mediante Hugging Face.

## 7. Ejecutar el ETL con DuckDB

```text
python scripts/preparar_datos.py
```

El SQL de `scripts/sql/preparar_catalogo.sql` cruza MovieLens con TMDB por `tmdbId`,
comprueba IMDb cuando está disponible, resuelve coincidencias y normaliza sinopsis y
géneros. Conserva todo el catálogo maestro en `datos/moviematch.duckdb`.

- **DuckDB:** 9.742 películas, 610 usuarios y 100.836 valoraciones.
- **Qdrant:** 9.494 películas con sinopsis válida, tengan o no valoraciones.
- **NebulaGraph:** 9.476 películas con sinopsis válida y al menos una valoración.

La validez de sinopsis se decide una vez en el SQL (texto normalizado, al menos 40
caracteres y no un marcador de ausencia). No se añaden filtros por año ni género.
El ETL valida claves, referencias y notas y genera:

```text
datos/procesados/peliculas_qdrant.parquet
datos/procesados/peliculas_nebula.csv
datos/procesados/usuarios_nebula.csv
datos/procesados/valoraciones_nebula.csv
datos/procesados/peliculas_generos_nebula.csv
datos/reporte_etl.json
```

La consola debe terminar con `ETL completado: 9742 películas, 9494 con sinopsis`.
Consulta el informe con `python -m json.tool datos/reporte_etl.json`.
Las cifras corresponden a las fuentes de referencia; si difieren, investiga la fuente.
Este comando reconstruye las tablas locales: no lo repitas para iniciar la aplicación.
Si solo faltan exportaciones y DuckDB existe, usa `python scripts/preparar_datos.py --solo-exportar`.

## 8. Cargar Qdrant

```text
python cargar_movielens.py
```

Lee DuckDB y genera vectores normalizados con **intfloat/multilingual-e5-base**:
768 dimensiones, coseno, máximo 512 tokens y texto de sinopsis + géneros.
Los documentos llevan `passage: ` y las consultas `query: `. La colección es
`peliculas_e5`; cada Point ID coincide con `movieId`. El payload contiene título,
año, géneros, sinopsis y los identificadores externos. Hay índices `keyword` sobre
`generos` e `integer` sobre `anio`.

La primera ejecución descarga el modelo y genera embeddings en lotes de 8: puede
consumir bastante memoria y tardar, especialmente en CPU. Espera el resumen
`Carga completada: 9494 películas en 'peliculas_e5'`. El cargador verifica IDs,
payloads, dimensiones y normas. Si se interrumpe, repetirlo continúa los puntos
pendientes; no borra colecciones. Comprueba el resultado:

```text
python -c "from src.motor import cliente, COLECCION; db=cliente(); print(db.count(COLECCION, exact=True)); db.close()"
```

También puedes abrir [el panel de Qdrant](http://127.0.0.1:6333/dashboard).
Las consultas de favoritas se guardan en `datos/consultas_e5.sqlite` para reutilizarlas.
Cambiar la representación exige una colección y una caché nuevas; comparar payloads
no detecta cambios de estrategia. En instalaciones previas, `peliculas_v2` se conserva
como respaldo; no es necesaria ni se crea en una instalación nueva.

## 9. Cargar NebulaGraph

```text
python cargar_nebula.py
```

Lee los cuatro CSV y crea el espacio `moviematch`. El cargador vuelve a comprobar
el registro de `storaged`; no depende de una herramienta externa de instalación.

```text
Usuario --VALORA(puntuacion, fecha)--> Pelicula --PERTENECE_A--> Genero
```

Resultado esperado: **9.476 películas, 610 usuarios, 100.244 valoraciones,
19 géneros y 21.504 relaciones película–género**. La carga contrasta registros con
los CSV y actualiza estadísticas para detectar sobrantes o relaciones huérfanas.
Debe finalizar con `Grafo preparado: 9476 películas, 610 usuarios y 100244 valoraciones`.
Comprueba una consulta real:

```text
python -c "from src.grafo import usuarios; print(len(usuarios()))"
```

No uses `--depurar` en la práctica: es una operación de mantenimiento con respaldo,
no un paso de instalación ni una forma de reiniciar la base.

## 10. Abrir Streamlit

```text
python -m streamlit run app.py --server.address 127.0.0.1
```

Abre **http://127.0.0.1:8501**. Prueba una descripción y sus filtros; cambia de perfil
en «Para ti». `Ctrl+C` termina Streamlit. Para los ejercicios de terminal, utiliza
otra terminal con el entorno activado o detén la interfaz.

## 11. Arranques posteriores y cierre

Abre Docker Desktop. Sitúate en el repositorio y activa el entorno:

- macOS: `source .venv/bin/activate`
- PowerShell: `.\.venv\Scripts\Activate.ps1`

Después, en ambos sistemas:

```text
docker compose up -d --wait
python -m streamlit run app.py --server.address 127.0.0.1
```

No repitas descargas, ETL ni cargas. Para terminar: `Ctrl+C` y después:

```text
docker compose stop
deactivate
```

Omite `deactivate` si no activaste el entorno.

`stop` conserva los volúmenes `qdrant_data`, `nebula_meta` y `nebula_storage`.
No borres volúmenes ni uses opciones para eliminarlos. `.gitignore` excluye datasets,
bases, caché y respaldos. Las credenciales `root` / `nebula` son exclusivamente locales.
Las variables opcionales `QDRANT_URL`, `NEBULA_HOST`, `NEBULA_PORT`, `NEBULA_USER` y
`NEBULA_PASSWORD` permiten otras conexiones; la práctica utiliza los valores locales.

## Experimentar y comprobar

Continúa con [la práctica de terminal](docs/practica_terminal.md): consultas,
CRUD aislado, relaciones del grafo y mediciones. Conserva `buscar.py`, los SQL de
`scripts/sql/` y `scripts/medir_rendimiento.py` como herramientas de trabajo.

Las sinopsis son principalmente inglesas; los resultados dependen del catálogo y
las preferencias de MovieLens. La similitud coseno no es una probabilidad. E5 es el
modelo definitivo, seleccionado mediante evaluación cualitativa manual.

Las comprobaciones realizadas y los pasos pendientes de ensayo en cada sistema
se detallan al final de la práctica. No se afirma que una instalación Windows se
haya ejecutado en este Mac.
