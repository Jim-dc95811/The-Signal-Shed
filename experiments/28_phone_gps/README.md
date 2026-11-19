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

This experiment lives in the Signal Shed; when hardened it graduates into The Lookout.
