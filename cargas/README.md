# Carga de las bases de datos

Estos programas trasladan a las bases especializadas los datos **ya preparados por DuckDB** en `integracion/`. Se usan durante la instalación o cuando hay que actualizar una carga; **no hay que repetirlos para abrir la aplicación cada día**.

| Archivo | Función |
|---|---|
| `cargar_movielens.py` | Lee `datos/moviematch.duckdb`, crea o comprueba la colección de Qdrant, genera embeddings E5 de las películas pendientes, las inserta por lotes y valida los resultados. |
| `cargar_nebula.py` | Lee los CSV de `datos/procesados/`, prepara el esquema del grafo, importa usuarios, películas, valoraciones y géneros, y comprueba la carga en NebulaGraph. También permite registrar los hosts de almacenamiento. |
| `__init__.py` | Marca `cargas` como paquete Python. |

Comandos desde la **raíz del repositorio**:

```bash
python -m cargas.cargar_movielens
python -m cargas.cargar_nebula
```

Para registrar los hosts durante la preparación inicial de NebulaGraph:

```bash
python -m cargas.cargar_nebula --registrar-hosts
```

**Atención:** la opción `--depurar` de NebulaGraph realiza mantenimiento de datos con respaldo previo; no forma parte del arranque habitual. Consulta el README principal antes de utilizarla.
