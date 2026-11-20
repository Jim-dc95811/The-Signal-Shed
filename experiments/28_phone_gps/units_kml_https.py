#!/usr/bin/env python3
"""units_kml.py - The Lookout: live units KML server  (Claude + Jim, 2026-11-14)

The second half of the Lookout. bk_bridge.py puts clean NMEA on the network (:10110);
this reads that feed, pairs each position with its unit ID, and serves a live
units.kml on :8080. Any ArcGIS Earth on the LAN opens a NetworkLink to it once and
the units move on their own - no Python, no install on the viewing PC.

It reads the BRIDGE's feed, not the radio, so it never opens a second connection to
the radio and it works with any NMEA source the bridge is serving.

v1.1 (2026-11-15): writes a daily CSV track log of every fix (logs/track_YYYY-MM-DD.csv)
so there is a persistent record after an incident. Each row is time-stamped from the
GPS fix itself when the radio also sends $..RMC (which carries the date) - that stays
accurate even when the box is offline and its own clock has drifted; it falls back to
the box clock, flagged, when no GPS date has been seen. The live map is unchanged.

v1.2 (2026-11-15): RADIO LINK ALARM. The bridge announces its radio link state
($PLKT,LINK,UP/DOWN). The instant the radio is unplugged (DOWN), or the bridge itself
goes unreachable, a big red "RADIO LINK DOWN" marker drops on the map and every unit is
flagged - no 90-second wait for units to go stale. "Nobody is transmitting" (link UP,
units quiet) is NOT an alarm, which only the bridge can tell apart. When the link is
healthy the units.kml is byte-for-byte identical to v1.1.

Run (normal):  python3 units_kml.py              # reads the bridge on 127.0.0.1:10110
Run (demo):    python3 units_kml.py --demo        # 3 moving synthetic units, no radio
Stop:          Ctrl+C
Serves:        http://<this-box>:8080/units.kml
Optional:      aliases.json beside this file = {"7101": "Engine 7", ...}
Writes:        logs/track_YYYY-MM-DD.csv  (one row per real fix)
Admin:         GET/POST http://<this-box>:8080/admin/aliases?token=...  (the Alias Manager app)

v1.3 (2026-11-15): token-guarded /admin/aliases endpoint so the Alias Manager PC app can
read and replace the unit id -> name table over the LAN. Names take effect within one map
refresh (aliases.json is already read live). Token default "lookout"; override with
admin_token.txt beside this file.

v1.11 (2026-11-16): field hardening - a .tpkx read that fails because its SSD vanished mid-
serve (cable jostled / drive unplugged) no longer errors the request; it drops the stale
reader, serves a blank tile, and rebuilds the reader when the drive remounts. The feed and
the units keep flowing throughout.

v1.12 (2026-11-16): NO DEFAULT MAP. The router holds no map and has no concept of a "default"
or privileged basemap - no basemap.* symlink, nothing served at "/" as special. It simply scans
whatever removable drive is mounted (/tmp/mountd/*; override with LOOKOUT_MAP_ROOTS) and serves
every .tpkx/.mbtiles it finds, all equal, each at /m/<slug>/, sorted ALPHABETICALLY by file name.
The bare URL "/" just shows whichever map sorts first - crews control that by naming (prefix a
file "1_" or "a_"). Swap drives freely; the box stays generic and carries no map of its own.

v1.10 (2026-11-15): MANY MAPS, one per link. Every .tpkx/.mbtiles found beside the default
basemap (e.g. dropped on the SSD) is served at its own URL /m/<slug>/ with the live units on
top; /maps.json lists them and the page has a Maps menu to jump between them. The default
basemap still loads at / unchanged. Two viewers can be on different maps at once; drop a new
map file on the drive and it appears within ~10 s, no restart. (v1.4-1.9: the in-browser live
slippy map - Leaflet over offline MBTiles, then Esri .tpkx too, reboot-safe; see git history.)
"""
import re, time, math, json, socket, threading, sys, argparse
from collections import deque
from pathlib import Path
import os, sqlite3, struct, zipfile, ssl
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

VERSION = "1.13"

# v1.13 (Signal Shed #28): optional HTTPS on :8443 so a phone can share its OWN GPS back
# (browsers gate geolocation/camera/mic to secure contexts). Enabled ONLY when certs are
# present (certs/server.crt + server.key) - otherwise byte-for-byte identical to v1.12 and
# :8080 http stays exactly as before for the map viewers. The box serves its fleet CA at
# /ca, a "share my position" page at /share, and accepts a phone fix at POST /report, which
# folds that phone into the same live unit list. Generate the certs with make_certs.sh.

