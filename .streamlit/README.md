# Configuración de Streamlit

Carpeta de configuración de la interfaz web de MovieMatch.

| Archivo | Función |
|---|---|
| `config.toml` | Establece `server.fileWatcherType = "none"` para desactivar la vigilancia automática de cambios de archivos de Streamlit. |

La aplicación se inicia desde la raíz del repositorio con:

```bash
python -m streamlit run aplicacion/app.py --server.address 127.0.0.1
```

Esta carpeta **no** contiene las consultas ni la lógica de recomendación: están en `consultas/` y `aplicacion/`.
