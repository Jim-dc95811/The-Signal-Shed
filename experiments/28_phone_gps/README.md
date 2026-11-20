# #28 — Phone GPS → box (and the fleet cert)

**Status: mechanism PROVEN in the sandbox (2026-11-19).** A browser over HTTPS reads the
phone's own GPS and POSTs it to the box, which folds it in as a unit — **no app.** The only
real-world step left is installing the fleet CA on each device.

## What this proves

A phone reporting its own position turns it into a tracked unit with **no radio** — the
complement to the P25 GPS work (GPS *from radios* → GPS *from phones*). The blocker is the
browser **secure-context gate**: `navigator.geolocation` (and camera/mic) only work on HTTPS
with a trusted cert — plain `http://192.168.8.1` doesn't qualify (only `localhost` is exempt).

Self-test result (`t.js`, headless Chromium with a mocked fix at 30.39382, -81.93785):

| Origin | `isSecureContext` | Share button | Result |
|---|---|---|---|
| `http://<box>:8080` | **false** | **disabled** | GPS blocked — the gate |
| `https://<box>:8443` | **true** | enabled | fix POSTed → box lists `phone-xxxx` as a unit |

See `proof.png`. (The test bypasses cert *trust* with `ignoreHTTPSErrors` to prove the
*mechanism*; on real devices that trust comes from installing the CA — the step below.)

## The cert decision

- **Private "Lookout Fleet CA"** *(chosen)* — the box is its own CA; install that one cert on
  each phone. **Works forever, fully offline, no domain, no renewal.** Cost: one install per
  device. Right for an appliance that may never see the internet again.
- Real domain + Let's Encrypt — no per-device install, but needs a domain and a 90-day online
  renewal. Rejected: the box lives offline.

## Run the prototype

```
./make_certs.sh 192.168.8.1      # makes the CA + server cert (keys stay local, gitignored)
python3 box.py                    # http:8080 (insecure) + https:8443 (secure)
# open https://<box>:8443/  → Share my position → it lands on the box; /units.json shows it
# the box serves the CA for devices to install at:  /ca
```

## Roadmap to productionize (needs the box)

1. **Box serves HTTPS.** Add `ssl` to `units_kml.py` (a second socket on **:8443**; keep
   **:8080** http so locked-down PCs can still view the map with no cert). Pattern = `box.py`.
2. **Lookout Manager generates the CA** (the `make_certs.sh` steps) during setup, installs
   `server.crt`/`server.key` on the box, and serves `lookout-ca.crt` at `/ca`.
3. **Per-device install** (one-time, printable guide + a QR to `/ca`):
   - **iOS:** open `/ca` → install profile → Settings ▸ General ▸ About ▸ Certificate Trust
     Settings ▸ enable full trust.
   - **Android:** Settings ▸ Security ▸ Install a certificate ▸ CA certificate → pick the file.
   - **Windows/desktop:** import into Trusted Root.
   - Fleet-managed devices: push the CA by MDM in one shot.
4. **Receiver graduates into the feed.** `POST /report` → fold phone fixes into the same unit
   list `bk_bridge`/`units_kml` already broadcast (distinct marker/colour for phone units).
5. **Then camera + mic come free** on the same secure origin (#29/#30) — same cert, no new work.

## The patch (built + tested 2026-11-19)

`units_kml_https.py` is **the real `units_kml.py` (v1.12) patched to v1.13** — tested here end
to end over https. `units_kml_v1.13.patch` is the unified diff for review/apply. What it adds:

- **Optional HTTPS on :8443**, enabled *only* when `certs/server.crt` + `certs/server.key`
  exist. **No certs → byte-for-byte identical to v1.12**, and `:8080` http is untouched, so it
  cannot disturb a live box. (The map viewers keep using plain-http :8080 with no cert.)
- `GET /ca` — serves the fleet CA for devices to install.
- `GET /share` — the "share my position" page (inline; no new asset file to ship).
- `POST /report` — validates a phone fix and folds it into the **same `_units` list**, flagged
  `phone=True`. It then shows in **both** the browser map (`/units.json`) **and** `units.kml`
  (so ArcGIS Earth sees phone units too).

**Verified** (`t2.js`, headless): `/ca` serves `CN=Lookout Fleet CA`; `http://box:8080/share`
→ `isSecureContext=false`, button disabled; `https://box:8443/share` → secure, a mocked fix
POSTs and appears as a unit in both feeds. See `proof_units.png`.

### Deploy on the box (bench)
```
# on the setup computer or the box: make the certs (keys stay on the box)
./make_certs.sh 192.168.8.1
scp certs/server.crt certs/server.key certs/lookout-ca.crt root@192.168.8.1:/root/certs/
# replace units_kml.py with the v1.13 build, then restart the service
scp units_kml_https.py root@192.168.8.1:/root/units_kml.py
ssh root@192.168.8.1 '/etc/init.d/units-kml restart'
# phone: install the CA from  https://192.168.8.1:8443/ca  (or http://192.168.8.1:8080/ca),
# then open  https://192.168.8.1:8443/share  → Share → it lands on the map
```

### Lookout Manager integration (next — when #28 is hardened for real)
Add to `SETUP_STEPS` (the box has `openssl-util`; the CA key never leaves the box):
```
opkg install openssl-util
mkdir -p /root/certs
# generate the Lookout Fleet CA + server cert on the box (make_certs.sh steps) if absent
[ -f /root/certs/server.crt ] || sh /root/make_certs.sh 192.168.8.1
```
…and bump the units_kml.py fetch target to the v1.13 build. The printable per-device CA-install
guide + a QR to `/ca` (via Lookout QR Maker) is the last field-facing piece.

This experiment lives in the Signal Shed; when hardened it graduates into The Lookout.
