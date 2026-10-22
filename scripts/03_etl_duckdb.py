#!/usr/bin/env python3
"""MovieMatch: ETL reproducible de MovieLens + metadatos de TMDB con DuckDB.

Ejecutar desde la raíz del repositorio:
    python scripts/03_etl_duckdb.py

Requiere los CSV originales de MovieLens en datos/fuentes/ml-latest-small/.
NO toca Qdrant ni NebulaGraph; produce una base DuckDB y exportaciones.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import duckdb
except ImportError:
    raise SystemExit("Falta DuckDB. Instala: python -m pip install 'duckdb==1.5.6'")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datos"
FUENTES = DATA / "fuentes"
ML = FUENTES / "ml-latest-small"
TMDB = FUENTES / "movies_metadata.csv"
DB_FILE = DATA / "moviematch.duckdb"
EXPORTS = DATA / "procesados"
SQL_FILE = ROOT / "scripts" / "sql" / "preparar_catalogo.sql"

TMDB_URL = "https://zenodo.org/records/18099452/files/movies_metadata.csv?download=1"
TMDB_MD5 = "42bf3ef8c208a01a4776955875978b1e"  # checksum publicado en Zenodo


def sql_quoted_path(path: Path) -> str:
    """Escapa una ruta como literal SQL (incluidos acentos y apóstrofos)."""
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def descargar_tmdb(destino: Path) -> None:
    if destino.is_file() and destino.stat().st_size > 1_000_000:
        print("✓ Metadatos TMDB ya disponibles; no es necesario descargarlos.")
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".parcial")
    print("Descargando movies_metadata.csv de Zenodo (~34 MB)...")
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
        print("✓ Archivo descargado y comprobado por MD5.")
    except Exception as exc:
        temporal.unlink(missing_ok=True)
        raise RuntimeError(
            f"No se pudieron obtener los metadatos de Zenodo: {exc}\n"
            "Descarga movies_metadata.csv desde https://zenodo.org/records/18099452 "
            "y guárdalo en datos/fuentes/movies_metadata.csv; vuelve a ejecutarlo."
        ) from exc


def comprobar_fuentes(metadata: Path) -> None:
    for nombre in ("movies.csv", "links.csv", "ratings.csv"):
        archivo = ML / nombre
        if not archivo.is_file():
            raise FileNotFoundError(
                f"Falta {archivo}. Los CSV deben estar en datos/fuentes/ml-latest-small/. "
                "Si solo tienes catalogo_movielens.json, ejecuta primero "
                "scripts/01_preparar_movielens.py."
            )
    if not metadata.is_file():
        raise FileNotFoundError(f"No se encontró {metadata}")


def ejecutar_sql(con: duckdb.DuckDBPyConnection, paths: dict[str, Path]) -> None:
    sql = SQL_FILE.read_text(encoding="utf-8")
    for token, ruta in paths.items():
        sql = sql.replace("{{" + token + "}}", sql_quoted_path(ruta))
    # Cada bloque SQL está claramente marcado y es ejecutable por separado.
    for bloque in sql.split("-- @PASO"):
        sentencia = bloque.strip()
        if not sentencia or all(
            not line.strip() or line.lstrip().startswith("--")
            for line in sentencia.splitlines()
        ):
            continue
        con.execute(sentencia)


def contar(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    return int(con.execute(sql).fetchone()[0])


def validar(con: duckdb.DuckDBPyConnection) -> dict:
    """Comprobaciones explícitas de claves, relaciones y puntuaciones."""
    pruebas = {
        "peliculas_con_id_nulo": "SELECT count(*) FROM ml_peliculas WHERE movieId IS NULL",
        "peliculas_con_id_duplicado": "SELECT count(*) FROM (SELECT movieId FROM ml_peliculas GROUP BY 1 HAVING count(*) > 1)",
        "links_con_id_duplicado": "SELECT count(*) FROM (SELECT movieId FROM ml_enlaces GROUP BY 1 HAVING count(*) > 1)",
        "valoraciones_con_id_nulo": "SELECT count(*) FROM valoraciones WHERE userId IS NULL OR movieId IS NULL",
        "valoraciones_huerfanas": "SELECT count(*) FROM valoraciones v LEFT JOIN peliculas p ON p.movieId=v.movieId WHERE p.movieId IS NULL",
        "valoraciones_fuera_de_escala": "SELECT count(*) FROM valoraciones WHERE puntuacion IS NULL OR puntuacion < 0.5 OR puntuacion > 5 OR puntuacion*2 <> floor(puntuacion*2)",
        "valoraciones_repetidas": "SELECT count(*) FROM (SELECT userId, movieId FROM valoraciones GROUP BY 1,2 HAVING count(*) > 1)",
        "peliculas_finales_duplicadas": "SELECT count(*) FROM (SELECT movieId FROM peliculas GROUP BY 1 HAVING count(*) > 1)",
        "filas_tmdb_insuficientes": "SELECT CASE WHEN count(*) < 10000 THEN 1 ELSE 0 END FROM tmdb_raw",
        "cobertura_qdrant_insuficiente": "SELECT CASE WHEN count(*) < 100 THEN 1 ELSE 0 END FROM peliculas_qdrant",
    }
    resultados = {nombre: contar(con, q) for nombre, q in pruebas.items()}
    fallos = {k: v for k, v in resultados.items() if v}
    if fallos:
        raise RuntimeError(
            "La integración presenta errores de integridad y se ha cancelado: "
            + json.dumps(fallos, ensure_ascii=False)
        )
    return resultados


def exportar(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    archivos = {
        "qdrant": EXPORTS / "peliculas_qdrant.parquet",
        "peliculas_nebula": EXPORTS / "peliculas_nebula.csv",
        "usuarios_nebula": EXPORTS / "usuarios_nebula.csv",
        "valoraciones_nebula": EXPORTS / "valoraciones_nebula.csv",
        "generos_nebula": EXPORTS / "peliculas_generos_nebula.csv",
    }
    for tabla, archivo in (
        ("peliculas_qdrant", archivos["qdrant"]),
        ("peliculas", archivos["peliculas_nebula"]),
        ("usuarios", archivos["usuarios_nebula"]),
        ("valoraciones", archivos["valoraciones_nebula"]),
        ("peliculas_generos", archivos["generos_nebula"]),
    ):
        # Las listas de géneros son útiles en Parquet; para CSV exportamos
        # columnas escalares pensadas para la futura importación del grafo.
        if tabla == "peliculas":
            query = "SELECT movieId, titulo, anio, tmdbId, imdbId FROM peliculas ORDER BY movieId"
        elif tabla == "peliculas_qdrant":
            query = "SELECT movieId, titulo, anio, generos, tmdbId, imdbId, sinopsis FROM peliculas_qdrant ORDER BY movieId"
        elif tabla == "usuarios":
            query = "SELECT userId FROM usuarios ORDER BY userId"
        elif tabla == "valoraciones":
            query = "SELECT userId, movieId, puntuacion, timestamp FROM valoraciones ORDER BY userId, movieId"
        else:
            query = "SELECT movieId, genero FROM peliculas_generos ORDER BY movieId, genero"
        formato = "(FORMAT PARQUET)" if archivo.suffix == ".parquet" else "(FORMAT CSV, HEADER TRUE)"
        con.execute(f"COPY ({query}) TO {sql_quoted_path(archivo)} {formato}")
    return {k: str(v.relative_to(ROOT)) for k, v in archivos.items()}


def resumen(con: duckdb.DuckDBPyConnection, comprobaciones: dict, rutas: dict) -> dict:
    total = contar(con, "SELECT count(*) FROM peliculas")
    con_sinopsis = contar(con, "SELECT count(*) FROM peliculas_qdrant")
    sin_tmdb = contar(con, "SELECT count(*) FROM peliculas WHERE tmdbId IS NULL")
    sin_match = contar(con, "SELECT count(*) FROM peliculas WHERE tmdbId IS NOT NULL AND sinopsis IS NULL")
    metadatos_duplicados = contar(con, "SELECT count(*) FROM (SELECT tmdbId FROM tmdb_limpio WHERE tmdbId IS NOT NULL GROUP BY tmdbId HAVING count(*) > 1)")
    reporte = {
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "fuente_peliculas": "MovieLens Latest Small (GroupLens)",
        "fuente_sinopsis": TMDB_URL,
        "duckdb_version": duckdb.__version__,
        "peliculas_movielens": total,
        "usuarios": contar(con, "SELECT count(*) FROM usuarios"),
        "valoraciones": contar(con, "SELECT count(*) FROM valoraciones"),
        "peliculas_para_qdrant": con_sinopsis,
        "cobertura_qdrant_pct": round(100 * con_sinopsis / total, 2) if total else 0.0,
        "peliculas_sin_tmdbId": sin_tmdb,
        "peliculas_con_tmdbId_pero_sin_sinopsis_usable": sin_match,
        "ids_tmdb_duplicados_en_fuente": metadatos_duplicados,
        "controles_integridad": comprobaciones,
        "archivos_exportados": rutas,
        "observaciones": [
            "La colección existente de Qdrant no se modifica.",
            "Las sinopsis son mayoritariamente inglesas.",
            "Las películas sin sinopsis permanecen en DuckDB y se exportan para NebulaGraph.",
            "Se ignoran las filas estructuralmente defectuosas del CSV de TMDB.",
        ],
    }
    (DATA / "reporte_etl.json").write_text(
        json.dumps(reporte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return reporte


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metadata", type=Path, default=None,
                    help="CSV de metadatos TMDB existente en otra ubicación")
    args = ap.parse_args()
    metadata = args.metadata.expanduser().resolve() if args.metadata else TMDB
    if args.metadata is None:
        descargar_tmdb(metadata)
    comprobar_fuentes(metadata)
    DATA.mkdir(parents=True, exist_ok=True)

    print("Preparando tablas en DuckDB con SQL...")
    con = duckdb.connect(str(DB_FILE))
    try:
        con.execute("BEGIN TRANSACTION")
        try:
            ejecutar_sql(con, {
                "MOVIES_CSV": ML / "movies.csv",
                "LINKS_CSV": ML / "links.csv",
                "RATINGS_CSV": ML / "ratings.csv",
                "TMDB_CSV": metadata,
            })
            integridad = validar(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        archivos = exportar(con)
        r = resumen(con, integridad, archivos)
    finally:
        con.close()

    print("\n=== MOVIEMATCH | ETL CON DUCKDB ===")
    print(f"Películas MovieLens:       {r['peliculas_movielens']}")
    print(f"Usuarios:                  {r['usuarios']}")
    print(f"Valoraciones:              {r['valoraciones']}")
    print(f"Películas para Qdrant:     {r['peliculas_para_qdrant']}")
    print(f"Cobertura Qdrant:          {r['cobertura_qdrant_pct']:.2f}%")
    print(f"Sin TMDB ID:               {r['peliculas_sin_tmdbId']}")
    print(f"TMDB sin sinopsis usable:  {r['peliculas_con_tmdbId_pero_sin_sinopsis_usable']}")
    print("Integridad referencial:    OK")
    print("\nArchivos:")
    print("  datos/moviematch.duckdb")
    print("  datos/reporte_etl.json")
    for archivo in archivos.values():
        print("  " + archivo)
    print("\nNo se ha modificado la colección actual de Qdrant.")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, RuntimeError, duckdb.Error) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
