# ya_lo_tengo

¿Tengo este disco? ¿Lo he escuchado? Una pequeña API que responde por cada artista y disco, y un script que cualquier web puede cargar para pintar la respuesta como iconos al lado de cada disco.

| Icono | Fuente | Qué dice |
|---|---|---|
| **A** | Servidor Subsonic (Airsonic, Navidrome…) | El disco está en tu biblioteca |
| **qB** | qBittorrent | Lo tienes en descarga |
| **♫** | `lastfm_stats.db` de [lastfm_scrobbles](https://github.com/volteret4/lastfm_scrobbles) | Cuántas veces lo has escuchado y cuándo fue la última |
| **M** | `library.db` de [mixxx_info](https://github.com/volteret4/mixxx_info) | Cuántas canciones suyas tienes en tu carpeta de DJ |

Todas son opcionales: empieza con una y añade las demás cuando quieras. Sin disco, responde por artista.

## Instalación

Necesitas Docker.

```bash
git clone https://github.com/volteret4/ya_lo_tengo.git && cd ya_lo_tengo && cp .env.example .env
```

Rellena en `.env` las fuentes que tengas. Si vas a usar las bases de escuchas o de Mix, pon en `LASTFM_DIR` y `MIXXX_DIR` las carpetas donde están (`lastfm_stats.db` y `library.db`). Después:

```bash
mkdir -p datos/lastfm datos/mixxx && docker compose up -d --build
```

Comprueba que responde:

```bash
curl 'http://localhost:8780/api/owned?artist=Radiohead&album=Kid%20A'
```

```json
{"airsonic": true, "qbittorrent": null, "listened": {"plays": 41, "last": "2026-10-02"}, "mix": null,
 "sources": {"airsonic": true, "qbittorrent": false, "lastfm": true, "mix": false}}
```

`null` significa que esa fuente no está configurada; `false`, que está pero no lo tiene.

Sin Docker: `pip install -r requirements.txt`, exporta las variables de `.env` y lanza `python app.py` (con `LASTFM_DB` y `MIXXX_DB` apuntando a los ficheros).

## Iconos en tus webs

Marca cada disco con `data-owned-artist` y, si quieres, `data-owned-album`, y carga el script:

```html
<li data-owned-artist="Radiohead" data-owned-album="Kid A">Kid A</li>
<script src="http://localhost:8780/owned-badges.js"></script>
```

El script pinta los iconos dentro de cada elemento marcado (o dentro de un hijo con `data-owned-slot`), también en lo que la web añada después. Agrupa las consultas de 200 en 200 y las guarda en memoria. `OwnedBadges.refresh()` vuelve a preguntar.

## API

| Llamada | Respuesta |
|---|---|
| `GET /api/owned?artist=&album=` | Un resultado y qué fuentes hay (`sources`) |
| `POST /api/owned` con `{"items": [{"artist", "album"}, …]}` | `{"results": […], "sources": {…}}`, hasta 500 a la vez |
| `GET /api/owned?…&refresh=1` | Lo mismo, releyendo las fuentes |
| `GET /owned-badges.js` | El script de los iconos |
| `GET /health` | `{"ok": true}` |

La API admite peticiones desde cualquier origen (CORS), porque la consultan webs servidas en otros puertos. Las fuentes se releen cada 10 minutos.

El cruce de nombres no distingue mayúsculas, acentos ni puntuación, y acepta que uno contenga al otro («Kid A» y «Kid A (Remastered)»).

## Parte de REPEAT-ONE

Este servicio es uno de los módulos de [REPEAT-ONE](https://volteret4.github.io/repeat-one-web/); allí lo usan dieta sonora, los charts, discografía gaps o discos pendientes. Funciona igual por separado.
