# MovieMatch — búsqueda semántica de películas con Qdrant

Proyecto educativo para la asignatura **Agregación y Presentación de Datos en IoT**.

## Objetivo

Comparar una búsqueda basada en coincidencia de palabras con una búsqueda semántica que emplea **Sentence Transformers** y **Qdrant**. La base de datos almacena vectores de 384 dimensiones y metadatos de películas. No hace falta utilizar servicios de pago ni modelos de lenguaje generativos.

**Este repositorio es un prototipo inicial**, no la entrega final de la asignatura. Incluye 38 películas con sinopsis breves escritas específicamente para la demostración. Para un proyecto final conviene aumentar el catálogo y medir la calidad de las búsquedas.

## Requisitos

- Docker Desktop funcionando.
- Python 3.10 o superior (recomendado Python 3.11 o 3.12).
- Conexión a Internet la primera vez para descargar la imagen de Qdrant y el modelo de embeddings.

## 1. Levantar la base de datos

Desde la carpeta del proyecto:

```bash
docker compose up -d
```

Abre el panel de Qdrant: http://localhost:6333/dashboard

La API responde en http://localhost:6333 . Los datos de Qdrant se conservan en un volumen Docker, incluso si se detiene el contenedor.

## 2. Crear un entorno Python

En macOS o Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

La primera importación del modelo puede descargar varios cientos de MB. Conviene hacerla **antes de la práctica en clase**.

## 3. Crear y poblar la colección

```bash
python cargar.py
```

El programa genera un embedding por película y lo almacena junto a su título, año, géneros y sinopsis. Si la colección ya existe, actualiza los IDs del catálogo original sin borrar las películas añadidas manualmente.

## 4. Hacer búsquedas semánticas

```bash
python buscar.py "una persona descubre que vive en una simulación"
python buscar.py "un viaje en el tiempo que cambia el pasado" --genero "Ciencia ficción"
python buscar.py "aventuras en el espacio" --desde 2010 --hasta 2020
```

El resultado muestra títulos, sinopsis y una **puntuación de similitud**. No debe interpretarse como probabilidad de acierto.

## 5. Comparar búsquedas

```bash
python comparar.py "un hombre atrapado en una realidad falsa"
```

La comparación de palabras de `comparar.py` es deliberadamente básica, para ilustrar el concepto: **no** es una implementación de BM25 ni de un motor de texto completo.

## 6. Insertar una película propia

```bash
python agregar.py \
  --titulo "Viaje imposible" \
  --anio 2026 \
  --generos "Ciencia ficción,Aventura" \
  --sinopsis "Una exploradora cruza un portal temporal y busca la manera de regresar a su época."
```

## Parar / reiniciar

```bash
docker compose stop
docker compose start
docker compose down
```

Para borrar el volumen y **eliminar todas las películas almacenadas**:

```bash
docker compose down -v
```

## Organización

- `docker-compose.yml`: servidor Qdrant.
- `datos/peliculas.json`: catálogo de ejemplo en español.
- `src/motor.py`: funciones reutilizables; una futura interfaz Streamlit puede invocarlas directamente.
- `cargar.py`: crea y carga la colección.
- `buscar.py`: búsqueda y filtros.
- `agregar.py`: nueva película introducida por el usuario.
- `comparar.py`: baseline léxica para la comparación.
- `practica_borrador.md`: actividad prevista de 20 minutos.

## Notas técnicas y limitaciones

- Modelo: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dimensiones).
- Métrica: distancia coseno.
- El mismo modelo se utiliza para insertar y consultar.
- Todos los componentes funcionan localmente después de las descargas iniciales.
- El modelo puede equivocarse; para evaluar la relevancia habrá que crear un conjunto de consultas con resultados esperados y probar con un catálogo más grande.
- El servidor solo se publica en `127.0.0.1` y no tiene autenticación: **no se debe exponer directamente a Internet**.
- La imagen de Qdrant está fijada a la versión `v1.19.2` para facilitar la reproducibilidad. Al cerrar el proyecto hay que fijar también versiones de dependencias Python.
