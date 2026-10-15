# tak-feeder-lightnings-fmi

> [!WARNING]
> **Work in progress. Not recommended for use.** This fork is being improved
> and has not been tested against a live TAK server yet. Things may change or
> break without notice.

Sends the lightning strikes observed by the Finnish Meteorological Institute
(FMI) to a TAK server as CoT.

Fork of [sgofferj/tak-feeder-lightnings-fmi](https://github.com/sgofferj/tak-feeder-lightnings-fmi)
by Stefan Gofferje, with the improvements of his
[trakbridge-plugin-lightnings-fmi](https://github.com/sgofferj/trakbridge-plugin-lightnings-fmi).

## What it sends

Every `UPDATE_INTERVAL` seconds the strikes of the last `HISTORY` seconds
(default 30 minutes) are sent, oldest first so the newest are drawn on top.

| Field | Value |
|---|---|
| UID | `lightning-<time>-<lon>-<lat>` (unchanged from upstream) |
| Callsign | `FMI Lightning` |
| Type | `a-o-G` with the thunderstorm icon |
| Colour by age | white < 5 min, yellow < 15 min, orange < 30 min, red < 45 min, dark red |
| `ce` | location accuracy (error ellipse) from FMI |
| Remarks | strike time, peak current, cloud-to-ground or cloud flash, source, `#weather #lightning` |

Ages are counted from FMI's response time, so a wrong local clock does not
change the colours.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `COT_URL` | `udp://239.2.3.1:6969` | TAK server, e.g. `ssl://takserver:8089` |
| `PYTAK_TLS_CLIENT_CERT` / `PYTAK_TLS_CLIENT_KEY` | | Client certificate and unencrypted key (PEM) |
| `PYTAK_TLS_DONT_VERIFY` | `0` | `1` = do not verify the server certificate |
| `HISTORY` | `1800` | Seconds of history (min 120) |
| `UPDATE_INTERVAL` | `30` | Seconds between rounds |
| `FMI_BBOX` | (FMI default area) | `west,south,east,north` |
| `TIMEZONE` | `Europe/Helsinki` | Time zone of the strike time |
| `HEALTH_MAX_ERRORS` | `3` | Failed rounds in a row before the container is unhealthy |
| `DEBUG` | `0` | Debug logging |

## Running

Image for amd64 and arm64: `ghcr.io/street3r/tak-feeder-lightnings-fmi:latest`.

```yaml
services:
  feeder-lightning:
    image: ghcr.io/street3r/tak-feeder-lightnings-fmi:latest
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./certs:/data:ro
```

The container runs as uid 10001; the key must be readable by it.

## Data

Finnish Meteorological Institute open data,
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The source line is
in every marker's remarks.

## Credits and changes

Original work © Stefan Gofferje:
[tak-feeder-lightnings-fmi](https://github.com/sgofferj/tak-feeder-lightnings-fmi)
and [trakbridge-plugin-lightnings-fmi](https://github.com/sgofferj/trakbridge-plugin-lightnings-fmi),
used with his permission.

Changes in this fork (Street3r):

- 2026-10-13
  - **Fixed:** an FMI outage stopped the feeder; it now logs and retries.
  - `fmiopendata` replaced with the WFS parsing of the TrakBridge plugin;
    requests no longer block.
  - Ages and colours from FMI's response time; strikes sent oldest first.
  - Default history 30 minutes (was 5), so the age colours are visible.
  - Remarks: local strike time, peak current, flash type, `#weather #lightning`.
    Callsign `FMI Lightning`. Optional area filter.
  - Health check; unprivileged container; tests and CI.
- 2026-10-15
  - Every event of a send round reaches TAK. pytak's send queue holds 100
    events and dropped the oldest when full, so rounds of more than 100
    lost the rest.

## License

GNU General Public License v3.0 or later, see [LICENSE](LICENSE).
