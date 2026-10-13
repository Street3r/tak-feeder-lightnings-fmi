# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the lightning feeder."""

import asyncio
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from unittest import mock

from tak_feeder_lightnings_fmi import feeder

NOW = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)
T_OLD = int(NOW.timestamp()) - 1000
T_NEW = int(NOW.timestamp()) - 60

SAMPLE = f"""<wfs:FeatureCollection timeStamp="2026-10-13T12:00:00Z"
 xmlns:wfs="http://www.opengis.net/wfs/2.0" xmlns:gml="http://www.opengis.net/gml/3.2"
 xmlns:gmlcov="http://www.opengis.net/gmlcov/1.0" xmlns:swe="http://www.opengis.net/swe/2.0">
 <gmlcov:positions>
   62.5 25.7 {T_NEW}
   61.0 24.0 {T_OLD}
 </gmlcov:positions>
 <gml:doubleOrNilReasonTupleList>
   1.0 -12.0 0.0 0.3
   2.0 25.0 1.0 NaN
 </gml:doubleOrNilReasonTupleList>
 <swe:field name="multiplicity"/><swe:field name="peak_current"/>
 <swe:field name="cloud_indicator"/><swe:field name="ellipse_major"/>
</wfs:FeatureCollection>""".encode()


class LightningTest(unittest.TestCase):
    def test_parse_oldest_first(self) -> None:
        stamp, strikes = feeder.parse(SAMPLE)
        self.assertEqual(stamp, NOW)
        self.assertEqual([s.lat for s in strikes], [61.0, 62.5])
        self.assertEqual(strikes[1].values["ellipse_major"], 0.3)
        self.assertNotIn("ellipse_major", strikes[0].values)

    def test_events(self) -> None:
        src = feeder.LightningSource(feeder.Settings())
        with mock.patch.object(feeder, "fetch", mock.AsyncMock(return_value=SAMPLE)):
            old, new = [ET.fromstring(e) for e in asyncio.run(src.events())]
        self.assertEqual(new.find("detail/color").get("argb"), "-1")  # 60 s old
        self.assertEqual(old.find("detail/color").get("argb"), "-35072")  # 1000 s old
        self.assertEqual(new.find("detail/contact").get("callsign"), "FMI Lightning")
        self.assertEqual(new.find("point").get("ce"), "300.0")
        text = new.find("detail/remarks").text
        self.assertIn("Peak current: -12 kA", text)
        self.assertIn("Cloud-to-ground", text)
        self.assertTrue(text.endswith("#weather #lightning"))
        self.assertTrue(new.get("uid").startswith("lightning-20261013T115900Z-25.7-62.5"))

    def test_history_default_and_window(self) -> None:
        settings = feeder.Settings()
        self.assertEqual(settings.history, 1800)
        url = feeder.LightningSource(settings).url(NOW)
        self.assertIn("starttime=2026-10-13T11:30:00Z", url)

    def test_fmi_down(self) -> None:
        src = feeder.LightningSource(feeder.Settings())
        with mock.patch.object(feeder, "fetch", mock.AsyncMock(side_effect=OSError("x"))):
            self.assertEqual(asyncio.run(src.events()), [])

    def test_empty(self) -> None:
        self.assertEqual(feeder.parse(b"<a/>")[1], [])


if __name__ == "__main__":
    unittest.main()
