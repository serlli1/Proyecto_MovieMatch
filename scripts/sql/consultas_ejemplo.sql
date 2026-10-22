-- Ejemplos para documentar el ETL y ejecutarlos en DuckDB.
-- Puedes abrir datos/moviematch.duckdb con DuckDB CLI o cualquier cliente SQL.

-- 1. Cuántas películas y sinopsis válidas tenemos.
SELECT
    COUNT(*) AS peliculas_totales,
    COUNT(sinopsis) AS con_sinopsis,
    ROUND(100.0 * COUNT(sinopsis) / COUNT(*), 2) AS cobertura_pct
FROM peliculas;

-- 2. Películas sin sinopsis, con información del proveedor externo.
SELECT movieId, titulo, anio, tmdbId, imdbId
FROM peliculas
WHERE sinopsis IS NULL
ORDER BY movieId
LIMIT 20;

-- 3. Detectar códigos TMDB duplicados en la fuente original.
SELECT tmdbId, COUNT(*) AS repeticiones
FROM tmdb_limpio
WHERE tmdbId IS NOT NULL
GROUP BY tmdbId
HAVING COUNT(*) > 1
ORDER BY repeticiones DESC, tmdbId;

-- 4. Validación referencial: la consulta debería devolver 0.
SELECT COUNT(*) AS valoraciones_sin_pelicula
FROM valoraciones v
LEFT JOIN peliculas p ON p.movieId = v.movieId
WHERE p.movieId IS NULL;

-- 5. Cinco películas más valoradas (mínimo 30 valoraciones).
SELECT
    p.movieId, p.titulo,
    COUNT(*) AS num_valoraciones,
    ROUND(AVG(v.puntuacion), 2) AS media
FROM valoraciones v
JOIN peliculas p ON p.movieId = v.movieId
GROUP BY p.movieId, p.titulo
HAVING COUNT(*) >= 30
ORDER BY media DESC, num_valoraciones DESC
LIMIT 5;
