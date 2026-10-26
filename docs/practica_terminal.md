# Práctica de terminal: MovieMatch

**Objetivo:** observar cómo un catálogo integrado en DuckDB se consulta como vectores
en Qdrant y como relaciones en NebulaGraph. Entrega los comandos, una muestra de
salida y tus respuestas. No hace falta copiar sinopsis ni vectores completos.

## Parte A. Instalación guiada

Sigue las once etapas del [README](../README.md), sin saltarlas ni agruparlas en un
script. Necesitas Git, Python 3.11, Docker Desktop con Compose e Internet.

| Etapa | Evidencia que debes guardar | Pregunta |
|---|---|---|
| Herramientas y clon | Versiones y directorio del proyecto | ¿Qué diferencia hay entre Git y Python? |
| Entorno virtual | Ruta de `sys.executable` y `pip check` | ¿Por qué instalar dentro de `.venv`? |
| Servicios y registro | `docker compose ps` y mensaje de host ONLINE | ¿Por qué no esperar primero a `storaged`? |
| Fuentes y ETL | Rutas, informe y recuentos | ¿Por qué se conservan más películas en DuckDB? |
| Cargas | Resúmenes de Qdrant y NebulaGraph | ¿Qué representa cada ID? |
| Interfaz | Búsqueda y cambio de perfil | ¿Qué base resuelve cada bloque de la pantalla? |

A partir de aquí, las bases deben estar cargadas. Todos los comandos se ejecutan
desde `Proyecto_MovieMatch`, con `.venv` activado. Los bloques `text` sirven tanto
en Bash/zsh como en PowerShell: no incluyen continuaciones de línea propias de un sistema.
Si PowerShell restringe la activación, usa la alternativa del README.

## Parte B. Experimentación

### 1. Identificar las fuentes

```text
python -c "from pathlib import Path; import hashlib; carpeta=Path('datos/fuentes/ml-latest-small'); print('\n'.join(nombre+': '+hashlib.sha256((carpeta/nombre).read_bytes()).hexdigest() for nombre in ['movies.csv','links.csv','ratings.csv']))"
python -c "from pathlib import Path; import hashlib; print(hashlib.md5(Path('datos/fuentes/movies_metadata.csv').read_bytes()).hexdigest())"
```

MovieLens de referencia:

```text
movies.csv: 5a5f32dd9bb3797b8e728a1b98958789d2b13f294a69fdfbc5727f8a9611aa07
links.csv: 97ad18e4e56a09363c65676b6cb3482ce3e2cea2372a24620c1599c843325f31
ratings.csv: aa289ca83157595d0df6aea1be6a4ded676ddc4385472e8313a8ed9805352646
```

TMDB: `42bf3ef8c208a01a4776955875978b1e` (MD5 publicado en Zenodo).
Estos comandos solo leen archivos. El enlace MovieLens «latest» puede cambiar;
si una huella difiere, identifica la versión antes de comparar resultados.
**Pregunta:** ¿un checksum comprueba integridad o relevancia de las sinopsis?

### 2. Distinguir procesos y bases preparadas

```text
docker compose ps
docker compose exec -T graphd ls -lah /logs
python -c "from src.motor import cliente; db=cliente(); print(db.get_collections()); db.close()"
python -c "from src.grafo import usuarios; print('Usuarios:',len(usuarios()))"
```

Esperado: cuatro servicios, archivos de registro internos de NebulaGraph,
colección `peliculas_e5` y 610 usuarios.
En una instalación nueva no tiene por qué existir `peliculas_v2`.
**Pregunta:** ¿un contenedor encendido garantiza que sus datos ya se han importado?

### 3. Consultar DuckDB en modo de lectura

```text
python -c "import duckdb; con=duckdb.connect('datos/moviematch.duckdb',read_only=True); print(con.sql('SELECT count(*) AS peliculas, count(sinopsis) AS con_sinopsis FROM peliculas')); con.close()"
python -c "import duckdb; from pathlib import Path; con=duckdb.connect('datos/moviematch.duckdb',read_only=True); print(con.execute(Path('scripts/sql/consultas_ejemplo.sql').read_text(encoding='utf-8')).fetchall()); con.close()"
```

La primera consulta debe devolver 9.742 y 9.494. El segundo comando ejecuta las
consultas académicas existentes y muestra **el resultado de la última**, cinco
películas con mejores notas entre las que tienen al menos 30 valoraciones.
Lee el archivo SQL para identificar las anteriores.
**Pregunta:** ¿por qué ese conjunto no equivale al Top 10 del grafo?

### 4. Contar e inspeccionar Qdrant

```text
python -c "from src.motor import cliente, COLECCION; db=cliente(); print(db.count(COLECCION,exact=True)); info=db.get_collection(COLECCION); print(info.config.params.vectors); print(info.config.hnsw_config); print(info.payload_schema); db.close()"
```