# ---- where we read from / serve to ----
BRIDGE_HOST = "127.0.0.1"     # the bridge's NMEA feed (same box)
BRIDGE_PORT = 10110
SERVE_HOST  = "0.0.0.0"       # serve units.kml to the whole LAN
SERVE_PORT  = 8080
STALE_S     = 90             # a unit with no update this long is labelled "stale"
EXPIRE_S    = 7200           # ...and dropped from the map after this long (0 = never)
RECONNECT_S = 4
ALARM_AFTER_S = 15          # no LINK status heard from the bridge this long -> treat as down
ALARM_ANCHOR  = None        # (lat, lon) to pin the alarm when no units are known; None = skip
ADMIN_TOKEN_DEFAULT = "lookout"   # shared token for the Alias Manager; override via admin_token.txt
ALIASES_PATH  = Path(__file__).with_name("aliases.json")   # unit id -> name, read live every refresh
LOG_DIR     = Path(__file__).with_name("logs")   # daily track CSVs land here
HTTPS_PORT  = 8443          # TLS listener for secure-context features; OFF unless certs present
CERT_DIR    = Path(__file__).with_name("certs")   # server.crt + server.key enable https; lookout-ca.crt served at /ca

# ---------- offline maps: served straight off whatever removable drive is plugged in ----------
# .tpkx is Esri Compact Cache V2 (exactly what mb2tpkx / ArcGIS Earth use) and .mbtiles is SQLite;
# the backend is picked by file extension. The router stores NO map and has NO "default": it just
# serves every map found on the mounted USB drive(s), as equals. Crews order them by FILE NAME
# (prefix a map "1_" or "a_" to make it the one the bare URL shows first).
# Where removable drives mount: OpenWrt/GL mountd uses /tmp/mountd/<diskN_partM>/. Override or
# extend for a Pi (e.g. "/mnt:/media") via LOOKOUT_MAP_ROOTS (os.pathsep-separated).
MAP_ROOTS = [p for p in (os.environ.get("LOOKOUT_MAP_ROOTS") or "/tmp/mountd").split(os.pathsep) if p]
_ASSET_DIR   = Path(__file__).resolve().parent
_meta_cache  = {}          # realpath -> meta dict (cached on a good read only)
_readers     = {}          # realpath -> _Tpkx instance (tpkx only; mbtiles open per request)
_maps_cache  = {}          # slug -> {path, real, name, tpkx}
_maps_ts     = [0.0]       # last discovery time (monotonic)
_maps_lock   = threading.Lock()

class _Tpkx:
    """Read tiles straight out of an Esri Compact Cache V2 .tpkx by direct seek (thread-safe)."""
    def __init__(self, path):
        self.path = path; self._tl = threading.local(); self._dataoff = {}
        z = zipfile.ZipFile(path)
        self._hdroff = {zi.filename: zi.header_offset for zi in z.infolist() if zi.filename.endswith(".bundle")}
        root = json.loads(z.read("root.json")); item = json.loads(z.read("iteminfo.json"))
        lods = root["tileInfo"]["lods"]
        self.minzoom = int(root.get("minLOD", lods[0]["level"]))
        self.maxzoom = int(root.get("maxLOD", lods[-1]["level"]))
        e = item["extent"]; self.bounds = [e["xmin"], e["ymin"], e["xmax"], e["ymax"]]
        z.close()
    def _fh(self):
        f = getattr(self._tl, "f", None)
        if f is None:
            f = self._tl.f = open(self.path, "rb")
        return f
    def _base(self, name):
        off = self._dataoff.get(name)
        if off is None:
            f = self._fh(); ho = self._hdroff[name]
            f.seek(ho + 26); n, m = struct.unpack("<HH", f.read(4))   # local header: name + extra len
            off = self._dataoff[name] = ho + 30 + n + m
        return off
    def tile(self, z, x, y):
        rb = (y // 128) * 128; cb = (x // 128) * 128
        name = "tile/L%02d/R%04xC%04x.bundle" % (z, rb, cb)
        if name not in self._hdroff:
            return None
        base = self._base(name); f = self._fh()
        f.seek(base + 64 + ((y - rb) * 128 + (x - cb)) * 8)
        v = int.from_bytes(f.read(8), "little"); off = v & ((1 << 40) - 1); sz = v >> 40
        if sz == 0:
            return None
        f.seek(base + off); return f.read(sz)
    def meta(self):
        return {"has_tiles": True, "minzoom": self.minzoom, "maxzoom": self.maxzoom, "bounds": self.bounds}

def _tpkx_path(p):
    return p.lower().endswith(".tpkx")

def _reader_for(path):
    """Cached _Tpkx reader per file (keyed by realpath). Returns None when a .tpkx can't be
    opened yet (e.g. the SSD isn't mounted) so callers keep retrying; MBTiles -> "mbtiles"."""
    if not _tpkx_path(path):
        return "mbtiles"
    key = os.path.realpath(path)
    r = _readers.get(key)
    if r is not None:
        return r
    with _maps_lock:
        r = _readers.get(key)
        if r is None:
            try:
                r = _readers[key] = _Tpkx(path)
            except Exception:
                return None
    return r

def meta_for(path):
    """Bounds + zoom range for one map file, cached per file on a good read only (so a map
    whose drive isn't mounted yet keeps being retried instead of cached empty)."""
    key = os.path.realpath(path)
    cached = _meta_cache.get(key)
    if cached:
        return cached
    blank = {"has_tiles": False, "minzoom": 0, "maxzoom": 20, "bounds": [-180.0, -85.0, 180.0, 85.0]}
    if _tpkx_path(path):
        r = _reader_for(path)
        if r and r != "mbtiles":
            m = r.meta(); _meta_cache[key] = m; return m
        return blank
    m = dict(blank)
    try:
        c = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5)
        md = dict(c.execute("select name, value from metadata").fetchall())
        if md.get("bounds"):
            m["bounds"] = [float(x) for x in md["bounds"].split(",")][:4]
        if md.get("minzoom"): m["minzoom"] = int(float(md["minzoom"]))
        if md.get("maxzoom"): m["maxzoom"] = int(float(md["maxzoom"]))
        m["has_tiles"] = True
        c.close()
    except Exception:
        pass
    if m["has_tiles"]:
        _meta_cache[key] = m
    return m

