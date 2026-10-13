# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright Stefan Gofferje (tak-feeder-lightnings-fmi, trakbridge-plugin-lightnings-fmi)
# Copyright (C) 2026 Street3r (changes, see README)
"""FMI lightning strikes -> CoT."""

from __future__ import annotations

import logging
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from . import __version__
from .common import Health, cot_event, env, env_float, fetch, remarks_text

LOG = logging.getLogger("tak_feeder_lightnings_fmi")

WFS_URL = "https://opendata.fmi.fi/wfs"
QUERY = "fmi::observations::lightning::multipointcoverage"
NS = {
    "gml": "http://www.opengis.net/gml/3.2",
    "gmlcov": "http://www.opengis.net/gmlcov/1.0",
    "swe": "http://www.opengis.net/swe/2.0",
}
ICON = "ad78aafb-83a6-4c07-b2b9-a897a8b6a38f/Shapes/thunderstorm.png"


@dataclass
class Strike:
    """One lightning strike."""

    lat: float
    lon: float
    time: datetime
    values: dict[str, float] = field(default_factory=dict)


@dataclass
class Settings:
    """Feeder settings from the environment (see .env.example)."""

    history: float = 1800.0
    update_interval: float = 30.0
    bbox: str = ""
    timezone: str = "Europe/Helsinki"
    source_line: str = "Source: Finnish Meteorological Institute open data, CC BY 4.0"

    @classmethod
    def from_env(cls) -> "Settings":
        """Read settings."""
        d = cls()
        return cls(
            history=max(120.0, env_float("HISTORY", d.history)),
            update_interval=env_float("UPDATE_INTERVAL", d.update_interval),
            bbox=env("FMI_BBOX", ""),
            timezone=env("TIMEZONE", d.timezone),
            source_line=env("SOURCE_LINE", d.source_line),
        )


def age_color(age: float) -> str:
    """ARGB colour by strike age, as in upstream."""
    if age >= 2700:
        return "-7864320"
    if age >= 1800:
        return "-65535"
    if age >= 900:
        return "-35072"
    if age >= 300:
        return "-256"
    return "-1"


def parse(xml: bytes) -> tuple[Optional[datetime], list[Strike]]:
    """(response time, strikes oldest first) from a multipointcoverage response."""
    root = ET.fromstring(xml)
    stamp = root.get("timeStamp")
    now = (datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
           if stamp else None)
    pos_el = root.find(".//gmlcov:positions", NS)
    rows_el = root.find(".//gml:doubleOrNilReasonTupleList", NS)
    if pos_el is None or not pos_el.text:
        return now, []
    numbers = pos_el.text.split()
    fields = [f.get("name", "") for f in root.findall(".//swe:field", NS)]
    rows = ([r.split() for r in rows_el.text.strip().splitlines() if r.strip()]
            if rows_el is not None and rows_el.text else [])
    strikes = []
    for i in range(0, len(numbers) - 2, 3):
        lat, lon, epoch = (float(v) for v in numbers[i:i + 3])
        values: dict[str, float] = {}
        row = rows[i // 3] if i // 3 < len(rows) else []
        for name, raw in zip(fields, row):
            try:
                value = float(raw)
            except ValueError:
                continue
            if not math.isnan(value):
                values[name] = value
        strikes.append(Strike(lat, lon, datetime.fromtimestamp(epoch, tz=timezone.utc), values))
    strikes.sort(key=lambda s: s.time)
    return now, strikes


class LightningSource:
    """Fetches the strikes of the last HISTORY seconds every round."""

    def __init__(self, settings: Settings, health: Optional[Health] = None) -> None:
        self.s = settings
        self.health = health
        self.tz = ZoneInfo(settings.timezone)
        self.headers = {"User-Agent": f"tak-feeder-lightnings-fmi/{__version__}"}

    def url(self, now: datetime) -> str:
        """WFS query for the history window ending now."""
        args = {
            "service": "WFS", "version": "2.0.0", "request": "getFeature",
            "storedquery_id": QUERY,
            "starttime": (now - timedelta(seconds=self.s.history)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endtime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if self.s.bbox:
            args["bbox"] = self.s.bbox
        return f"{WFS_URL}?{urlencode(args, safe=',:')}"

    def strike_event(self, strike: Strike, now: datetime) -> bytes:
        """CoT for one strike, coloured by age."""
        v = strike.values
        current = v.get("peak_current")
        cloud = v.get("cloud_indicator")
        lines = [
            f"Strike time: {strike.time.astimezone(self.tz).strftime('%H:%M:%S')}",
            f"Peak current: {current:.0f} kA" if current is not None else None,
            None if cloud is None else ("Cloud flash" if cloud else "Cloud-to-ground"),
        ]
        ce = v.get("ellipse_major", 0.1) * 1000  # km -> m
        return cot_event(
            uid=(f"lightning-{strike.time.strftime('%Y%m%dT%H%M%SZ')}"
                 f"-{strike.lon}-{strike.lat}"),  # as in upstream
            cot_type="a-o-G",  # ATAK does not stale out b-w-A-S-T-L (upstream note)
            lat=strike.lat, lon=strike.lon,
            callsign="FMI Lightning",
            remarks=remarks_text(lines, self.s.source_line, ("weather", "lightning")),
            stale=self.s.update_interval * 2 + 10,
            how="m-c",
            hae=5000.0,
            ce=ce,
            icon=ICON,
            color=age_color((now - strike.time).total_seconds()),
        )

    async def events(self) -> list[bytes]:
        """Source protocol: fetch and convert."""
        now = datetime.now(timezone.utc)
        try:
            body = await fetch(self.url(now), self.headers, timeout=60)
            stamp, strikes = parse(body)
        except Exception as exc:  # noqa: BLE001  pylint: disable=broad-exception-caught
            LOG.warning("FMI lightning request failed: %s", exc)
            if self.health is not None:
                self.health.error()
            return []
        if self.health is not None:
            self.health.ok()
        ref = stamp or now  # FMI's clock, so ages are right even if ours is off
        LOG.debug("Lightning: %d strikes", len(strikes))
        return [self.strike_event(s, ref) for s in strikes]

    async def start(self) -> None:
        """Nothing runs in the background."""
