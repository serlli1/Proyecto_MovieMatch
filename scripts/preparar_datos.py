#!/usr/bin/env python3
"""MovieMatch: ETL reproducible de MovieLens + metadatos de TMDB con DuckDB.

Ejecutar desde la raíz del repositorio:
    python scripts/preparar_datos.py

Requiere los CSV originales de MovieLens en datos/fuentes/ml-latest-small/.
NO toca Qdrant ni NebulaGraph; produce una base DuckDB y exportaciones.
"""

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "datos"
FUENTES = DATOS / "fuentes"
ML = FUENTES / "ml-latest-small"
TMDB = FUENTES / "movies_metadata.csv"
RUTA_DUCKDB = DATOS / "moviematch.duckdb"
EXPORTACIONES = DATOS / "procesados"
RUTA_SQL = RAIZ / "scripts" / "sql" / "preparar_catalogo.sql"

TMDB_URL = "https://zenodo.org/records/18099452/files/movies_metadata.csv?download=1"
TMDB_MD5 = "42bf3ef8c208a01a4776955875978b1e"  # checksum publicado en Zenodo


def ruta_sql(ruta: Path) -> str:
    """Escapa una ruta como literal SQL (incluidos acentos y apóstrofos)."""
    ruta_absoluta = ruta.resolve().as_posix()
    ruta_escapada = ruta_absoluta.replace("'", "''")
    return "'" + ruta_escapada + "'"


def descargar_tmdb(destino: Path) -> None:
    if destino.is_file():
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".parcial")
    try:
        peticion = urllib.request.Request(
            TMDB_URL, headers={"User-Agent": "MovieMatch-ETL-Educativo/1.0"}
        )
        md5 = hashlib.md5()  # integridad del archivo, no seguridad criptográfica
        with urllib.request.urlopen(peticion, timeout=120) as origen, temporal.open("wb") as salida:
            while True:
                bloque = origen.read(1024 * 1024)
                if not bloque:
                    break
                salida.write(bloque)
                md5.update(bloque)
        if temporal.stat().st_size < 1_000_000:
            raise RuntimeError("La descarga es demasiado pequeña para ser el CSV esperado.")
        if md5.hexdigest() != TMDB_MD5:
            raise RuntimeError(
                "El checksum no coincide con el publicado en Zenodo. "
                "Comprueba la descarga o utiliza --metadata con otra copia validada."
            )
        temporal.replace(destino)
    except Exception as exc:
        temporal.unlink(missing_ok=True)
        raise RuntimeError(
            f"No se pudieron obtener los metadatos de Zenodo: {exc}\n"
            "Descarga movies_metadata.csv desde https://zenodo.org/records/18099452 "
            "y guárdalo en datos/fuentes/movies_metadata.csv; vuelve a ejecutarlo."
        ) from exc


def comprobar_fuentes(metadatos: Path) -> None:
    for nombre in ("movies.csv", "links.csv", "ratings.csv"):
        archivo = ML / nombre
        if not archivo.is_file():
            raise FileNotFoundError(
                f"Falta {archivo}. Los CSV deben estar en datos/fuentes/ml-latest-small/. "
                "Descarga y descomprime ml-latest-small.zip desde GroupLens (ver README.md)."
            )
    if not metadatos.is_file():
        raise FileNotFoundError(f"No se encontró {metadatos}")


def ejecutar_sql(con: duckdb.DuckDBPyConnection, rutas: dict[str, Path]) -> None:
    sql = RUTA_SQL.read_text(encoding="utf-8")
    for token, ruta in rutas.items():
        sql = sql.replace("{{" + token + "}}", ruta_sql(ruta))
    con.execute(sql)