def tile_for(path, z, x, y):
    if _tpkx_path(path):
        r = _reader_for(path)
        if not r or r == "mbtiles":
            return None
        try:
            return r.tile(z, x, y)
        except Exception:
            # the SSD vanished mid-read (cable jostled / unplugged). Drop the stale reader so
            # it rebuilds when the drive remounts; serve a blank tile meanwhile, never crash.
            with _maps_lock:
                _readers.pop(os.path.realpath(path), None)
            return None
    # MBTiles: Leaflet asks XYZ (y=0 at north); MBTiles stores TMS (row 0 at south) -> flip.
    try:
        c = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5)
        row = c.execute("select tile_data from tiles where zoom_level=? and tile_column=? and tile_row=?",
                        (z, x, (1 << z) - 1 - y)).fetchone()
        c.close()
        return row[0] if row else None
    except Exception:
        return None

# ---------- discover every map on the mounted drive(s): all equal, no default ----------
def _scan_dirs():
    """Each directory to look in for maps: every mounted partition under each map root, plus the
    root itself (so LOOKOUT_MAP_ROOTS may point straight at a maps folder, e.g. on a Pi)."""
    dirs = []
    for root in MAP_ROOTS:
        r = Path(root)
        try:
            if not r.is_dir():
                continue
            dirs.append(r)
            for d in sorted(r.iterdir()):
                try:
                    if d.is_dir():
                        dirs.append(d)
                except OSError:
                    pass
        except OSError:
            pass
    return dirs

def _slugify(stem):
    s = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return s or "map"

def _discover_maps():
    """slug -> {path, real, name, tpkx}. Every .tpkx/.mbtiles on any mounted removable drive,
    all equal - no default, and nothing from the router's own flash. The router holds no map."""
    found = {}; seen = {}
    def add(path):
        try:
            real = os.path.realpath(path)
        except OSError:
            return
        if real in seen or not os.path.exists(real):
            return
        name = Path(real).stem
        base = _slugify(name); slug = base; n = 2
        while slug in found:
            slug = "%s-%d" % (base, n); n += 1
        found[slug] = {"path": str(path), "real": real, "name": name, "tpkx": _tpkx_path(str(path))}
        seen[real] = slug
    for d in _scan_dirs():
        try:
            entries = sorted(d.glob("*.tpkx")) + sorted(d.glob("*.mbtiles"))
        except OSError:
            entries = []
        for p in entries:
            add(str(p))
    return found

def _maps(force=False):
    now = time.monotonic()
    if force or not _maps_cache or now - _maps_ts[0] > 10:   # re-scan ~every 10s: drop a file, it appears
        with _maps_lock:
            if force or not _maps_cache or now - _maps_ts[0] > 10:
                fresh = _discover_maps()
                _maps_cache.clear(); _maps_cache.update(fresh)
                _maps_ts[0] = now
    return _maps_cache

def _maps_list():
    out = []
    for slug, info in _maps().items():
        m = meta_for(info["path"])
        out.append({"slug": slug, "name": info["name"], "base": "/m/%s/" % slug,
                    "has_tiles": m.get("has_tiles", False), "bounds": m.get("bounds")})
    out.sort(key=lambda e: e["name"].lower())   # name-ordered; prefix a file 1_/a_ to sort it first
    return out

_CTYPE = {".js": "application/javascript", ".css": "text/css", ".html": "text/html; charset=utf-8"}
def _serve_asset(h, name):
    try:
        data = (_ASSET_DIR / name).read_bytes()
    except OSError:
        h.send_error(404); return
    h.send_response(200)
    h.send_header("Content-Type", _CTYPE.get(Path(name).suffix, "application/octet-stream"))
    h.send_header("Content-Length", str(len(data)))
    h.send_header("Cache-Control", "no-store" if name.endswith(".html") else "max-age=86400")
    h.end_headers()
    h.wfile.write(data)

# ---- diagnostic: who pulls units.kml, and how often (answers "does this client auto-refresh?") ----
_fetch_log  = deque(maxlen=400)          # (epoch, client_ip) for each units.kml GET
_fetch_lock = threading.Lock()

def _note_fetch(ip):
    with _fetch_lock:
        _fetch_log.append((time.time(), ip))

