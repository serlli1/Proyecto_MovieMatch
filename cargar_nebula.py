"""Importa los CSV preparados por DuckDB con depuración opcional y respaldo previo."""
import argparse
import csv
from datetime import datetime
import json
import sys
import time
from pathlib import Path

from src.grafo import ESPACIO, conectar, ejecutar

DATOS = Path(__file__).resolve().parent / "datos" / "procesados"
TAM_LOTE = 500


CONSULTAS = {
    "peliculas": """MATCH (p:Pelicula) RETURN p.Pelicula.movieId AS movieId,
        p.Pelicula.titulo AS titulo, p.Pelicula.anio AS anio""",
    "usuarios": "MATCH (u:Usuario) RETURN u.Usuario.userId AS userId",
    "valoraciones": """MATCH (u:Usuario)-[v:VALORA]->(p:Pelicula)
        RETURN u.Usuario.userId AS userId, p.Pelicula.movieId AS movieId,
               v.puntuacion AS puntuacion, v.fecha AS `timestamp`""",
    "peliculas_generos": """MATCH (p:Pelicula)-[:PERTENECE_A]->(g:Genero)
        RETURN p.Pelicula.movieId AS movieId, g.Genero.nombre AS genero""",
}


def leer_fuentes(carpeta=DATOS):
    tablas = {}
    for nombre in ("peliculas", "usuarios", "valoraciones", "peliculas_generos"):
        ruta = carpeta / f"{nombre}_nebula.csv"
        with ruta.open(encoding="utf-8", newline="") as archivo:
            tablas[nombre] = list(csv.DictReader(archivo))
        if not tablas[nombre]:
            raise ValueError(f"El archivo {ruta.name} está vacío.")

    peliculas = set()
    usuarios = set()
    for fila in tablas["peliculas"]:
        identificador = int(fila["movieId"])
        if identificador <= 0 or identificador in peliculas or not fila["titulo"]:
            raise ValueError("Película inválida o duplicada en los CSV.")
        peliculas.add(identificador)
        if fila["anio"]:
            int(fila["anio"])
    for fila in tablas["usuarios"]:
        identificador = int(fila["userId"])
        if identificador <= 0 or identificador in usuarios:
            raise ValueError("Usuario inválido o duplicado en los CSV.")
        usuarios.add(identificador)

    relaciones = set()
    con_historial = set()
    for fila in tablas["valoraciones"]:
        usuario = int(fila["userId"])
        pelicula = int(fila["movieId"])
        puntuacion = float(fila["puntuacion"])
        int(fila["timestamp"])
        if usuario not in usuarios or pelicula not in peliculas:
            raise ValueError("Valoración sin usuario o película correspondiente.")
        if not 0.5 <= puntuacion <= 5 or puntuacion * 2 % 1 != 0:
            raise ValueError("Valoración fuera de escala.")
        if (usuario, pelicula) in relaciones:
            raise ValueError("Valoración duplicada.")
        relaciones.add((usuario, pelicula))
        con_historial.add(usuario)

    if con_historial != usuarios:
        raise ValueError("Hay usuarios sin historial válido en los CSV.")

    relaciones = set()
    for fila in tablas["peliculas_generos"]:
        relacion = (int(fila["movieId"]), fila["genero"])
        if relacion[0] not in peliculas or not relacion[1] or relacion in relaciones:
            raise ValueError("Relación de género inválida o duplicada.")
        relaciones.add(relacion)
    return tablas


def esperar(sesion, consulta):
    # Los cambios de esquema se propagan mediante los heartbeats de NebulaGraph.
    for intento in range(60):
        try:
            return ejecutar(sesion, consulta)
        except RuntimeError:
            if intento == 59:
                raise
            time.sleep(1)


def registrar_hosts(sesion):
    hosts = ejecutar(sesion, "SHOW HOSTS")
    if not any(fila.get("Host") == "storaged" and fila.get("Port") == 9779 for fila in hosts):
        ejecutar(sesion, 'ADD HOSTS "storaged":9779')
    for intento in range(60):
        hosts = ejecutar(sesion, "SHOW HOSTS")
        if any(fila.get("Host") == "storaged" and fila.get("Port") == 9779
               and fila.get("Status") == "ONLINE" for fila in hosts):
            return
        time.sleep(1)
    raise RuntimeError("storaged:9779 no está ONLINE. Revisa docker compose logs storaged metad.")


