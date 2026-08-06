from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path


def render_m3u8(manifest: dict[str, object]) -> str:
    lines = ["#EXTM3U"]
    for item in manifest["resolved"]:
        assert isinstance(item, dict)
        lines.append(f"#EXTINF:-1,{item['display_name']}")
        lines.append(str(item["playlist_path"]))
    return "\n".join(lines) + "\n"


def render_missing_report(manifest: dict[str, object]) -> str:
    return json.dumps({"missing": manifest["missing"]}, indent=2, sort_keys=True) + "\n"


def export_basename(name: str, export_id: int) -> str:
    clean = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(". ") or "collection"
    return f"{clean} [{export_id}]"


def write_export_artifacts(
    export_root: Path, name: str, export_id: int, manifest: dict[str, object]
) -> tuple[str, str, str]:
    export_root.mkdir(parents=True, exist_ok=True)
    base = export_basename(name, export_id)
    m3u8_path = export_root / f"{base}.m3u8"
    report_path = export_root / f"{base}.missing.json"
    m3u8 = render_m3u8(manifest)
    report = render_missing_report(manifest)
    _atomic_write(m3u8_path, m3u8)
    _atomic_write(report_path, report)
    digest = hashlib.sha256((m3u8 + report).encode("utf-8")).hexdigest()
    return m3u8_path.name, report_path.name, digest


def _atomic_write(path: Path, contents: str) -> None:
    temporary = path.with_name(f".{path.name}.partial")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
