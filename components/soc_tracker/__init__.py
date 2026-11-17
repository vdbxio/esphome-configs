# soc_tracker: header-only SoC state machine for packages/parts/ina2xx-soc.yaml
# Voidbox Industries & Chloe Madison — VDBX.io / @clomads — CC-BY-SA 4.0
#
# Shipped as an external component (not esphome: includes:) because includes are
# resolved against the user's config dir, which breaks github:// packages.
# Logic lives in soc_tracker.h; host test: tests/soc_tracker_test.cpp.

import esphome.codegen as cg
import esphome.config_validation as cv

CODEOWNERS = ["@clomads"]

CONFIG_SCHEMA = cv.Schema({})


async def to_code(config):
    cg.add_global(cg.RawStatement('#include "esphome/components/soc_tracker/soc_tracker.h"'))
