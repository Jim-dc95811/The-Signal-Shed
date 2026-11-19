# The Signal Shed — Systems Diary

**Written by Claude, for Claude — a living findings log, updated in real time as we build.**
Jim gets limited time per week with me, so this doc is how that time *compounds*:
every browser data-path experiment gets recorded here the moment it's proven, so a
future session (even a different model) resumes cold without re-deriving anything.
Keep it current and lean; the dated log at the bottom holds the running history.

> Public-safe: strip any employer/agency name (Jim's own name/handle are fine).
> Precedence: live code > the family `CLAUDE.md` (ArcGIS-Earth-Unlocked) > The Lookout's
> `CLAUDE.md` > the Signal Shed's `CLAUDE.md` > this diary. This diary owns the
> **transport-systems** thread. The Signal Shed is The Lookout's **lab** — paths are
> proven here, then the hardened ones **graduate into The Lookout** so the OG stays pristine.

---

## The thesis (why this exists)

The Lookout started as a map server. The real discovery is bigger: **the box is a
content & data distribution platform.** It sits on its own Wi-Fi with no internet, and
any device with a browser can reach it. So the question stops being "can it serve a
map" and becomes **"what can a plain browser eat and emit — and the box be the source
and sink of — with nothing installed on the viewer?"**

Jim's framing, kept verbatim because it's the north star:
- **The range** — anything a phone can *receive* over Wi-Fi, the box can be the source of.
- **The mirror** — anything a phone can *send* over Wi-Fi, the box can take back.
- And the quiet punchline: a button on a screen that *does something* — where the thing
  it talks to is **in the truck**, not a server in San Jose.

Everything here is a concrete answer to that question, each one built self-contained,
offline, and **tested by me before Jim sees it.**

---

## The tier model (the finding that governs everything)

Every data path falls into one of three honest tiers. Say which, always — it's the
difference between a promise that holds in the field and one that embarrasses you.

| Tier | What it unlocks | Cost |
|---|---|---|
| **browser · today** | files in/out, audio, video, slides, zoomable imagery, live canvas/data, forms, photo *upload* (`<input type=file capture>`) | plain http, nothing installed |
| **+1 cert on the fleet** | live **camera / mic / GPS** (`getUserMedia`, Geolocation), service workers / PWA install | one locally-trusted cert pushed to the devices — still just a browser |
| **+ an app** | raw sockets, Bluetooth, background operation | Android sideloads an APK from the box; **iOS blocks local sideload** (App Store / MDM only) |

Why the cert line exists: browsers gate camera/mic/GPS and service workers behind a
**secure context** (https). A plain-http offline box can't give them that without a
cert trusted on each device. File-upload camera-capture is the exception — it works on
plain http today — which is why the "mirror" works now and *live* camera doesn't.

---

## Proven paths

All three delivered to Jim's Downloads (not the repo — they're explorations). Each was
render-verified **and** function-verified headless before hand-off.

| Path | File | What it proves | Honest note |
|---|---|---|---|
| **Content Lab** | `Lookout_Content_Lab.html` | 9 data paths in one offline page: audio, video, HTML slide deck, photo gallery+lightbox, pan/zoom image, live-ticking data tile w/ sparkline, form+photo-upload "mirror", rich-doc, file download | One page, ~464 KB with all media embedded as data URIs. The tier legend is baked in so it answers "can it do X" honestly. |
| **Service Manual** | `Lookout Service Manual/` (folder) | A PDF-killer: the Developer's Guide reflowed + **search-as-you-type** (highlight, prev/next, count), a **vector** system diagram (sharp at any zoom, theme-aware), a **raster** wiring plate in a pan/zoom viewer, scrollspy TOC, phone drawer | **268 KB vs the 232 KB+ PDF — but searchable, reflowing, zoomable.** Ships as a *folder* so its relative links to companion PDFs resolve (see landmine below). |
| **Audio Scope** | `Lookout_Audio_Scope.html` | **audio → live visual.** Web Audio `AnalyserNode` drives a waveform, a spectrum (peak-Hz readout), and a transmission-level meter on the box's own 3%/54% scale | Candidate **real feature**: rides under the map's 🔊 Listen button, fed by the live radio PCM (`:8081`) — a crew *sees* a transmission land with the volume down. Proven reactive, not canned (see test method). |

---

## Landmines (each cost a real cycle once — don't pay again)

- **A lone HTML is only self-contained if it *embeds* everything.** The moment it
  *links* to a sibling file (a companion PDF, an image), it must travel as a **folder**,
  or the relative link 404s when opened from Downloads. Embed assets as data URIs when
  you can; bundle a folder when you can't. (Caught live: the Service Manual's
  "hardware requirements sheet" link broke until shipped as a folder with `graphics/`.)
- **Search must skip SVG.** A text-highlight TreeWalker that wraps matches in `<mark>`
  will silently *delete* the matched text inside an inline `<svg>` — SVG ignores the
  `<mark>` element. Exclude `p.closest('svg')` from the walk. (Searching "audio" turned
  "lookout_audio.py" into "lookout_.py" in the diagram until fixed.)
