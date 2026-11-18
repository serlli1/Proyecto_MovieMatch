# Aplicación

Esta carpeta contiene las **dos formas de buscar películas en MovieMatch**: la interfaz web y la terminal. Ambas utilizan las funciones de `consultas/` y no cargan las bases de datos desde cero.

| Archivo | Función |
|---|---|
| `app.py` | Interfaz web con Streamlit: búsqueda por sinopsis, filtros, Top 10, perfiles y recomendaciones de películas. |
| `buscar.py` | Buscador por terminal: recibe una descripción y filtros opcionales, y muestra las películas más similares de Qdrant. |
| `__init__.py` | Marca `aplicacion` como paquete Python para poder ejecutar sus módulos. |

Desde la **raíz del repositorio**, con el entorno virtual activado y los servicios preparados:

```bash
python -m streamlit run aplicacion/app.py --server.address 127.0.0.1
python -m aplicacion.buscar "aventuras en el espacio" --limite 5
```

La búsqueda y las recomendaciones se apoyan en Qdrant y NebulaGraph; sus funciones están en `consultas/`.
