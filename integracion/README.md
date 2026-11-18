# Integración de datos (ETL con DuckDB)

Esta carpeta prepara el catálogo común de MovieMatch a partir de los CSV de **MovieLens Latest Small y TMDB**. El resultado se guarda en DuckDB y se exporta para las cargas posteriores de Qdrant y NebulaGraph.

| Archivo | Función |
|---|---|
| `preparar_datos.py` | Comprueba que existen los CSV, verifica la integridad del fichero TMDB mediante su checksum, ejecuta el SQL, valida las tablas, exporta los conjuntos preparados y genera `datos/reporte_etl.json`. |
| `preparar_catalogo.sql` | Contiene las operaciones SQL: importar CSV, limpiar campos, relacionar MovieLens con TMDB, seleccionar sinopsis válidas y construir tablas de películas, usuarios, valoraciones y géneros. |
| `__init__.py` | Marca `integracion` como paquete Python. |

Desde la **raíz del repositorio**:

```bash
python -m integracion.preparar_datos
```

Los CSV originales deben haberse descargado manualmente en `datos/fuentes/`; este programa **no los descarga**. La ejecución normal reconstruye las tablas locales de DuckDB. Si la base ya existe y solo se necesitan de nuevo las exportaciones:

```bash
python -m integracion.preparar_datos --solo-exportar
```

Esta etapa no inserta datos directamente en Qdrant ni en NebulaGraph: de eso se ocupa `cargas/`.
