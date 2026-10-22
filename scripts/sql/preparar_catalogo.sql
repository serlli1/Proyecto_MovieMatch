-- MovieMatch | ETL MovieLens + TMDB
-- Este SQL se ejecuta desde 03_etl_duckdb.py.
-- Las rutas entre {{...}} se sustituyen por rutas locales previamente escapadas.
-- 1. Importar los CSV originales conservando todos los campos como texto.
-- El esquema de la fuente queda disponible para inspeccionar problemas.
CREATE OR REPLACE TABLE ml_movies_raw AS
SELECT * FROM read_csv({{MOVIES_CSV}}, header = true, all_varchar = true);
CREATE OR REPLACE TABLE ml_links_raw AS
SELECT * FROM read_csv({{LINKS_CSV}}, header = true, all_varchar = true);
CREATE OR REPLACE TABLE ml_ratings_raw AS
SELECT * FROM read_csv({{RATINGS_CSV}}, header = true, all_varchar = true);
-- Algunos registros de la fuente TMDB tienen una estructura irregular.
-- Se omiten solo las filas del CSV con errores de lectura.
CREATE OR REPLACE TABLE tmdb_raw AS
SELECT * FROM read_csv(
    {{TMDB_CSV}},
    header = true,
    all_varchar = true,
    ignore_errors = true,
    null_padding = true,
    max_line_size = 2000000
);
-- 2. Catálogo base de MovieLens: título, año y géneros traducidos.
CREATE OR REPLACE TABLE ml_peliculas AS
SELECT
    TRY_CAST(movieId AS BIGINT) AS movieId,
    TRIM(REGEXP_REPLACE(title, ' \([0-9]{4}\)$', '')) AS titulo,
    TRY_CAST(REGEXP_EXTRACT(title, '\(([0-9]{4})\)$', 1) AS INTEGER) AS anio,
    CASE
      WHEN genres IS NULL OR TRIM(genres) IN ('', '(no genres listed)')
        THEN []::VARCHAR[]
      ELSE LIST_TRANSFORM(STRING_SPLIT(genres, '|'), g -> CASE g
        WHEN 'Action' THEN 'Acción'
        WHEN 'Adventure' THEN 'Aventura'
        WHEN 'Animation' THEN 'Animación'
        WHEN 'Children' THEN 'Infantil'
        WHEN 'Children''s' THEN 'Infantil'
        WHEN 'Comedy' THEN 'Comedia'
        WHEN 'Crime' THEN 'Crimen'
        WHEN 'Documentary' THEN 'Documental'
        WHEN 'Drama' THEN 'Drama'
        WHEN 'Fantasy' THEN 'Fantasía'
        WHEN 'Film-Noir' THEN 'Cine negro'
        WHEN 'Horror' THEN 'Terror'
        WHEN 'IMAX' THEN 'IMAX'
        WHEN 'Musical' THEN 'Musical'
        WHEN 'Mystery' THEN 'Misterio'
        WHEN 'Romance' THEN 'Romance'
        WHEN 'Sci-Fi' THEN 'Ciencia ficción'
        WHEN 'Thriller' THEN 'Suspense'
        WHEN 'War' THEN 'Bélica'
        WHEN 'Western' THEN 'Wéstern'
        ELSE g END)
    END AS generos
FROM ml_movies_raw;
-- 3. Relación con proveedores externos, sin perder ceros de IMDb.
CREATE OR REPLACE TABLE ml_enlaces AS
WITH l AS (
    SELECT
        TRY_CAST(movieId AS BIGINT) AS movieId,
        TRY_CAST(NULLIF(TRIM(tmdbId), '') AS BIGINT) AS tmdbId,
        TRY_CAST(REGEXP_REPLACE(LOWER(TRIM(imdbId)), '^tt', '') AS BIGINT) AS imdb_num
    FROM ml_links_raw
)
SELECT
    movieId, tmdbId, imdb_num,
    CASE WHEN imdb_num IS NULL THEN NULL
         ELSE 'tt' || LPAD(CAST(imdb_num AS VARCHAR),
                           CAST(GREATEST(7, LENGTH(CAST(imdb_num AS VARCHAR))) AS INTEGER), '0')
    END AS imdbId
