#!/usr/bin/env python3
"""
ya_lo_tengo — ¿tengo / he escuchado este disco?

Un único sitio para la pregunta que se hacen varias apps de tumtumpa
(dieta sonora, orpheus charts, discografía gaps, discos pendientes...):
para cada (artista, disco) responde si está en Airsonic, en qBittorrent,
si se ha escuchado (lastfm_stats.db: Last.fm + ListenBrainz) y si está en
la carpeta Mix (library.db de mixxx_info). Sin disco, responde por artista.

Además sirve /owned-badges.js, que cada app carga para pintar los cuatro
iconos sobre los elementos marcados con data-owned-artist/data-owned-album
(ver el propio script). Las listas se cachean en memoria _TTL segundos.
"""
import os
import re
import sqlite3
import threading
import time
import unicodedata

import requests
from flask import Flask, jsonify, request, send_from_directory

APP_DIR = os.path.dirname(os.path.abspath(__file__))

AIRSONIC_URL  = os.environ.get("AIRSONIC_URL", "").rstrip("/")
AIRSONIC_USER = os.environ.get("AIRSONIC_USER", "")
AIRSONIC_PASS = os.environ.get("AIRSONIC_PASS", "")
QB_HOST       = os.environ.get("QB_HOST", "")
QB_PORT       = os.environ.get("QB_PORT", "8080")
QB_USER       = os.environ.get("QB_USER", "")
QB_PASS       = os.environ.get("QB_PASS", "")
LASTFM_DB     = os.environ.get("LASTFM_DB", "/lastfm/lastfm_stats.db")
MIXXX_DB      = os.environ.get("MIXXX_DB", "/mixxx/library.db")
PORT          = int(os.environ.get("PORT", "5000"))

_TTL = 600
MAX_ITEMS = 500

app = Flask(__name__)


# ── Normalización y cruce (mismo criterio que charts_orpheus) ────────────────