def _fetchlog_report():
    """Plain-text report: per-client pull cadence (static load vs. timed refresh), then raw hits."""
    with _fetch_lock:
        rows = list(_fetch_log)
    now = time.time()
    lines = ["The Lookout - units.kml fetch log   (now %s)" % time.strftime("%H:%M:%S", time.localtime(now)),
             "Each client that opens the live map pulls units.kml. One pull = static load;",
             "a pull every few seconds = it honors the NetworkLink refresh.",
             ""]
    by_ip = {}
    for ts, ip in rows:
        by_ip.setdefault(ip, []).append(ts)
    if not by_ip:
        lines.append("(no pulls yet - open the map on a device, then reload this page)")
    else:
        lines.append("Per device:")
        for ip in sorted(by_ip):
            tss = by_ip[ip]
            n = len(tss)
            last_ago = now - tss[-1]
            if n == 1:
                verdict = "1 pull - loaded once (STATIC, no auto-refresh seen yet)"
            else:
                w = tss[-20:]
                gaps = [b - a for a, b in zip(w, w[1:]) if b - a > 0]
                med = sorted(gaps)[len(gaps) // 2] if gaps else 0
                if med and med <= 20:
                    verdict = "%d pulls, every ~%.1fs - REFRESHING on a timer" % (n, med)
                else:
                    verdict = "%d pulls, spread over %.0fs - irregular" % (n, tss[-1] - tss[0])
            lines.append("  %-16s  %s   (last %.0fs ago)" % (ip, verdict, last_ago))
        lines.append("")
        lines.append("Recent pulls (newest last):")
        for ts, ip in rows[-40:]:
            lines.append("  %s   %s" % (time.strftime("%H:%M:%S", time.localtime(ts)), ip))
    return ("\n".join(lines) + "\n").encode("utf-8")

# ---------- NMEA parser: lifted verbatim from the P25 GPS Tracker (p25_core.py) ----------
_SENTENCE = re.compile(r"\$[^*$\r\n]{2,88}\*[0-9A-Fa-f]{2}")

def _nmea_ok(s):
    body, _, chk = s[1:].partition("*")
    try:
        want = int(chk[:2], 16)
    except ValueError:
        return False
    g = 0
    for c in body:
        g ^= ord(c)
    return g == want

def _to_deg(value, hemi, deg_digits):
    if not value:
        return None
    try:
        d = int(value[:deg_digits]); m = float(value[deg_digits:])
    except ValueError:
        return None
    dd = d + m / 60.0
    return -dd if hemi in ("S", "W") else dd

def _valid_coord(lat, lon):
    if lat is None or lon is None:
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return False
    if abs(lat) < 1e-6 and abs(lon) < 1e-6:     # null island = no real fix
        return False
    return True

# Last date seen in a $..RMC sentence (DDMMYY). GGA carries no date, so this is the
# only GPS-sourced date; it lets the track log stay accurate with a drifted box clock.
_last_gps_date = None

# Radio link state, learned from the bridge's $PLKT,LINK,* heartbeat.
_link_state = "unknown"       # "up" / "down" / "unknown"
_link_seen  = 0.0             # monotonic time of the last LINK status heard

class Report:
    __slots__ = ("unit", "lat", "lon", "alt", "sats", "utc")
    def __init__(self, unit, lat, lon, alt, sats, utc):
        self.unit, self.lat, self.lon, self.alt, self.sats, self.utc = unit, lat, lon, alt, sats, utc

class StreamParser:
    """Feed raw bytes; yields paired (GGA position + PP25 unit id) Reports."""
    def __init__(self):
        self._buf = bytearray()
        self._pending = None
    def feed(self, data: bytes):
        global _last_gps_date, _link_state, _link_seen
        out = []
        self._buf.extend(data)
        text = self._buf.decode("latin-1")
        last_end = 0
        for m in _SENTENCE.finditer(text):
            s = m.group(0); last_end = m.end()
            if not _nmea_ok(s):
                continue
            f = s.split(",")
            tag = f[0][1:]
            if tag.endswith("GGA") and len(f) >= 10:
                lat = _to_deg(f[2], f[3], 2); lon = _to_deg(f[4], f[5], 3)
                if f[6] in ("", "0") or not _valid_coord(lat, lon):
                    self._pending = None
                    continue
                self._pending = {"lat": lat, "lon": lon, "alt": f[9], "sats": f[7], "utc": f[1]}
            elif tag == "PP25" and len(f) >= 2 and f[1]:
                if self._pending is not None:
                    p = self._pending
                    out.append(Report(f[1], p["lat"], p["lon"], p["alt"], p["sats"], p["utc"]))
                    self._pending = None
            elif tag.endswith("RMC") and len(f) >= 10:
                d = f[9]                        # DDMMYY; keep for offline-accurate log timestamps
                if len(d) == 6 and d.isdigit():
                    _last_gps_date = d
            elif tag == "PLKT" and len(f) >= 3 and f[1] == "LINK":
                _link_state = "up" if f[2].split("*")[0] == "UP" else "down"
                _link_seen = time.monotonic()
        if last_end:
            del self._buf[:last_end]
        if len(self._buf) > 8192:
            del self._buf[:-2048]
        return out

# ---------- live unit state ----------
_units = {}                 # unit id -> dict(lat, lon, alt, sats, utc, seen=monotonic)
_lock = threading.Lock()
_bridge_connected = False   # are we currently reading from the bridge?
_ever_connected   = False   # have we ever reached the bridge? (no alarm before first contact)

def _put(rep):
    with _lock:
        _units[str(rep.unit)] = {"lat": rep.lat, "lon": rep.lon, "alt": rep.alt,
                                 "sats": rep.sats, "utc": rep.utc, "seen": time.monotonic()}

def _put_phone(uid, lat, lon, acc):
    """A phone reported its own GPS (POST /report over https). Fold it into the same live
    list as the radio units, flagged phone=True so the map can mark it apart."""
    with _lock:
        _units[str(uid)] = {"lat": lat, "lon": lon, "alt": "0", "sats": "", "utc": "",
                            "seen": time.monotonic(), "phone": True, "acc": acc}

# ---------- daily track log ----------
def _log_fix(rep):
    """Append one row per real fix. Never let a logging error break the live feed."""
    hhmmss = (rep.utc or "")[:6]
    if _last_gps_date and len(hhmmss) == 6 and hhmmss.isdigit():
        yy, mm, dd = _last_gps_date[4:6], _last_gps_date[2:4], _last_gps_date[0:2]
        date = f"20{yy}-{mm}-{dd}"
        iso  = f"{date}T{hhmmss[0:2]}:{hhmmss[2:4]}:{hhmmss[4:6]}Z"
        src  = "gps"
    else:
        date = time.strftime("%Y-%m-%d")
        iso  = time.strftime("%Y-%m-%dT%H:%M:%S")
        src  = "box"                            # box clock - may be wrong if offline with no RTC
    try:
        LOG_DIR.mkdir(exist_ok=True)
        path = LOG_DIR / f"track_{date}.csv"
        new = not path.exists()
        with path.open("a", encoding="utf-8") as fh:
            if new:
                fh.write("time,time_src,gps_utc,unit,lat,lon,alt,sats\n")
            fh.write(f"{iso},{src},{rep.utc},{rep.unit},{rep.lat:.6f},{rep.lon:.6f},{rep.alt},{rep.sats}\n")
    except OSError:
        pass

def _aliases():
    try:
        return json.loads(ALIASES_PATH.read_text())
    except Exception:
        return {}

def _admin_token():
    try:
        t = Path(__file__).with_name("admin_token.txt").read_text().strip()
        return t or ADMIN_TOKEN_DEFAULT
    except OSError:
        return ADMIN_TOKEN_DEFAULT

def _write_aliases(data):
    """Validate {id: name} and write aliases.json atomically. Returns the count written."""
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object of id -> name")
    clean = {}
    for k, v in list(data.items())[:2000]:
        key = str(k).strip()
        if key:
            clean[key] = str(v).strip()[:64]
    tmp = ALIASES_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(clean, indent=2))
    tmp.replace(ALIASES_PATH)
    return len(clean)

