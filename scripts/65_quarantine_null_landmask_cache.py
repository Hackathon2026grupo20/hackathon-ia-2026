#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path


def all_null(values) -> bool:
    if not isinstance(values, list) or not values:
        return True
    for value in values:
        if value is None:
            continue
        try:
            if math.isfinite(float(value)):
                return False
        except (TypeError, ValueError):
            return False
    return True


def invalid_temperature_payload(obj: dict) -> tuple[bool, str | None]:
    payload = obj.get("payload") or {}

    hourly = payload.get("hourly") or {}
    if "temperature_2m" in hourly and all_null(hourly.get("temperature_2m")):
        return True, "hourly.temperature_2m_all_null"

    daily = payload.get("daily") or {}
    daily_vars = [
        name
        for name in ("temperature_2m_max", "temperature_2m_min", "temperature_2m_mean")
        if name in daily
    ]
    if daily_vars and all(all_null(daily.get(name)) for name in daily_vars):
        return True, "daily.temperature_all_null"

    return False, None


def main() -> None:
    p = argparse.ArgumentParser(
        description=(
            "Quarantine cached ERA5-Land RAW records whose temperature is entirely "
            "null, so the next climate download refetches only those gaps through "
            "the ARCO land-mask fallback."
        )
    )
    p.add_argument("--root", required=True)
    p.add_argument("--quarantine-root", required=True)
    p.add_argument("--report")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    root = Path(a.root)
    quarantine = Path(a.quarantine_root)

    scanned = 0
    invalid = []
    coordinates = set()

    if root.exists():
        for path in root.rglob("*.json"):
            scanned += 1
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue

            bad, reason = invalid_temperature_payload(obj)
            if not bad:
                continue

            payload = obj.get("payload") or {}
            lat = payload.get("latitude")
            lon = payload.get("longitude")
            if lat is not None and lon is not None:
                coordinates.add((float(lat), float(lon)))

            rel = path.relative_to(root)
            destination = quarantine / rel
            invalid.append(
                {
                    "path": str(path),
                    "destination": str(destination),
                    "reason": reason,
                    "latitude": lat,
                    "longitude": lon,
                    "external_id": obj.get("external_id"),
                }
            )

            if not a.dry_run:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    destination.unlink()
                shutil.move(str(path), str(destination))

    report = {
        "root": str(root),
        "quarantine_root": str(quarantine),
        "dry_run": bool(a.dry_run),
        "scanned_json": scanned,
        "quarantined_files": len(invalid),
        "distinct_bad_coordinates": [
            {"latitude": lat, "longitude": lon}
            for lat, lon in sorted(coordinates)
        ],
        "records": invalid,
    }

    if a.report:
        rp = Path(a.report)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"PREDICTA_LANDMASK_CACHE_CHECK scanned={scanned} "
        f"invalid={len(invalid)} coordinates={len(coordinates)} dry_run={a.dry_run}"
    )
    for lat, lon in sorted(coordinates):
        print(f"  bad_coordinate={lat:.5f},{lon:.5f}")


if __name__ == "__main__":
    main()
