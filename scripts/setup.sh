#!/usr/bin/env bash
# One-time setup for a headless machine (cloud container, CI, server).
set -euo pipefail
python3 -m pip install -r "$(dirname "$0")/../requirements.txt"
# Optional: EEVEE (toon shading previews) on machines without a GPU needs Mesa's software EGL.
if command -v apt-get >/dev/null && [ "${WITH_EEVEE:-0}" = "1" ]; then
  apt-get install -y libegl1 libegl-mesa0 libgl1-mesa-dri libgbm1
  echo "Run EEVEE renders with EGL_PLATFORM=surfaceless"
fi
