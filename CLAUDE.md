# ya_lo_tengo

API Flask (`app.py`) que cruza un artista + disco con cuatro fuentes opcionales y `owned-badges.js`, que pinta el resultado en otras webs.

- Fuentes: Subsonic (`AIRSONIC_*`), qBittorrent (`QB_*`), `LASTFM_DB` (tablas `scrobbles`, `albums`, `artists` de lastfm_scrobbles) y `MIXXX_DB` (tabla `songs` de mixxx_info). Una fuente sin configurar devuelve `null`, nunca `false`.
- Las bases se abren con `mode=ro&immutable=1`: llegan montadas en solo lectura.
- Cache en memoria de 10 min (`_TTL`); `?refresh=1` la vacía.
- `norm()`, `artist_match()` y `album_match()` deciden qué cuenta como el mismo disco; si se cambian, cambia lo que ven todas las webs que cargan los iconos.
- Ninguna ruta, usuario ni contraseña va en el código: todo llega por variables de entorno (`.env.example`).