def preparar_grafo(sesion):
    registrar_hosts(sesion)
    esperar(sesion, f"""
        CREATE SPACE IF NOT EXISTS {ESPACIO}
        (partition_num=10, replica_factor=1, vid_type=FIXED_STRING(80))
    """)
    esperar(sesion, f"USE {ESPACIO}")
    esquemas = [
        "CREATE TAG IF NOT EXISTS Usuario(userId int)",
        "CREATE TAG IF NOT EXISTS Pelicula(movieId int, titulo string, anio int NULL)",
        "CREATE TAG IF NOT EXISTS Genero(nombre string)",
        "CREATE EDGE IF NOT EXISTS VALORA(puntuacion double, fecha int)",
        "CREATE EDGE IF NOT EXISTS PERTENECE_A()",
    ]
    for esquema in esquemas:
        ejecutar(sesion, esquema)
    for etiqueta in ("Usuario", "Pelicula", "Genero"):
        esperar(sesion, f"DESCRIBE TAG {etiqueta}")
    for relacion in ("VALORA", "PERTENECE_A"):
        esperar(sesion, f"DESCRIBE EDGE {relacion}")


def insertar_lotes(sesion, sentencia, valores):
    for inicio in range(0, len(valores), TAM_LOTE):
        lote = valores[inicio:inicio + TAM_LOTE]
        esperar(sesion, sentencia + " VALUES " + ", ".join(lote))


def importar(sesion, tablas):
    valores = []
    for fila in tablas["peliculas"]:
        movie_id = int(fila["movieId"])
        titulo = json.dumps(fila["titulo"], ensure_ascii=False)
        anio = "NULL"
        if fila["anio"]:
            anio = str(int(fila["anio"]))
        valores.append(f'"pelicula:{movie_id}":({movie_id}, {titulo}, {anio})')
    insertar_lotes(sesion, "INSERT VERTEX Pelicula(movieId, titulo, anio)", valores)

    valores = []
    for fila in tablas["usuarios"]:
        user_id = int(fila["userId"])
        valores.append(f'"usuario:{user_id}":({user_id})')
    insertar_lotes(sesion, "INSERT VERTEX Usuario(userId)", valores)

    generos = set()
    for fila in tablas["peliculas_generos"]:
        generos.add(fila["genero"])
    valores = []
    for genero in sorted(generos):
        identificador = json.dumps("genero:" + genero, ensure_ascii=False)
        nombre = json.dumps(genero, ensure_ascii=False)
        valores.append(f"{identificador}:({nombre})")
    insertar_lotes(sesion, "INSERT VERTEX Genero(nombre)", valores)

    valores = []
    for fila in tablas["valoraciones"]:
        usuario = int(fila["userId"])
        pelicula = int(fila["movieId"])
        nota = float(fila["puntuacion"])
        fecha = int(fila["timestamp"])
        valores.append(f'"usuario:{usuario}"->"pelicula:{pelicula}":({nota}, {fecha})')
    insertar_lotes(sesion, "INSERT EDGE VALORA(puntuacion, fecha)", valores)

    valores = []
    for fila in tablas["peliculas_generos"]:
        pelicula = int(fila["movieId"])
        genero = json.dumps("genero:" + fila["genero"], ensure_ascii=False)
        valores.append(f'"pelicula:{pelicula}"->{genero}:()')
    insertar_lotes(sesion, "INSERT EDGE PERTENECE_A()", valores)


def validar_importacion(sesion, tablas):
    for nombre, consulta in CONSULTAS.items():
        filas = ejecutar(sesion, consulta)
        columnas = list(filas[0]) if filas else []
        esperadas = set()
        actuales = set()
        for origen, destino in ((tablas[nombre], esperadas), (filas, actuales)):
            for fila in origen:
                valores = []
                for columna in columnas:
                    valor = fila[columna]
                    if valor is None or valor == "":
                        valor = ""
                    elif columna == "puntuacion":
                        valor = float(valor)
                    else:
                        valor = str(valor)
                    valores.append(valor)
                destino.add(tuple(valores))
        if len(filas) != len(tablas[nombre]) or actuales != esperadas:
            raise RuntimeError(f"La importación de {nombre} no coincide con los CSV.")

    for etiqueta, propiedad, prefijo in (
        ("Usuario", "userId", "usuario:"), ("Pelicula", "movieId", "pelicula:"),
    ):
        filas = ejecutar(sesion, f"""
            MATCH (v:{etiqueta})
            WHERE id(v) != "{prefijo}" + toString(v.{etiqueta}.{propiedad})
            RETURN count(v) AS errores
        """)
        if filas[0]["errores"]:
            raise RuntimeError(f"Identificadores inconsistentes en {etiqueta}.")
    generos_esperados = set()
    for fila in tablas["peliculas_generos"]:
        generos_esperados.add(fila["genero"])
    generos = ejecutar(sesion, "MATCH (g:Genero) RETURN g.Genero.nombre AS nombre")
    nombres = set()
    for genero in generos:
        nombres.add(genero["nombre"])
    if nombres != generos_esperados or len(generos) != len(nombres):
        raise RuntimeError("Los géneros del grafo no coinciden con los CSV.")

    # MATCH no muestra aristas huérfanas; contrasta también el recuento de almacenamiento.
    trabajo = ejecutar(sesion, "SUBMIT JOB STATS")[0]["New Job Id"]
    for intento in range(60):
        estado = ejecutar(sesion, f"SHOW JOB {trabajo}")[0]["Status"]
        if estado == "FINISHED":
            break
        if estado == "FAILED" or intento == 59:
            raise RuntimeError("No se pudieron verificar las estadísticas del grafo.")
        time.sleep(1)
    esperados = {
        "Usuario": len(tablas["usuarios"]), "Pelicula": len(tablas["peliculas"]),
        "Genero": len(nombres), "VALORA": len(tablas["valoraciones"]),
        "PERTENECE_A": len(tablas["peliculas_generos"]),
        "vertices": len(tablas["usuarios"]) + len(tablas["peliculas"]) + len(nombres),
        "edges": len(tablas["valoraciones"]) + len(tablas["peliculas_generos"]),
    }
    actuales = {}
    for fila in ejecutar(sesion, "SHOW STATS"):
        actuales[fila["Name"]] = fila["Count"]
    if actuales != esperados:
        raise RuntimeError("El grafo contiene registros sobrantes o relaciones huérfanas.")


