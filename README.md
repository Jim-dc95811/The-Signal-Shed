# The Signal Shed

**A lab for [The Lookout](https://github.com/Jim-dc95811/The-Lookout).** The Lookout proved
an offline box can serve a live map to any browser with nothing installed. The Signal Shed
asks the bigger question: **what *else* can a plain browser carry to and from that box — audio,
video, documents, live data, a phone's own camera or GPS — with nothing installed on the
viewer?**

Each answer is built self-contained, offline, and tested before it's trusted. When a path is
hardened, it **graduates into The Lookout**. This repo keeps the experiments so the shipped
appliance stays pristine.

🤖 **Using AI assistance?** Have the agent read [`CLAUDE.md`](CLAUDE.md) first.

---

## The systems diary

The master list of every box↔browser transport — **38 and counting** — grouped by direction
(the *range*: box→viewer, the *mirror*: viewer→box), tiered (works today / needs a fleet cert /
needs an app), and status-marked. This is the map of the whole effort:

➡️ **[docs/SYSTEMS_DIARY.md](docs/SYSTEMS_DIARY.md)**

The plan: catalog every path, then harden them **one at a time**.

---

## The demos (open in any browser — offline, nothing installed)

| Demo | What it shows |
|---|---|
| [`demos/Content_Lab.html`](demos/Content_Lab.html) | Nine data paths in one page — audio, video, slides, gallery, pan/zoom, live data tile, photo-upload "mirror", document, download |
| [`demos/Audio_Scope.html`](demos/Audio_Scope.html) | **See what you hear** — radio audio as a live waveform, spectrum and transmission-level meter |
| [`demos/Service_Manual/Service_Manual.html`](demos/Service_Manual/Service_Manual.html) | A PDF-killer — a manual the box *serves*: search-as-you-type, a vector system diagram, a zoomable wiring plate |

Download the file (or the `Service_Manual` folder) and double-click it — no server needed to try.

---

## How it relates to the family

The Signal Shed is part of the **ArcGIS Earth Unlocked** project family. The Lookout is the
appliance; the Shed is where its next capabilities are proven. Free & open-source (MIT).
