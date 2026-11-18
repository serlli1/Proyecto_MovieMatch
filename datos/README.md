# Datos locales de MovieMatch

Esta carpeta guarda los **archivos de entrada y los resultados generados** por el programa. No contiene código Python. La mayoría de sus contenidos están excluidos de Git porque se descargan o reconstruyen localmente.

| Ruta | Contenido |
|---|---|
| `fuentes/ml-latest-small/` | CSV de MovieLens: `movies.csv`, `links.csv` y `ratings.csv`. |
| `fuentes/movies_metadata.csv` | Metadatos y sinopsis de TMDB, descargados manualmente. |
| `moviematch.duckdb` | Base de datos relacional integrada por el ETL. |
| `procesados/` | Exportaciones para las cargas: `peliculas_qdrant.parquet` y los CSV de películas, usuarios, valoraciones y géneros de NebulaGraph. |
| `reporte_etl.json` | Resumen y comprobaciones de la integración. |
| `consultas_e5.sqlite` | Caché local de vectores de consultas E5, para evitar recalcularlos cuando se reutilizan. |
| `respaldos_nebula/` | Respaldos de NebulaGraph, si se realiza una depuración que los necesite. |

Los datos persistentes de **Qdrant y NebulaGraph** se conservan en los volúmenes de Docker definidos en `docker-compose.yml`, no dentro de esta carpeta. No borres estas fuentes o bases locales para ordenar el repositorio.