def _age(sec):
    s = int(sec)
    if s < 60:   return "now"
    if s < 3600: return f"{s // 60} min"
    return f"{s // 3600} h {(s % 3600) // 60:02d} min"

def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _alarm_state(now):
    """Return (down, why). Only the bridge can tell 'radio unplugged' from 'nobody talking'."""
    if _bridge_connected:
        if _link_state == "down":
            return True, "radio link down"
        if _link_seen and (now - _link_seen) > ALARM_AFTER_S:
            return True, "no status from bridge"
        return False, ""
    if _ever_connected:
        return True, "feed lost (bridge unreachable)"
    return False, ""                            # cold start, never connected - behave like before

def build_kml():
    al = _aliases(); now = time.monotonic()
    down, why = _alarm_state(now)
    with _lock:
        items = list(_units.items())
    pfx = "⚠ " if down else ""
    marks = []; lats = []; lons = []
    for uid, u in items:
        age = now - u["seen"]
        if EXPIRE_S and age > EXPIRE_S:
            continue
        name = al.get(uid, uid)
        stale = "  (stale)" if age > STALE_S else ""
        label = f"{pfx}{_esc(name)} · {_age(age)}{stale}"
        marks.append(
            f'<Placemark><name>{label}</name>'
            f'<Point><coordinates>{u["lon"]:.6f},{u["lat"]:.6f},0</coordinates></Point></Placemark>')
        lats.append(u["lat"]); lons.append(u["lon"])
    if not down:
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Live units</name>'
                + "".join(marks) + '</Document></kml>').encode("utf-8")
    # --- alarm on: a document-level red style drives the banner AND (by ArcGIS Earth's
    #     own behaviour) tints the unit pins red. AE keeps the pins red until the layer is
    #     reloaded - kept ON PURPOSE as a "lingering alarm": a recovered map that is still
    #     red tells the operator the link flickered. Reload the layer to clear it. ---
    style = ('<Style id="alarm"><LabelStyle><color>ff0000ff</color><scale>1.4</scale></LabelStyle>'
             '<IconStyle><color>ff0000ff</color><scale>1.3</scale></IconStyle></Style>')
    anchor = (sum(lats) / len(lats), sum(lons) / len(lons)) if lats else ALARM_ANCHOR
    banner = ""
    if anchor:
        banner = (f'<Placemark><name>⚠ RADIO LINK DOWN — {why}</name><styleUrl>#alarm</styleUrl>'
                  f'<Point><coordinates>{anchor[1]:.6f},{anchor[0]:.6f},0</coordinates></Point></Placemark>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>⚠ RADIO LINK DOWN</name>'
            + style + banner + "".join(marks) + '</Document></kml>').encode("utf-8")

