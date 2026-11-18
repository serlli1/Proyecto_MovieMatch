# Consultas y recomendaciones

Aquí está la **lógica de acceso a Qdrant y NebulaGraph** que comparten la interfaz, el buscador de terminal y los cargadores. Son módulos que normalmente se **importan**, no programas que haya que ejecutar directamente.

| Archivo | Función |
|---|---|
| `motor.py` | Conecta con Qdrant, carga el modelo multilingüe E5, convierte textos en vectores, reutiliza consultas en caché SQLite, busca películas por significado con filtros y genera recomendaciones basadas en contenido. |
| `grafo.py` | Conecta con NebulaGraph y ejecuta consultas de usuarios, perfiles de valoraciones, Top 10, géneros favoritos y recomendaciones colaborativas. |
| `__init__.py` | Marca `consultas` como paquete Python. |

**Cómo encajan:** `aplicacion/app.py` y `aplicacion/buscar.py` llaman a estas funciones para mostrar resultados. Los archivos de `cargas/` también las reutilizan para conectarse a las bases.
