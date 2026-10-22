"""Uso: python buscar.py "viajes espaciales" --genero "Ciencia ficción"""
import argparse

from src.motor import buscar_semanticamente


def main():
    parser = argparse.ArgumentParser(description="Buscador semántico de películas con Qdrant")
    parser.add_argument("texto", help="Lo que te apetece ver, en lenguaje natural")
    parser.add_argument("--genero", help='Filtro exacto; ej. "Ciencia ficción"')
    parser.add_argument("--desde", type=int, help="Año mínimo")
    parser.add_argument("--hasta", type=int, help="Año máximo")
    parser.add_argument("--limite", type=int, default=5)
    args = parser.parse_args()
    try:
        resultados = buscar_semanticamente(
            args.texto, args.genero, args.desde, args.hasta, args.limite
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(f"\nBúsqueda: {args.texto!r} | {len(resultados)} resultados\n")
    for puesto, resultado in enumerate(resultados, 1):
        pelicula = resultado.payload or {}
        titulo = pelicula.get("titulo")
        anio = pelicula.get("anio") or "—"
        generos = ", ".join(pelicula.get("generos", []))
        print(
            f"{puesto}. {titulo} ({anio}) "
            f"— similitud: {resultado.score:.4f}"
        )
        print(f"   {generos}")
        print(f"   {pelicula.get('sinopsis', '')}\n")
    if not resultados:
        print("No se encontraron resultados con esos filtros.")
    print("NOTA: la puntuación de similitud no es una probabilidad ni un porcentaje de acierto.")


if __name__ == "__main__":
    main()
