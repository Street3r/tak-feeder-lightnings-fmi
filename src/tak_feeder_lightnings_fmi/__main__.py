# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright Stefan Gofferje (tak-feeder-lightnings-fmi)
# Copyright (C) 2026 Street3r (changes, see README)
"""Run the feeder: python -m tak_feeder_lightnings_fmi"""

from __future__ import annotations

import asyncio
import logging

from . import __version__
from .common import Health, TakSettings, run_feeder, setup_logging
from .feeder import Settings, LightningSource

LOG = logging.getLogger("tak_feeder_lightnings_fmi")


async def main() -> None:
    """Read settings and run."""
    tak = TakSettings.from_env()
    setup_logging(tak.debug)
    settings = Settings.from_env()
    LOG.info("tak-feeder-lightnings-fmi %s -> %s (history %.0f s)", __version__, tak.cot_url,
             settings.history)
    await run_feeder(tak, LightningSource(settings, Health()), min(settings.fetch_interval, settings.send.static))


def run() -> None:
    """Console script entry point."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