- **Secure-context gate.** Camera/mic/GPS/service-workers need https. Don't promise live
  camera on the plain-http box; promise photo *upload* (works) and note the cert path.
- **Media that plays everywhere:** MP3/M4A(AAC) audio and **H.264** MP4 video play on
  iPhone + Android + desktop. Avoid OGG/Opus (trips older iOS).
- **Tiles are flat-cost.** The box seeks one 256 px tile per request off the SSD, no
  decode — map/library size doesn't scale RAM/CPU. "Infinite in puny human terms — just
  buy a bigger SSD" (Jim). The same tiling handles a monster diagram or a 2,000-page
  manual's plates.

---

## My build & test method (so a future me matches the bar)

1. Build the page self-contained (assets as data URIs; folder only when it links out).
2. **Render-verify** with Playwright at desktop *and* ~390 px phone — no horizontal
   scroll, reflows to one column.
3. **Function-verify**, not just render: drive the real behavior headless and assert the
   mechanism. (Audio Scope: played the sweep clip, sampled the live spectrum twice,
   asserted the peak bin *climbs* 17→31 and level>0 — proof it tracks the audio, not a
   fake animation.) Launch Chromium with `--autoplay-policy=no-user-gesture-required`
   for audio tests; expose `window.__hooks()` to read internal state.
4. Deliver to Jim's Downloads via the bridge from a **fresh** `/mnt/user-data/outputs/<uniq>/`
   path, **distinct filename** each time.

---

## The transport systems — master list (the systems diary)

The running catalog of **every data path the box and a browser can carry between them.**
The plan (Jim, 2026-11-19): gather them all here first, then go at them **one at a time**,
researching and hardening each protocol. This table is the backlog and the map.

**Legend** — direction: `→` box to viewer (the range) · `←` viewer to box (the mirror) · `↔` both.
status: ✅ proven · 🧪 simulated/partial · 🔬 to research · 🔒 needs cert (secure context) · 📱 needs an app.

### Box → viewer (the range)