Esperado: 9.494 puntos, tamaño 768, distancia Cosine, configuración HNSW e índices
`generos` (keyword) y `anio` (integer). Ver una configuración HNSW no demuestra que
toda consulta lo utilice: el plan también depende del tamaño y de los filtros.
**Pregunta:** ¿qué diferencia hay entre un índice vectorial y uno de metadatos?

### 5. Recuperar una película por su ID

```text
python -c "from src.motor import obtener_peliculas; from pprint import pprint; pprint(obtener_peliculas([1]))"
```

Esperado: ID 1, Toy Story, año, géneros, sinopsis, `tmdbId` e `imdbId`.
**Pregunta:** ¿el Point ID es un identificador TMDB o MovieLens?

### 6. Buscar por significado

```text
python buscar.py "Un hombre descubre que vive en una realidad simulada" --limite 3
python buscar.py "A man discovers that his reality is a computer simulation" --limite 3
```

Obtendrás hasta tres películas con sinopsis y similitud; no se exige un orden fijo
entre idiomas. Las consultas usan `query: `; los documentos se cargaron con `passage: `.
**Pregunta:** ¿por qué una similitud de 0,84 no significa un 84 % de acierto?

### 7. Comparar filtros y parámetros

```text
python buscar.py "aventuras en el espacio" --limite 5
python buscar.py "aventuras en el espacio" --genero "Ciencia ficción" --limite 5
python buscar.py "aventuras en el espacio" --desde 1990 --hasta 2010 --limite 5
python buscar.py "aventuras en el espacio" --genero "Ciencia ficción" --desde 1990 --hasta 2010 --limite 3
```

Comprueba géneros, años y número de resultados. Los límites de año son inclusivos;
las películas sin año quedan fuera cuando se restringe el intervalo.
**Pregunta:** ¿el filtro cambia el texto vectorizado o las candidatas recuperables?

### 8. Crear una película de prueba aislada

```text
python scripts/practica_qdrant.py crear
python scripts/practica_qdrant.py ver
```

Se crea **solo** `moviematch_practica` y su punto 1, «PRUEBA — La misión del aula»,
con `es_prueba: true`. No es un `movieId` real y no se añade a DuckDB ni al grafo.
La herramienta fija el destino y no permite elegir `peliculas_e5` ni `peliculas_v2`.
Genera un único embedding E5 con la configuración del proyecto. Si repites `crear`,
rechaza sobrescribir el punto existente. Una colección con configuración incompatible
o un punto 1 sin marca de prueba tampoco se modifica.
**Pregunta:** ¿por qué el ID 1 puede coexistir con Toy Story sin reemplazarlo?

### 9. Buscar la prueba y actualizar sus metadatos

```text
python scripts/practica_qdrant.py buscar --texto "Una expedición espacial busca un planeta habitable"
python scripts/practica_qdrant.py actualizar --anio 2030
python scripts/practica_qdrant.py ver
python scripts/practica_qdrant.py buscar --texto "Una expedición espacial busca un planeta habitable"
```

Esperado: se recupera la película y el año pasa de 2026 a 2030. El año no forma parte
del texto vectorizado, por lo que esta actualización no requiere otro embedding.
**Pregunta:** ¿ocurriría lo mismo al modificar la sinopsis?

### 10. Revertir la escritura

```text
python scripts/practica_qdrant.py eliminar
python scripts/practica_qdrant.py ver
python scripts/practica_qdrant.py buscar
python -c "from src.motor import cliente, COLECCION; db=cliente(); print(db.count(COLECCION,exact=True)); db.close()"
```

Esperado: `[]`, cero resultados en la colección de prueba y **9.494** puntos en el
catálogo. Solo se elimina el punto de prueba; la colección vacía permanece y puede
reutilizarse. Si interrumpes el ejercicio, ejecuta `eliminar` cuando puedas continuar.
**Pregunta:** ¿qué se perdería si borrases una colección completa en lugar de un punto?

### 11. Consultar usuarios, valoraciones y recomendaciones

```text
python -c "from src import grafo; from pprint import pprint; print(grafo.usuarios()[:10]); pprint(grafo.perfil(1)[:5])"
python -c "from src import grafo; from pprint import pprint; perfil=grafo.perfil(1); pprint(grafo.colaborativas(1,perfil))"
python -c "from src import grafo; from src.motor import recomendar_contenido; from pprint import pprint; pprint(recomendar_contenido(grafo.perfil(1)))"
```

Compara usuario 1 y usuario 2. Las colaborativas usan hasta 30 vecinos con al menos
tres favoritas compartidas (nota ≥4), excluyen lo valorado y devuelven hasta cinco.
El contenido consulta Qdrant con favoritas reales y conserva el motivo individual.
**Pregunta:** ¿qué parte del cálculo se ejecuta en cada base?

### 12. Explorar el grafo con nGQL