def _units_payload():
    """Same live state as build_kml(), as plain JSON for the in-browser map."""
    al = _aliases(); now = time.monotonic()
    down, why = _alarm_state(now)
    with _lock:
        items = list(_units.items())
    out = []
    for uid, u in items:
        age = now - u["seen"]
        if EXPIRE_S and age > EXPIRE_S:
            continue
        out.append({"id": uid, "name": al.get(uid, uid),
                    "lat": round(u["lat"], 6), "lon": round(u["lon"], 6),
                    "age_s": int(age), "age": _age(age), "stale": age > STALE_S,
                    "sats": u.get("sats", "")})
    out.sort(key=lambda d: d["name"].lower())
    return {"server_time": time.strftime("%H:%M:%S"),
            "alarm": {"down": down, "why": why},
            "count": len(out), "units": out}

# A self-contained live map for any phone/tablet browser. No internet, no app, no CDN:
# it polls /units.json every few seconds and plots the units on a scaled grid.


# ---------- HTTPS: enabled only when certs are present (phone GPS / camera / mic) ----------
def _ssl_ctx():
    """A TLS context if certs/server.crt + certs/server.key exist, else None (https stays off)."""
    crt = CERT_DIR / "server.crt"; key = CERT_DIR / "server.key"
    if not (crt.exists() and key.exists()):
        return None
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(crt), str(key))
        return ctx
    except (OSError, ssl.SSLError) as e:
        print(f"[units] cert load failed, https off: {e}", flush=True)
        return None

# "Share my position" - served at /share over https. Reads the phone's own GPS and POSTs it.
SHARE_HTML = """<!doctype html><html lang=en><head>
<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Share my position · The Lookout</title><style>
:root{--bg:#0d1117;--panel:#131a22;--pan2:#172230;--line:#223042;--fg:#dbe6f0;--mut:#8aa0b4;--grn:#2ec16b;--grn2:#49d17a;--red:#ff6a6a;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 -apple-system,Segoe UI,Roboto,Arial,sans-serif}
.w{max-width:560px;margin:0 auto;padding:22px max(16px,env(safe-area-inset-left)) 60px}
.b{display:flex;align-items:center;gap:9px;font-weight:700}.dot{width:11px;height:11px;border-radius:50%;background:var(--grn);box-shadow:0 0 10px var(--grn)}
h1{font-size:21px;margin:14px 0 4px}.s{color:var(--mut);font-size:14px;margin:0 0 18px}
.c{display:flex;align-items:center;gap:9px;background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:12px 14px;margin-bottom:16px;font-size:14px}
.c .t{margin-left:auto;font-weight:700;font-size:12px;padding:2px 10px;border-radius:999px}.ok{color:var(--grn2);border:1px solid #2ec16b55}.bad{color:var(--red);border:1px solid #ff6a6a55}
.btn{width:100%;background:var(--grn);color:#06130b;font-weight:800;border:0;border-radius:12px;padding:15px;font-size:17px;cursor:pointer}.btn:disabled{background:var(--pan2);color:var(--mut)}
.st{margin:14px 0;min-height:22px;font-size:14px;color:var(--mut)}.st b{color:var(--grn2)}
.u{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:6px 0;margin-top:10px}.r{display:flex;gap:10px;padding:9px 14px;border-bottom:1px solid var(--line);font-size:14px}.r:last-child{border-bottom:0}.r b{color:var(--fg)}.r span{color:var(--mut);margin-left:auto}
.h{color:var(--mut);font-size:12.5px;margin-top:16px;line-height:1.6}code{background:#000;border:1px solid var(--line);border-radius:4px;padding:0 5px;font-size:12.5px}
</style></head><body><div class=w>
<div class=b><span class=dot></span>THE LOOKOUT</div><h1>Share my position</h1>
<p class=s>Put this phone on the map as a unit — no app, just the browser.</p>
<div class=c id=c><span id=ct>checking…</span><span class=t id=cg>—</span></div>
<button class=btn id=go>📍 Share my position</button><div class=st id=st></div>
<div class=u id=u hidden></div><p class=h id=hint></p></div><script>
var sec=window.isSecureContext,geo=('geolocation'in navigator);
var ct=document.getElementById('ct'),cg=document.getElementById('cg'),go=document.getElementById('go'),st=document.getElementById('st'),hint=document.getElementById('hint');
var ID='phone-'+Math.random().toString(36).slice(2,6);
var name=prompt?null:null;
if(sec){ct.textContent='Secure connection — GPS is available.';cg.textContent='HTTPS · secure';cg.className='t ok';}
else{ct.textContent='Plain http — the browser blocks GPS here.';cg.textContent='HTTP · blocked';cg.className='t bad';go.disabled=true;hint.innerHTML='Open this over <code>https://</code> (install the fleet certificate once) and the button works.';}
go.onclick=function(){if(!geo){st.textContent='no geolocation in this browser';return;}st.textContent='getting a fix…';
navigator.geolocation.getCurrentPosition(function(p){var body=JSON.stringify({id:ID,lat:p.coords.latitude,lon:p.coords.longitude,acc:Math.round(p.coords.accuracy)});
fetch('/report',{method:'POST',headers:{'Content-Type':'application/json'},body:body}).then(function(r){return r.json();}).then(function(j){st.innerHTML=j.ok?('<b>On the map.</b> '+p.coords.latitude.toFixed(5)+', '+p.coords.longitude.toFixed(5)+' (±'+Math.round(p.coords.accuracy)+' m)'):'box refused the fix';poll();}).catch(function(){st.textContent='could not reach the box';});},
function(e){st.textContent='GPS error: '+e.message;},{enableHighAccuracy:true,timeout:8000});};
function poll(){fetch('/units.json').then(function(r){return r.json();}).then(function(d){var u=document.getElementById('u');var list=d.units||[];if(!list.length){u.hidden=true;return;}u.hidden=false;u.innerHTML='<div class=r style="color:var(--mut);font-size:12px;border:0">ON THE BOX</div>'+list.map(function(x){return '<div class=r><b>'+x.name+'</b><span>'+x.lat+', '+x.lon+' · '+x.age+'</span></div>';}).join('');}).catch(function(){});}
poll();setInterval(poll,2000);
</script></body></html>"""