| # | System | dir | tier | status | Lookout payoff |
|---|---|---|---|---|---|
| 1 | Static file download (any type) | → | today | ✅ | hand a phone a CSV/KML/form to keep |
| 2 | Images (jpg/png/webp) | → | today | ✅ | field photos, reference plates |
| 3 | Vector graphics (SVG) | → | today | ✅ | diagrams sharp at any zoom, theme-aware |
| 4 | Tiled slippy map (`.tpkx`/`.mbtiles`) | → | today | ✅ | the core — offline imagery, any browser |
| 5 | Deep-zoom giant image (pan/zoom + tiles) | → | today | ✅ | a schematic/diagram explored like a map |
| 6 | Audio file (mp3/AAC) | → | today | ✅ | fault tones, example transmissions |
| 7 | Audio **stream** (PCM / WebSocket `:8081`) | → | today | ✅ | live radio in the browser |
| 8 | Audio **visualized** (scope) | → | today | ✅ | *see* a transmission land, volume down |
| 9 | Video file (H.264 MP4) | → | today | ✅ | procedure walkthrough, site flyover |
| 10 | **Live video stream** (MJPEG `multipart/x-mixed-replace`) | → | today | 🔬 | a camera on the box → every screen, no plugin |
| 11 | **Live video stream** (HLS `.m3u8`) | → | today | 🔬 | smoother live camera; needs hls.js on older browsers |
| 12 | Live data (**SSE** / `text/event-stream`) | → | today | 🔬 | one-way sensor/telemetry ticks — dead simple |
| 13 | Live data (**WebSocket**) | ↔ | today | 🧪 | the general live channel (dash proven simulated) |
| 14 | Live positions (KML NetworkLink) | → | today | ✅ | units in ArcGIS Earth |
| 15 | NMEA/TCP position feed (`:10110`) | → | today | ✅ | units in any NMEA app |
| 16 | Reflowed document (HTML reader) | → | today | ✅ | searchable manual, beats a PDF |
| 17 | PDF served (native viewer) | → | today | ✅ | baseline doc view |
| 18 | Slide deck (HTML, from `.pptx`) | → | today | 🧪 | the box carries its briefing |
| 19 | 3D model (glTF via `<model-viewer>`/three.js) | → | today | 🔬 | a piece of equipment or site in 3D |
| 20 | Charts/graphs from data | → | today | 🧪 | trends from the feed (sparkline proven) |
| 21 | QR deep-link to a page/map | → | today | ✅ | point a phone, land on the right map |
| 22 | Downloadable Android app (APK) | → | +app | 🔬📱 | the box hands out its own app (iOS can't) |
| 23 | PWA / offline app install (service worker) | → | +cert | 🔒 | the page installs like an app, works after |

### Viewer → box (the mirror)

| # | System | dir | tier | status | Lookout payoff |
|---|---|---|---|---|---|
| 24 | Form submit (text) | ← | today | 🧪 | a field note to the box (needs POST sink) |
| 25 | Photo **upload** (camera-capture file) | ← | today | 🧪 | proof-of-completion, hazard photo, no app |
| 26 | File upload (any) | ← | today | 🔬 | drop a track log / doc onto the box |
| 27 | Audio/voice-memo upload (recorded file) | ← | today | 🔬 | a spoken report filed as a clip |
| 28 | **Phone GPS → box** (Geolocation API) | ← | +cert | 🔒✅ | **every crew phone becomes a tracked unit, no radio** — mechanism proven, `experiments/28_phone_gps` |
| 29 | **Live camera** (getUserMedia) | ← | +cert | 🔒 | a phone as a field camera to the box |
| 30 | **Live mic** (getUserMedia) | ← | +cert | 🔒 | push-to-talk / live audio from a phone |
| 31 | QR / barcode scan | ← | today¹ | 🔬 | scan asset tags (¹ via uploaded photo today; live needs cert) |
| 32 | Map annotation / drawing sent back | ← | today | 🔬 | mark a hazard, everyone sees it (needs sink) |
| 33 | Device compass / motion | ← | +cert | 🔒 | heading / orientation for AR-ish overlays |

### Two-way / shared / infrastructure

| # | System | dir | tier | status | Lookout payoff |
|---|---|---|---|---|---|
| 34 | **Shared board** (post + broadcast via WebSocket) | ↔ | today | 🔬 | the mirror made shared — a live field bulletin |
| 35 | Text chat / net log | ↔ | today | 🔬 | a crew net without cell service |
| 36 | Per-device storage (localStorage/IndexedDB) | ↔ | today | ✅ | remember a filter/draft on that phone |
| 37 | WebRTC phone↔phone (box as signaling) | ↔ | +cert | 🔒🔬 | direct phone-to-phone media, box brokers |
| 38 | Web Bluetooth to a sensor | ← | +app/+cert | 🔒📱 | a BLE sensor's data onto the map (limited support) |

### Priority picks (what to harden first, and why)

1. **#28 Phone GPS → box** — the biggest payoff for Jim's world: turn any crew phone into
   a tracked unit with **no radio**, complementing the P25 GPS work (his original Holy
   Grail was GPS *from radios*; this is GPS *from phones*). Blocked only by the secure-
   context cert — which is exactly Jim's "browser bridge perfection" step. Research the
   cert-on-the-fleet path and this unlocks #28/#29/#30/#23 together.
2. **#34 Shared board** — the mirror's headline demo; needs a small POST+broadcast sink
   on the box (the first *write* endpoint beyond unit-renaming).
3. **#10/#12 MJPEG + SSE** — the two cheapest live streams (a box camera, a sensor tick)
   that work on plain http **today**, no cert. Good early wins.
4. **"Drop a doc on the box" builder** — productizes the Service Manual: any folder of
   markdown/PDF → a served bundle. Pure authoring tool, no box-side risk.

**The cert question gates a whole column.** Everything 🔒 (live camera/mic/GPS, PWA,
WebRTC) waits on one decision: push a locally-trusted cert to the fleet. Research that
once and five systems light up. That's the first real research task after this catalog.

---

## Session log

- **2026-11-19 (Thu):** Started this journal at Jim's request ("document these findings
  in real time"). Built and proved three browser data-path combos in one evening:
  **Content Lab** (9 paths, one page), the **Service Manual** (reflow+search+vector/raster
  diagrams; learned the folder-bundle rule the hard way when its companion-PDF link 404'd
  from Downloads, fixed by shipping a folder), and the **Audio Scope** (audio→live
  waveform/spectrum/level; function-tested the reactivity — sweep peak bin climbed 17→31).
  Established the tier model and the SVG-search landmine. Jim: "It's the new revolution,
  build it and they will come." Direction set: the box is a content/data platform, and
  this journal tracks every path. Then gathered the full **transport-systems master list**
  (38 paths, grouped by direction, tiered and status-marked) — the "systems diary." Plan:
  catalog first, then harden one protocol at a time. Flagged **phone-GPS→box (#28)** as the
  top prize (crew phones as units, no radio) and the **fleet-cert question** as the first
  real research task (it unlocks five 🔒 systems at once). Repo decision pending: likely a
  separate "lab" repo to keep the OG Lookout pristine.
- **2026-11-19 (Thu, later):** Spun up this repo — **The Signal Shed**, The Lookout's lab —
  and moved the diary + demos here; The Lookout kept a one-line pointer (OG pristine). Then
  **went at #28 and the fleet cert, and PROVED the mechanism** (`experiments/28_phone_gps`):
  a private **Lookout Fleet CA** → box serves HTTPS → the phone's Geolocation API works →
  a mocked fix POSTed and the box listed the phone as a unit. Self-test confirmed the gate:
  `secureContext=false` + button disabled on http, `true` + working on https. **Cert decision:
  private CA** (offline-forever, no domain/renewal; Lookout Manager will generate it). Left:
  the real-device CA install + wiring HTTPS into `units_kml.py` + graduating the receiver into
  the unit feed. Same cert then unlocks phone camera/mic (#29/#30) for free.