def depurar(sesion, tablas):
    permitidas = set()
    for pelicula in tablas["peliculas"]:
        permitidas.add(int(pelicula["movieId"]))
    actuales = ejecutar(sesion, CONSULTAS["peliculas"])
    descartadas = []
    for pelicula in actuales:
        if pelicula["movieId"] not in permitidas:
            descartadas.append(pelicula)
    if not descartadas:
        return

    carpeta = DATOS.parent / "respaldos_nebula" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    carpeta.mkdir(parents=True, exist_ok=False)
    for nombre, consulta in CONSULTAS.items():
        filas = ejecutar(sesion, consulta)
        if not filas:
            raise RuntimeError("No se puede respaldar una tabla vacía del grafo.")
        with (carpeta / f"{nombre}_nebula.csv").open("w", encoding="utf-8", newline="") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=list(filas[0]))
            escritor.writeheader()
            escritor.writerows(filas)
    # Relee y contrasta la copia antes de permitir cualquier eliminación.
    respaldo = leer_fuentes(carpeta)
    validar_importacion(sesion, respaldo)
    (carpeta / "descartadas.json").write_text(
        json.dumps(descartadas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Respaldo verificado: {carpeta}", flush=True)
    for inicio in range(0, len(descartadas), TAM_LOTE):
        ids = []
        for pelicula in descartadas[inicio:inicio + TAM_LOTE]:
            ids.append(f'"pelicula:{int(pelicula["movieId"])}"')
        ejecutar(sesion, "DELETE VERTEX " + ", ".join(ids) + " WITH EDGE")
    print(f"Descartadas {len(descartadas)} películas y sus relaciones.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registrar-hosts", action="store_true",
                        help="Solo registra storaged y espera ONLINE; no requiere CSV ni importa datos")
    parser.add_argument("--depurar", action="store_true",
                        help="Respalda y elimina las películas ausentes de los CSV actuales")
    parser.add_argument("--fuentes", type=Path, default=DATOS,
                        help="Carpeta de CSV; permite recuperar un respaldo sin borrar registros")
    args = parser.parse_args()
    if args.registrar_hosts:
        if args.depurar or args.fuentes.resolve() != DATOS.resolve():
            parser.error("--registrar-hosts se utiliza sin --depurar ni --fuentes.")
        print("Esperando a Graph Service y registrando el Storage Host...", flush=True)
        limite = time.monotonic() + 120
        while True:
            try:
                with conectar(usar_espacio=False) as sesion:
                    registrar_hosts(sesion)
                break
            except Exception:
                if time.monotonic() >= limite:
                    raise
                time.sleep(2)
        print("Storage Host storaged:9779 registrado y ONLINE.")
        return
    if args.depurar and args.fuentes.resolve() != DATOS.resolve():
        parser.error("La depuración solo admite las exportaciones actuales del ETL.")
    tablas = leer_fuentes(args.fuentes)
    with conectar(usar_espacio=False) as sesion:
        preparar_grafo(sesion)
        if args.depurar:
            depurar(sesion, tablas)
        importar(sesion, tablas)
        validar_importacion(sesion, tablas)
    print(
        f"Grafo preparado: {len(tablas['peliculas'])} películas, "
        f"{len(tablas['usuarios'])} usuarios y {len(tablas['valoraciones'])} valoraciones."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