# ---------- HTTP server ----------
class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")
        if path == "/admin/aliases":
            return self._admin(read=True)
        if path == "/ca":
            return self._serve_ca()          # the fleet CA cert, for devices to install
        if path in ("/share", "/me"):
            return self._serve_share()        # "share my position" page (needs https for GPS)
        if path in ("/open.kml", "/open", "/live", "/live.kml"):
            return self._serve_opener()   # one URL any device opens to get the LIVE, refreshing map
        if path == "/fetchlog":
            rep = _fetchlog_report()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(rep)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(rep)
            return
        if path in ("", "/map", "/index.html"):
            return _serve_asset(self, "map.html")
        if path in ("/leaflet.js", "/leaflet.css"):
            return _serve_asset(self, path.lstrip("/"))
        if path == "/maps.json":
            return self._json(200, {"maps": _maps_list()})
        if path.startswith("/m/"):
            slug, _, tail = path[3:].partition("/")
            info = _maps().get(slug) or _maps(force=True).get(slug)   # re-scan once for a just-added map
            if not info:
                self.send_error(404); return
            if tail in ("", "map", "index.html"):
                return _serve_asset(self, "map.html")
            if tail == "meta.json":
                return self._json(200, meta_for(info["path"]))
            if tail.startswith("tiles/"):
                try:
                    z, x, y = tail[len("tiles/"):].split("/")[:3]
                    z, x, y = int(z), int(x), int(y.split(".")[0])
                except ValueError:
                    self.send_error(400); return
                return self._tile(tile_for(info["path"], z, x, y))
            self.send_error(404); return
        # (no root "/tiles" or "/meta.json": there is no default map - every map serves at /m/<slug>/)
        if path == "/units.json":
            body = json.dumps(_units_payload()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return
        _note_fetch(self.client_address[0])   # this pull is a device asking for the live units (units.kml)
        body = build_kml()
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.google-earth.kml+xml")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _tile(self, data):
        if data is None:
            self.send_response(204); self.end_headers(); return
        ctype = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"   # .tpkx is MIXED
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers(); self.wfile.write(data)

    def _serve_opener(self):
        # A NetworkLink opener that points back at THIS box (whatever address the device used
        # to reach it, via the Host header), so a phone just opens http://<box>:8080/open.kml
        # in ArcGIS Earth and the units refresh on their own - no file to sideload, no IP to edit.
        host = self.headers.get("Host") or ("%s:%d" % (SERVE_HOST, SERVE_PORT))
        kml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>The Lookout - Live Units</name>'
               '<NetworkLink><name>Live units</name><Link>'
               '<href>http://%s/units.kml</href>'
               '<refreshMode>onInterval</refreshMode><refreshInterval>3</refreshInterval>'
               '</Link></NetworkLink></Document></kml>' % host).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.google-earth.kml+xml")
        self.send_header("Content-Disposition", 'attachment; filename="Live_Units.kml"')
        self.send_header("Content-Length", str(len(kml)))
        self.end_headers()
        self.wfile.write(kml)

    def do_POST(self):
        p = urlparse(self.path).path.rstrip("/")
        if p == "/admin/aliases":
            return self._admin(read=False)
        if p == "/report":
            return self._report()            # a phone posting its own GPS fix
        self.send_error(404)

    # ---- phone-GPS feature (#28): serve the CA, the share page, and receive fixes ----
    def _serve_ca(self):
        try:
            data = (CERT_DIR / "lookout-ca.crt").read_bytes()
        except OSError:
            self.send_error(404); return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-x509-ca-cert")
        self.send_header("Content-Disposition", 'attachment; filename="lookout-fleet-ca.crt"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def _serve_share(self):
        body = SHARE_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)

    def _report(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0 or n > 4096:
                return self._json(400, {"ok": False, "error": "bad length"})
            d = json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, OSError) as e:
            return self._json(400, {"ok": False, "error": str(e)})
        lat = d.get("lat"); lon = d.get("lon")
        if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))
                and _valid_coord(float(lat), float(lon))):
            return self._json(400, {"ok": False, "error": "bad coords"})
        uid = (str(d.get("id") or "phone")).strip()[:24] or "phone"
        _put_phone(uid, float(lat), float(lon), d.get("acc"))
        return self._json(200, {"ok": True, "id": uid})

    # ---- Alias Manager endpoint: GET returns the names, POST replaces them ----
    def _admin(self, read):
        q = parse_qs(urlparse(self.path).query)
        tok = (q.get("token", [""])[0]) or self.headers.get("X-Token", "")
        if tok != _admin_token():
            return self._json(403, {"ok": False, "error": "bad token"})
        if read:
            return self._json(200, {"ok": True, "aliases": _aliases()})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0 or n > 262144:
                return self._json(400, {"ok": False, "error": "bad length"})
            count = _write_aliases(json.loads(self.rfile.read(n).decode("utf-8")))
            return self._json(200, {"ok": True, "count": count})
        except (ValueError, OSError) as e:
            return self._json(400, {"ok": False, "error": str(e)})

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

