"""Land dots for the dashboard globe, computed once from Natural Earth's 110m land polygons (public domain)."""

from __future__ import annotations

import json
import math
from pathlib import Path

from .http import get_json

LAND_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_land.geojson"


def _rings(geojson: dict) -> list[list[list[float]]]:
    """Outer rings of every land polygon (the 110m file has no holes worth keeping)."""
    rings = []
    for feature in geojson["features"]:
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        rings += [polygon[0] for polygon in polygons]
    return rings


def _inside(lng: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray casting. Good enough for dots; points exactly on an edge can land either way."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def land_dots(step: float = 1.6, min_lat: float = -58.0) -> list[list[float]]:
    """[lat, lng] pairs on an equal-area grid, kept where they fall on land."""
    rings = _rings(get_json(LAND_URL, ttl_hours=24 * 365))
    boxes = [(min(p[0] for p in r), max(p[0] for p in r), min(p[1] for p in r), max(p[1] for p in r), r) for r in rings]
    dots = []
    lat = 90 - step / 2
    while lat > min_lat:
        lng_step = step / max(math.cos(math.radians(lat)), 0.05)
        lng = -180 + lng_step / 2
        while lng < 180:
            if any(x0 <= lng <= x1 and y0 <= lat <= y1 and _inside(lng, lat, r) for x0, x1, y0, y1, r in boxes):
                dots.append([round(lat, 2), round(lng, 2)])
            lng += lng_step
        lat -= step
    return dots


def ensure_land_dots(path: Path) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(land_dots(), separators=(",", ":")))
    return path
