"""Consultas de perfiles y recomendaciones ejecutadas en NebulaGraph."""
import os
from contextlib import contextmanager

from nebula3.Config import Config
from nebula3.gclient.net import ConnectionPool

ESPACIO = "moviematch"


@contextmanager
def conectar(usar_espacio=True):
    config = Config()
    config.max_connection_pool_size = 2
    config.timeout = 30000
    pool = ConnectionPool()
    sesion = None
    try:
        host = os.getenv("NEBULA_HOST", "127.0.0.1")
        puerto = int(os.getenv("NEBULA_PORT", "9669"))
        if not pool.init([(host, puerto)], config):
            raise ConnectionError("No se pudo conectar con NebulaGraph.")
        sesion = pool.get_session(
            os.getenv("NEBULA_USER", "root"), os.getenv("NEBULA_PASSWORD", "nebula")
        )
        if usar_espacio:
            ejecutar(sesion, f"USE {ESPACIO}")
        yield sesion
    finally:
        if sesion is not None:
            sesion.release()
        pool.close()


def ejecutar(sesion, consulta):
    resultado = sesion.execute(consulta)
    if not resultado.is_succeeded():
        raise RuntimeError(f"NebulaGraph: {resultado.error_msg()}")
    filas = []
    for indice in range(resultado.row_size()):
        fila = {}
        for nombre, valor in zip(resultado.keys(), resultado.row_values(indice)):
            fila[nombre] = valor.cast_primitive()
        filas.append(fila)
    return filas


def usuarios():
    with conectar() as sesion:
        filas = ejecutar(sesion, """
            MATCH (u:Usuario) RETURN u.Usuario.userId AS userId ORDER BY userId
        """)
    return [fila["userId"] for fila in filas]


def perfil(user_id):
    with conectar() as sesion:
        return ejecutar(sesion, f'''
            MATCH (u:Usuario)-[v:VALORA]->(p:Pelicula)
            WHERE id(u) == "usuario:{int(user_id)}"
            RETURN p.Pelicula.movieId AS movieId, p.Pelicula.titulo AS titulo,
                   v.puntuacion AS puntuacion
            ORDER BY puntuacion DESC, movieId
        ''')


def top_comunidad():
    with conectar() as sesion:
        return ejecutar(sesion, """
            MATCH (:Usuario)-[v:VALORA]->(p:Pelicula)
            WITH p, avg(v.puntuacion) AS media, count(v) AS votos
            WHERE votos >= 20
            RETURN p.Pelicula.movieId AS movieId, p.Pelicula.titulo AS titulo,
                   p.Pelicula.anio AS anio, media, votos
            ORDER BY media DESC, votos DESC, movieId LIMIT 10
        """)


def colaborativas(user_id, valoradas):
    # La afinidad y la puntuación se calculan en el grafo, no en Python.
    excluidas = []
    for pelicula in valoradas:
        excluidas.append(int(pelicula["movieId"]))
    with conectar() as sesion:
        vecinos = ejecutar(sesion, f'''
            MATCH (u:Usuario)-[a:VALORA]->(comun:Pelicula)<-[b:VALORA]-(vecino:Usuario)
            WHERE id(u) == "usuario:{int(user_id)}" AND id(vecino) != id(u)
                  AND a.puntuacion >= 4 AND b.puntuacion >= 4
            WITH vecino, count(DISTINCT comun) AS coincidencias
            WHERE coincidencias >= 3
            RETURN id(vecino) AS vid, coincidencias
            ORDER BY coincidencias DESC, vid LIMIT 30
        ''')
        if not vecinos:
            return []
        ids_vecinos = []
        casos = []
        for vecino in vecinos:
            ids_vecinos.append(vecino["vid"])
            casos.append(f'WHEN "{vecino["vid"]}" THEN {vecino["coincidencias"]}')
        # Cada vecino aporta sus coincidencias a las películas que recomienda.
        peso = "CASE id(u) " + " ".join(casos) + " ELSE 0 END"
        peliculas = ejecutar(sesion, f'''
            MATCH (u:Usuario)-[v:VALORA]->(p:Pelicula)
            WHERE id(u) IN {ids_vecinos} AND v.puntuacion >= 4
                  AND NOT p.Pelicula.movieId IN {excluidas}
            RETURN p.Pelicula.movieId AS movieId, p.Pelicula.titulo AS titulo,
                   p.Pelicula.anio AS anio, sum({peso}) AS afinidad,
                   count(DISTINCT u) AS apoyos, avg(v.puntuacion) AS media
            ORDER BY afinidad DESC, apoyos DESC, media DESC, movieId LIMIT 5
        ''')
        ids = []
        for pelicula in peliculas:
            ids.append("pelicula:" + str(pelicula["movieId"]))
            pelicula["generos"] = []
        if ids:
            generos = ejecutar(sesion, f'''
                MATCH (p:Pelicula)-[:PERTENECE_A]->(g:Genero)
                WHERE id(p) IN {ids}
                RETURN p.Pelicula.movieId AS movieId, g.Genero.nombre AS genero
                ORDER BY genero
            ''')
            for pelicula in peliculas:
                for genero in generos:
                    if genero["movieId"] == pelicula["movieId"]:
                        pelicula["generos"].append(genero["genero"])
        return peliculas


def generos_favoritos(user_id):
    with conectar() as sesion:
        return ejecutar(sesion, f'''
            MATCH (u:Usuario)-[v:VALORA]->(:Pelicula)-[:PERTENECE_A]->(g:Genero)
            WHERE id(u) == "usuario:{int(user_id)}"
            WITH g, count(v) AS peliculas, avg(v.puntuacion) AS media
            WHERE peliculas >= 5
            RETURN g.Genero.nombre AS genero, peliculas, media
            ORDER BY media DESC, peliculas DESC, genero LIMIT 5
        ''')