# ---------- read the bridge's NMEA feed ----------
def read_bridge():
    global _bridge_connected, _ever_connected
    while True:
        s = None
        try:
            print(f"[units] connecting to bridge {BRIDGE_HOST}:{BRIDGE_PORT} ...", flush=True)
            s = socket.create_connection((BRIDGE_HOST, BRIDGE_PORT), timeout=6)
            s.settimeout(1.0)
            sp = StreamParser()
            _bridge_connected = True; _ever_connected = True
            print("[units] reading NMEA from the bridge", flush=True)
            while True:
                try:
                    data = s.recv(65535)
                except socket.timeout:
                    continue
                if not data:
                    print("[units] bridge closed - reconnecting", flush=True)
                    break
                for rep in sp.feed(data):
                    _put(rep)
                    _log_fix(rep)
                    print(f"[units] {rep.unit}  {rep.lat:.5f},{rep.lon:.5f}", flush=True)
        except OSError as e:
            print(f"[units] bridge connection problem: {e} - retrying", flush=True)
        finally:
            _bridge_connected = False
            if s is not None:
                try: s.close()
                except OSError: pass
        time.sleep(RECONNECT_S)

# ---------- demo feed (no radio): 3 units walking small circles over Bryceville ----------
def demo_feed():
    print("[units] DEMO mode - 3 synthetic units, no radio needed", flush=True)
    base = [("7-01", 30.3961, -81.9392, 0.020, 0.0),
            ("7-02", 30.3850, -81.9100, 0.013, 2.1),
            ("7-03", 30.4050, -81.9600, 0.027, 4.1)]
    t = 0
    while True:
        for uid, clat, clon, r, ph in base:
            a = ph + t * 0.14
            lat = clat + r * math.sin(a)
            lon = clon + r * math.cos(a) / math.cos(math.radians(clat))
            _put(Report(uid, lat, lon, "0", "9", "000000"))
        t += 1
        time.sleep(2)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="The Lookout - live units KML server")
    ap.add_argument("--demo", action="store_true", help="serve moving synthetic units, no radio")
    args = ap.parse_args()
    print(f"=== The Lookout - live units KML server  v{VERSION} ===", flush=True)
    print(f"serving units.kml on http://{SERVE_HOST}:{SERVE_PORT}/units.kml  (Ctrl+C to stop)", flush=True)
    print(f"   diagnostic: who pulls the map + how often -> http://{SERVE_HOST}:{SERVE_PORT}/fetchlog", flush=True)
    threading.Thread(target=(demo_feed if args.demo else read_bridge), daemon=True).start()
    http_srv = ThreadingHTTPServer((SERVE_HOST, SERVE_PORT), _H)
    ctx = _ssl_ctx()
    if ctx is not None:
        try:
            https_srv = ThreadingHTTPServer((SERVE_HOST, HTTPS_PORT), _H)
            https_srv.socket = ctx.wrap_socket(https_srv.socket, server_side=True)
            threading.Thread(target=https_srv.serve_forever, daemon=True).start()
            print(f"   secure (phone GPS/camera/mic): https://{SERVE_HOST}:{HTTPS_PORT}/share  (CA at /ca)", flush=True)
        except OSError as e:
            print(f"[units] https disabled: {e}", flush=True)
    else:
        print("   (no certs in ./certs - https off; run make_certs.sh to enable phone GPS)", flush=True)
    try:
        http_srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[units] stopped.", flush=True)
        sys.exit(0)