FROM l;
-- 4. Normalizar metadatos TMDB: IDs numéricos y sinopsis.
-- No se emparejan registros por título: únicamente mediante tmdbId +
-- una validación adicional de IMDb cuando los dos proveedores lo incluyen.
CREATE OR REPLACE TABLE tmdb_limpio AS
SELECT
    TRY_CAST(TRIM(id) AS BIGINT) AS tmdbId,
    TRY_CAST(REGEXP_REPLACE(LOWER(TRIM(imdb_id)), '^tt', '') AS BIGINT) AS imdb_num,
    NULLIF(TRIM(REGEXP_REPLACE(overview, '\s+', ' ', 'g')), '') AS sinopsis,
    TRY_CAST(SUBSTR(release_date, 1, 4) AS INTEGER) AS anio_tmdb
FROM tmdb_raw;
-- 5. Seleccionar una sola sinopsis válida por película de MovieLens.
-- Hay algunos tmdbId duplicados; se prioriza coincidencia IMDb, año y
-- extensión de la sinopsis. IMDb incompatibles se excluyen.
CREATE OR REPLACE TABLE tmdb_coincidencias AS
SELECT
    m.movieId,
    t.sinopsis,
    t.anio_tmdb,
    ROW_NUMBER() OVER (
        PARTITION BY m.movieId
        ORDER BY
            CASE WHEN e.imdb_num IS NOT NULL AND t.imdb_num = e.imdb_num
                 THEN 1 ELSE 0 END DESC,
            CASE WHEN m.anio IS NOT NULL AND t.anio_tmdb IS NOT NULL
                 THEN ABS(m.anio - t.anio_tmdb) ELSE 999 END ASC,
            LENGTH(t.sinopsis) DESC,
            t.sinopsis ASC
    ) AS prioridad
FROM ml_peliculas m
JOIN ml_enlaces e ON m.movieId = e.movieId
JOIN tmdb_limpio t ON e.tmdbId = t.tmdbId
WHERE t.sinopsis IS NOT NULL
  AND LENGTH(t.sinopsis) >= 40
  AND LOWER(t.sinopsis) NOT IN (
        'no overview found', 'no overview found.',
        'no description available', 'no description available.',
        'nan', 'none'
  )
  AND (e.imdb_num IS NULL OR t.imdb_num IS NULL OR e.imdb_num = t.imdb_num);
-- 6. Dimensión maestra: todas las películas, aunque falte sinopsis.
CREATE OR REPLACE TABLE peliculas AS
SELECT
    m.movieId,
    m.titulo,
    COALESCE(m.anio, c.anio_tmdb) AS anio,
    m.generos,
    e.tmdbId,
    e.imdbId,
    c.sinopsis
FROM ml_peliculas m
LEFT JOIN ml_enlaces e ON m.movieId = e.movieId
LEFT JOIN tmdb_coincidencias c ON m.movieId = c.movieId AND c.prioridad = 1;
-- 7. Subconjunto de Qdrant: únicamente películas con sinopsis aprovechable.
CREATE OR REPLACE TABLE peliculas_qdrant AS
SELECT movieId, titulo, anio, generos, tmdbId, imdbId, sinopsis
FROM peliculas
WHERE sinopsis IS NOT NULL;
-- 8. Datos para el futuro grafo NebulaGraph.
CREATE OR REPLACE TABLE valoraciones AS
SELECT
    TRY_CAST(userId AS BIGINT) AS userId,
    TRY_CAST(movieId AS BIGINT) AS movieId,
    TRY_CAST(rating AS DOUBLE) AS puntuacion,
    TRY_CAST(timestamp AS BIGINT) AS timestamp
FROM ml_ratings_raw;
CREATE OR REPLACE TABLE usuarios AS
SELECT DISTINCT userId FROM valoraciones WHERE userId IS NOT NULL;
CREATE OR REPLACE TABLE peliculas_generos AS
SELECT p.movieId, g.genero
FROM peliculas p
CROSS JOIN UNNEST(p.generos) AS g(genero);