def norm(s):
    """Minúsculas, sin acentos ni puntuación, espacios simples."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^\w]+", " ", s.replace("&", " and "))
    return re.sub(r"\s+", " ", s).strip()


def artist_match(a, b):
    return a == b or (len(a) >= 3 and len(b) >= 3 and (a in b or b in a))


def album_match(a, b):
    return a == b or (len(a) >= 4 and a in b) or (len(b) >= 4 and b in a)


# ── Fuentes ──────────────────────────────────────────────────────────────────

def _airsonic():
    """[(artista, álbum)] normalizados de toda la biblioteca, o None."""
    if not (AIRSONIC_URL and AIRSONIC_USER):
        return None
    out, offset = [], 0
    try:
        while True:
            r = requests.get(AIRSONIC_URL + "/rest/getAlbumList2", timeout=15, params={
                "u": AIRSONIC_USER, "p": AIRSONIC_PASS, "v": "1.15.0", "c": "ya_lo_tengo",
                "f": "json", "type": "alphabeticalByName", "size": 500, "offset": offset,
            })
            albums = r.json()["subsonic-response"].get("albumList2", {}).get("album", [])
            out += [(norm(a.get("artist")), norm(a.get("name"))) for a in albums]
            if len(albums) < 500:
                return out
            offset += 500
    except Exception as e:
        print(f"Airsonic no disponible: {e}")
        return None


def _qbittorrent():
    """Nombres normalizados de los torrents, o None."""
    if not QB_HOST:
        return None
    base = f"http://{QB_HOST}:{QB_PORT}/api/v2"
    try:
        sess = requests.Session()
        sess.post(base + "/auth/login", data={"username": QB_USER, "password": QB_PASS}, timeout=10)
        r = sess.get(base + "/torrents/info", timeout=15)
        r.raise_for_status()
        return [norm(t.get("name")) for t in r.json()]
    except Exception as e:
        print(f"qBittorrent no disponible: {e}")
        return None


def _ro(path):
    # immutable=1: los .db vienen montados :ro (lastfm_stats.db además en WAL)
    return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)


def _lastfm():
    """({(artista, álbum): (escuchas, último ts)}, {artista: escuchas}), o None."""
    if not os.path.exists(LASTFM_DB):
        return None
    try:
        con = _ro(LASTFM_DB)
        albums, artists = {}, {}
        for ar, al, n, ts in con.execute("""
                SELECT ar.name, al.name, COUNT(*), MAX(s.ts) FROM scrobbles s
                JOIN albums al  ON al.album_id  = s.album_id
                JOIN artists ar ON ar.artist_id = al.artist_id
                GROUP BY al.album_id"""):
            key = (norm(ar), norm(al))
            prev = albums.get(key, (0, 0))
            albums[key] = (prev[0] + n, max(prev[1], ts or 0))
        for ar, n in con.execute("""
                SELECT ar.name, COUNT(*) FROM scrobbles s
                JOIN artists ar ON ar.artist_id = s.artist_id
                GROUP BY s.artist_id"""):
            artists[norm(ar)] = artists.get(norm(ar), 0) + n
        con.close()
        return albums, artists
    except Exception as e:
        print(f"lastfm_stats.db no disponible: {e}")
        return None


def _mix():
    """({(artista, álbum): nº de temas}, {artista: nº de temas}) de la carpeta Mix, o None."""
    if not os.path.exists(MIXXX_DB):
        return None
    try:
        con = _ro(MIXXX_DB)
        albums, artists = {}, {}
        for ar, al, n in con.execute(
                "SELECT artist, album, COUNT(*) FROM songs WHERE artist IS NOT NULL GROUP BY artist, album"):
            na = norm(ar)
            artists[na] = artists.get(na, 0) + n
            if al:
                key = (na, norm(al))
                albums[key] = albums.get(key, 0) + n
        con.close()
        return albums, artists
    except Exception as e:
        print(f"library.db de mixxx_info no disponible: {e}")
        return None


_cache = {"t": 0}
_lock = threading.Lock()


def library(refresh=False):
    with _lock:
        if refresh or time.time() - _cache["t"] > _TTL:
            _cache.update(t=time.time(), airsonic=_airsonic(), qbittorrent=_qbittorrent(),
                          lastfm=_lastfm(), mix=_mix())
        return _cache


# ── Respuesta ────────────────────────────────────────────────────────────────

def owned(lib, artist, album):
    na, nb = norm(artist), norm(album)
    out = {"airsonic": None, "qbittorrent": None, "listened": None, "mix": None}
    if not na:
        return out

    if lib["airsonic"] is not None:
        out["airsonic"] = any(artist_match(na, fa) and (not nb or album_match(nb, fb))
                              for fa, fb in lib["airsonic"])
    if lib["qbittorrent"] is not None:
        out["qbittorrent"] = any(na in t and (not nb or nb in t) for t in lib["qbittorrent"])
    if lib["lastfm"] is not None:
        lfm_albums, lfm_artists = lib["lastfm"]
        if nb:
            plays, last = 0, 0
            for (fa, fb), (n, ts) in lfm_albums.items():
                if artist_match(na, fa) and album_match(nb, fb):
                    plays, last = plays + n, max(last, ts)
        else:
            plays = sum(n for fa, n in lfm_artists.items() if artist_match(na, fa))
            last = 0
        out["listened"] = {"plays": plays,
                           "last": time.strftime("%Y-%m-%d", time.gmtime(last)) if last else None}
    if lib["mix"] is not None:
        mix_albums, mix_artists = lib["mix"]
        if nb:
            out["mix"] = sum(n for (fa, fb), n in mix_albums.items() if artist_match(na, fa) and album_match(nb, fb))
        else:
            out["mix"] = sum(n for fa, n in mix_artists.items() if artist_match(na, fa))
    return out


@app.after_request
def _cors(resp):
    # Lo consultan, desde el navegador, las webs de los demás servicios (otro puerto)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.route("/api/owned", methods=["GET", "POST", "OPTIONS"])
def api_owned():
    """GET ?artist=&album=  -> un resultado.
    POST {"items": [{"artist", "album"}, ...]}  -> {"results": [...], "sources": {...}}."""
    if request.method == "OPTIONS":
        return "", 204
    lib = library(request.args.get("refresh") == "1")
    sources = {k: lib[k] is not None for k in ("airsonic", "qbittorrent", "lastfm", "mix")}
    if request.method == "GET":
        return jsonify({**owned(lib, request.args.get("artist", ""), request.args.get("album", "")),
                        "sources": sources})
    items = ((request.get_json(silent=True) or {}).get("items") or [])[:MAX_ITEMS]
    return jsonify({"results": [owned(lib, i.get("artist", ""), i.get("album", "")) for i in items],
                    "sources": sources})


@app.route("/owned-badges.js")
def badges_js():
    resp = send_from_directory(APP_DIR, "owned-badges.js", mimetype="application/javascript")
    resp.headers["Cache-Control"] = "max-age=300"
    return resp


@app.route("/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
