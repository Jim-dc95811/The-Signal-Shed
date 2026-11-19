# CLAUDE.md — The Signal Shed

**Written by Claude, for Claude.** Resuming or picking up the Shed? Read this first. Keep it
decodable by a future Claude (possibly a different model) reading cold; shorthand is fine if
self-explaining.

> **Public repo. Keep this file public-safe** — strip any employer/agency name (Jim's own
> name/handle are fine). **Precedence:** live code > the family `CLAUDE.md`
> (ArcGIS-Earth-Unlocked) > The Lookout's `CLAUDE.md` > this file. Disagreement → trust live
> code, then the family file, then The Lookout, then this.

---

## What this is (one breath)

The Signal Shed is **The Lookout's lab.** The Lookout (a GL-MT6000 / Raspberry Pi) serves a
live offline map to any browser with nothing installed. The Shed explores **every other
transport** a plain browser can carry to and from that box — audio, video, documents, live
data streams, a phone's own camera/GPS/mic back to the box. Build it here, prove it, and when
it's hardened, **graduate it into The Lookout** so the shipped appliance stays pristine.

## The one doc that matters first

**[`docs/SYSTEMS_DIARY.md`](docs/SYSTEMS_DIARY.md)** — the living master list of all ~38
transport systems (grouped by direction, tiered, status-marked), the proven combos, the
landmines, the tier model, and the build/test method. **Read it before building anything.**
Update it in real time as paths are proven — that's the whole point: Jim gets limited time
per week, so findings are banked the moment they land and never re-derived.

## The thesis & the tier model (short version — full in the diary)

The box is a **content & data platform**, not just a map server. Jim's north star:
- **The range** — anything a phone can *receive* over Wi-Fi, the box can be the source of.
- **The mirror** — anything a phone can *send* over Wi-Fi, the box can take back.

Every path is one of three honest tiers, and you **always say which**:
- **browser · today** — plain http, nothing installed (files, audio, video, slides, tiles,
  live canvas/data, forms, photo *upload*).
- **+1 cert on the fleet** — unlocks live **camera / mic / GPS** and PWA install (they need a
  secure context). One locally-trusted cert pushed to the devices; still just a browser.
- **+ an app** — raw sockets, Bluetooth, background. Android sideloads from the box; **iOS
  can't** (App Store / MDM only).

## Priorities (from the diary)

1. **Phone-GPS → box (#28):** crew phones as tracked units with no radio. Top prize. Gated by
   the cert.
2. **The fleet-cert research:** one decision unlocks five 🔒 systems (phone GPS, camera, mic,
   PWA, WebRTC). First real research task.
3. **Plain-http wins, no cert:** MJPEG box-camera (#10), SSE sensor ticks (#12), the shared
   board (#34), the "drop a doc on the box" builder.

## Landmines (each cost a cycle once — in the diary, repeated here)

- A lone HTML is self-contained only if it **embeds** everything (data URIs). The moment it
  *links* to a sibling file, it must ship as a **folder** or the link 404s from Downloads.
- **Search must skip SVG** — a `<mark>`-wrapping highlighter silently deletes matched text
  inside an inline `<svg>`. Exclude `p.closest('svg')`.
- **Secure-context gate** — camera/mic/GPS/service-workers need https; don't promise them on
  the plain-http box without the cert.
- Media that plays everywhere: **MP3/AAC** audio, **H.264** MP4 video (avoid OGG/Opus on iOS).

## Build & test method (match this bar)

1. Self-contained (data URIs; folder only when it links out).
2. Render-verify with Playwright at desktop **and** ~390px phone (no horizontal scroll).
3. **Function-verify, not just render** — drive the real behavior headless and assert the
   mechanism (e.g. Audio Scope: played the sweep, asserted the spectrum peak *climbs*).
   Chromium `--autoplay-policy=no-user-gesture-required` for audio; expose `window.__hooks()`.
4. Deliver to Jim's Downloads via the bridge from a **fresh** output path, **distinct filename**.

## Working with Jim (inherited from the family)

- Limited time per week — make his minutes count; do the long builds/tests myself, leave the
  field tests and direction to him.
- Communicates in vision/gist; meet him at the concept level, work out the mechanism myself.
- Unvarnished honesty; no cautions about obvious truths; warn only before publishing something
  over a line.
- Deliver files straight to his Downloads (bridge), distinct name each time, tell him after.
- Zero employer references in anything public.

## Resume procedure

1. Clone `The-Signal-Shed`; attach with push access (`add_repo`, `access: push`) before pushing.
2. Read this file → **`docs/SYSTEMS_DIARY.md`** → the demo(s) your task touches.
3. Pick a path from the diary's priority list, research + harden it, log the finding, deliver.
4. When a path is production-ready, graduate it into The Lookout and note it in both repos.

*Keep this file lean; the depth lives in the diary.*