Abre `python` en la terminal. Pega este bloque Python, incluida la línea en blanco
que termina el `with` antes de `exit()`. No pegues indicadores `>>>` ni el delimitador
Markdown. Funciona igual en el intérprete de macOS y de Windows.

```python
from src.grafo import conectar, ejecutar
from pprint import pprint
with conectar() as sesion:
    pprint(ejecutar(sesion, 'SHOW HOSTS'))
    pprint(ejecutar(sesion, 'SHOW STATS'))
    pprint(ejecutar(sesion, 'MATCH (u:Usuario)-[v:VALORA]->(p:Pelicula)-[:PERTENECE_A]->(g:Genero) WHERE id(u) == "usuario:1" RETURN p.Pelicula.titulo AS titulo, v.puntuacion AS nota, g.Genero.nombre AS genero LIMIT 10'))

exit()
```

Esperado: `storaged:9779` ONLINE, 10.105 vértices y 121.748 aristas en las estadísticas
calculadas por el cargador; después, diez caminos usuario–película–género. Una película
puede aparecer varias veces si tiene varios géneros. `SHOW STATS` muestra el último
cálculo, no un recuento actualizado automáticamente tras cualquier escritura.
El recorrido parte del VID `usuario:1`; no necesita crear un índice de propiedades.
**Pregunta:** ¿en qué se distingue una fila de esta consulta de una valoración única?

### 13. Top 10 y preferencias

```text
python -c "from src import grafo; from pprint import pprint; pprint(grafo.top_comunidad()); pprint(grafo.generos_favoritos(1))"
```

El Top 10 requiere al menos 20 valoraciones por película; los géneros favoritos,
al menos cinco películas valoradas en ese género. Son reglas de consulta, no filtros
de eliminación del catálogo.
**Pregunta:** ¿por qué no ordenar únicamente por la nota de una sola valoración?

### 14. Medir sin confundir los tiempos

```text
python scripts/medir_rendimiento.py --repeticiones 6
```

Guarda primera llamada, media y mediana. El script separa generación/recuperación
del embedding, petición a Qdrant y búsqueda completa. Las funciones del grafo
incluyen conexión y procesamiento Python; no son tiempos internos del servidor.
No borra índices ni cambia las bases. La variación entre perfiles depende del historial.
**Pregunta:** ¿puedes atribuir una mejora a un índice sin comparar con y sin él?

### 15. Terminar y volver a abrir

Detén Streamlit con `Ctrl+C` si lo tienes abierto, y ejecuta `docker compose stop`.
Repite el arranque habitual de la etapa 11 del README; comprueba que siguen las
9.494 películas y los 610 usuarios. No repitas el ETL ni las cargas.
**Pregunta:** ¿qué se guarda en los volúmenes Docker y qué archivos quedan en `datos/`?

## Comprobaciones y ensayo del alumno

Validado el **26 de octubre de 2026 en macOS, con Python 3.11 y Docker Desktop**:

- Descarga HTTPS de las fuentes, verificación de sus hashes y ejecución real del ETL.
- Primer arranque de NebulaGraph con almacenamiento vacío en contenedores aislados:
  espera de Graph Service, registro ONLINE y segundo registro sin duplicados. Se retiraron
  solo esos contenedores temporales, sin tocar los servicios ni volúmenes habituales.
- Todos los comandos Python de los ejercicios, incluido el recorrido nGQL, las búsquedas,
  recomendaciones, métricas con seis repeticiones y el ciclo CRUD completo. La colección
  `moviematch_practica` quedó vacía; el catálogo E5 conservó sus 9.494 películas.
- Comparación completa de IDs, payloads y vectores Qdrant con DuckDB, y del grafo con
  sus CSV y estadísticas. No se volvieron a importar películas ni relaciones del catálogo.
- Compilación, `pip check`, opciones CLI, enlaces locales y `git diff --check`.
  Pruebas puntuales de rechazo de certificados y protección de puntos no marcados como prueba.

No se ejecutó una instalación limpia completa de herramientas y dependencias, ni se
repitió la generación masiva de embeddings. Windows/PowerShell y las descargas mediante
su navegador/`Expand-Archive` se revisaron documentalmente, **no se ejecutaron** aquí.
Los ejercicios de parada se dejan al alumno para no interrumpir los servicios habituales.

**macOS:** probar instalación de herramientas en un equipo sin preparar, clon nuevo,
creación/activación de `.venv`, instalación de requisitos, descarga y descompresión,
HTTPS de Zenodo, secuencia de registro, ETL, cargas iniciales, Streamlit y persistencia
tras detener y arrancar. Los comandos operativos se verifican en el Mac de desarrollo;
eso no sustituye una instalación limpia completa.

**Windows (PowerShell):** probar además el lanzador `py -3.11`, activación con la
política del centro (o Python directo), rutas de Descargas, `Expand-Archive`, backend
Linux/WSL 2, certificados corporativos y visualización de acentos. Repetir las etapas
y los ejercicios en un equipo Windows real antes de distribuir el PDF definitivo.
