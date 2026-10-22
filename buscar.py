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
    if args.limite < 1:
        parser.error("--limite debe ser positivo")
    resultados = buscar_semanticamente(args.texto, args.genero, args.desde, args.hasta, args.limite)
    print(f"\nBúsqueda: {args.texto!r} | {len(resultados)} resultados\n")
    for i, r in enumerate(resultados, 1):
        p = r.payload or {}
        print(f"{i}. {p.get('titulo')} ({p.get('anio')}) — similitud: {r.score:.4f}")
        print(f"   {', '.join(p.get('generos', []))}")
        print(f"   {p.get('sinopsis', '')}\n")
    if not resultados:
        print("No se encontraron resultados con esos filtros.")
    print("NOTA: la puntuación de similitud no es una probabilidad ni un porcentaje de acierto.")

if __name__ == "__main__":
    main()