def contar(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    return int(con.execute(sql).fetchone()[0])


def validar(con: duckdb.DuckDBPyConnection) -> dict:
    """Comprobaciones explícitas de claves, relaciones y puntuaciones."""
    controles = {
        "peliculas_con_id_nulo": "SELECT count(*) FROM ml_peliculas WHERE movieId IS NULL",
        "peliculas_con_id_duplicado": """
            SELECT count(*) FROM (
                SELECT movieId FROM ml_peliculas GROUP BY movieId HAVING count(*) > 1
            )
        """,
        "links_con_id_duplicado": """
            SELECT count(*) FROM (
                SELECT movieId FROM ml_enlaces GROUP BY movieId HAVING count(*) > 1
            )
        """,
        "links_con_id_nulo": "SELECT count(*) FROM ml_enlaces WHERE movieId IS NULL",
        "valoraciones_con_id_nulo": """
            SELECT count(*) FROM valoraciones WHERE userId IS NULL OR movieId IS NULL
        """,
        "valoraciones_huerfanas": """
            SELECT count(*) FROM valoraciones v
            LEFT JOIN peliculas p ON p.movieId = v.movieId WHERE p.movieId IS NULL
        """,
        "valoraciones_fuera_de_escala": """
            SELECT count(*) FROM valoraciones
            WHERE puntuacion IS NULL OR puntuacion < 0.5 OR puntuacion > 5
               OR puntuacion * 2 <> floor(puntuacion * 2)
        """,
        "valoraciones_repetidas": """
            SELECT count(*) FROM (
                SELECT userId, movieId FROM valoraciones
                GROUP BY userId, movieId HAVING count(*) > 1
            )
        """,
        "peliculas_finales_duplicadas": """
            SELECT count(*) FROM (
                SELECT movieId FROM peliculas GROUP BY movieId HAVING count(*) > 1
            )
        """,
        "filas_tmdb_insuficientes": """
            SELECT CASE WHEN count(*) < 10000 THEN 1 ELSE 0 END FROM tmdb_raw
        """,
        "cobertura_qdrant_insuficiente": """
            SELECT CASE WHEN count(*) < 100 THEN 1 ELSE 0 END
            FROM peliculas_qdrant
        """,
    }
    resultados = {}
    fallos = {}
    for nombre, consulta in controles.items():
        cantidad = contar(con, consulta)
        resultados[nombre] = cantidad
        if cantidad > 0:
            fallos[nombre] = cantidad

    if fallos:
        raise RuntimeError(
            "La integración presenta errores de integridad y se ha cancelado: "
            + json.dumps(fallos, ensure_ascii=False)
        )
    return resultados


def exportar(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    # Reutiliza exactamente el conjunto con sinopsis válida de Qdrant.
    con.execute("""
        CREATE OR REPLACE TEMP VIEW peliculas_nebula AS
        SELECT p.* FROM peliculas_qdrant p
        WHERE EXISTS (SELECT 1 FROM valoraciones v WHERE v.movieId = p.movieId)
    """)
    sin_historial = contar(con, """
        SELECT count(*) FROM usuarios u WHERE NOT EXISTS (
            SELECT 1 FROM valoraciones v JOIN peliculas_nebula p USING (movieId)
            WHERE v.userId = u.userId
        )
    """)
    if sin_historial:
        raise RuntimeError(f"El filtro dejaría {sin_historial} usuarios sin historial.")
    EXPORTACIONES.mkdir(parents=True, exist_ok=True)
    consultas = {
        "qdrant": """
            SELECT movieId, titulo, anio, generos, tmdbId, imdbId, sinopsis
            FROM peliculas_qdrant ORDER BY movieId
        """,
        "peliculas_nebula": """
            SELECT movieId, titulo, anio, tmdbId, imdbId
            FROM peliculas_nebula ORDER BY movieId
        """,
        "usuarios_nebula": "SELECT userId FROM usuarios ORDER BY userId",
        "valoraciones_nebula": """
            SELECT userId, movieId, puntuacion, timestamp
            FROM valoraciones WHERE movieId IN (SELECT movieId FROM peliculas_nebula)
            ORDER BY userId, movieId
        """,
        "generos_nebula": """
            SELECT movieId, genero FROM peliculas_generos
            WHERE movieId IN (SELECT movieId FROM peliculas_nebula)
            ORDER BY movieId, genero
        """,
    }
    nombres_archivos = {
        "qdrant": "peliculas_qdrant.parquet",
        "peliculas_nebula": "peliculas_nebula.csv",
        "usuarios_nebula": "usuarios_nebula.csv",
        "valoraciones_nebula": "valoraciones_nebula.csv",
        "generos_nebula": "peliculas_generos_nebula.csv",
    }
    archivos = {}
    for nombre, consulta in consultas.items():
        archivo = EXPORTACIONES / nombres_archivos[nombre]
        if archivo.suffix == ".parquet":
            formato = "FORMAT PARQUET"
        else:
            formato = "FORMAT CSV, HEADER TRUE"
        con.execute(f"COPY ({consulta}) TO {ruta_sql(archivo)} ({formato})")
        archivos[nombre] = str(archivo.relative_to(RAIZ))
    return archivos


def resumen(con: duckdb.DuckDBPyConnection, comprobaciones: dict, rutas: dict) -> dict:
    total = contar(con, "SELECT count(*) FROM peliculas")
    con_sinopsis = contar(con, "SELECT count(*) FROM peliculas_qdrant")
    sin_tmdb = contar(con, "SELECT count(*) FROM peliculas WHERE tmdbId IS NULL")
    sin_match = contar(con, """
        SELECT count(*) FROM peliculas WHERE tmdbId IS NOT NULL AND sinopsis IS NULL
    """)
    metadatos_duplicados = contar(con, """
        SELECT count(*) FROM (
            SELECT tmdbId FROM tmdb_limpio WHERE tmdbId IS NOT NULL
            GROUP BY tmdbId HAVING count(*) > 1
        )
    """)
    cobertura = 0.0
    if total > 0:
        cobertura = round(100 * con_sinopsis / total, 2)

    reporte = {
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "fuente_peliculas": "MovieLens Latest Small (GroupLens)",
        "fuente_sinopsis": TMDB_URL,
        "duckdb_version": duckdb.__version__,
        "peliculas_movielens": total,
        "usuarios": contar(con, "SELECT count(*) FROM usuarios"),
        "valoraciones": contar(con, "SELECT count(*) FROM valoraciones"),
        "peliculas_para_qdrant": con_sinopsis,
        "peliculas_para_nebula": contar(con, "SELECT count(*) FROM peliculas_nebula"),
        "cobertura_qdrant_pct": cobertura,
        "peliculas_sin_tmdbId": sin_tmdb,
        "peliculas_con_tmdbId_pero_sin_sinopsis_usable": sin_match,
        "ids_tmdb_duplicados_en_fuente": metadatos_duplicados,
        "controles_integridad": comprobaciones,
        "archivos_exportados": rutas,
        "observaciones": [
            "La colección existente de Qdrant no se modifica.",
            "Las sinopsis son mayoritariamente inglesas.",
            "NebulaGraph recibe solo películas de peliculas_qdrant con al menos una valoración.",
            "Se ignoran las filas estructuralmente defectuosas del CSV de TMDB.",
        ],
    }
    (DATOS / "reporte_etl.json").write_text(
        json.dumps(reporte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return reporte


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metadata", type=Path,
        help="CSV de metadatos TMDB existente en otra ubicación",
    )
    parser.add_argument(
        "--solo-exportar", action="store_true",
        help="Regenera las exportaciones desde DuckDB en modo de solo lectura",
    )
    args = parser.parse_args()
    if args.solo_exportar:
        with duckdb.connect(str(RUTA_DUCKDB), read_only=True) as con:
            integridad = validar(con)
            archivos = exportar(con)
            reporte = resumen(con, integridad, archivos)
        print(f"Exportaciones preparadas: {reporte['peliculas_para_nebula']} películas para NebulaGraph.")
        return
    if args.metadata is None:
        metadatos = TMDB
        descargar_tmdb(metadatos)
    else:
        metadatos = args.metadata.expanduser().resolve()
    comprobar_fuentes(metadatos)
    DATOS.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(RUTA_DUCKDB))
    try:
        con.execute("BEGIN TRANSACTION")
        try:
            ejecutar_sql(con, {
                "MOVIES_CSV": ML / "movies.csv",
                "LINKS_CSV": ML / "links.csv",
                "RATINGS_CSV": ML / "ratings.csv",
                "TMDB_CSV": metadatos,
            })
            integridad = validar(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        archivos = exportar(con)
        reporte = resumen(con, integridad, archivos)
    finally:
        con.close()

    print(
        f"ETL completado: {reporte['peliculas_movielens']} películas, "
        f"{reporte['peliculas_para_qdrant']} con sinopsis. Informe: datos/reporte_etl.json"
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, duckdb.Error) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
