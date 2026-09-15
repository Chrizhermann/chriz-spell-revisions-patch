"""Build Windows ZIPs from committed Git files and a verified WeiDU donor archive.

Donor: SRCB_RR_COMPAT-v4-21-chriz-4.zip from this repository's v4.21-chriz.4
release. Its hash pins the official WeiDU 249 x64 executable, manual and license
already verified for that release. No files are taken from an installed game.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DONOR_SHA256 = "6276bfdb3610e0d7d5100f845e14037812d739b7fcf287b4c51152428c161298"
MODS = ("spell_rev", "SRCB_RR_COMPAT", "SRCB_CLASSIC_LIGHTNING")


def package(donor: Path, output: Path) -> list[dict]:
    donor_bytes = donor.read_bytes()
    if hashlib.sha256(donor_bytes).hexdigest() != DONOR_SHA256:
        raise ValueError("WeiDU donor archive does not match the verified release")
    with zipfile.ZipFile(io.BytesIO(donor_bytes)) as donor_zip:
        executable = donor_zip.read("Setup-SRCB_RR_COMPAT.exe")
        shared = {name: donor_zip.read(name) for name in ("README-WeiDU.html", "WeiDU-COPYING.txt")}
    if not executable.startswith(b"MZ"):
        raise ValueError("WeiDU donor is not a Windows executable")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    raw = subprocess.check_output(["git", "archive", "--format=zip", "HEAD", "spell_rev", "README.md",
                                   "live-patch/SRCB_RR_COMPAT", "live-patch/SRCB_CLASSIC_LIGHTNING"], cwd=ROOT)
    with zipfile.ZipFile(io.BytesIO(raw)) as source:
        payload = {entry.filename: source.read(entry) for entry in source.infolist() if not entry.is_dir()}
        timestamp = source.getinfo("README.md").date_time
    tp2 = payload["spell_rev/setup-spell_rev.tp2"].decode("utf-8")
    version = re.search(r"VERSION\s+~(v4\.21-chriz\.\d+)~", tp2).group(1)
    for mod in MODS[1:]:
        if f"VERSION ~{version}~" not in payload[f"live-patch/{mod}/setup-{mod}.tp2"].decode("utf-8"):
            raise ValueError(f"Version mismatch in {mod}")
    if payload["spell_rev/lib/classic_lightning_bolt.tpa"] != payload["live-patch/SRCB_CLASSIC_LIGHTNING/lib/classic_lightning_bolt.tpa"]:
        raise ValueError("Lightning source and tail implementations differ")
    release_notes = subprocess.check_output(["git", "show", f"HEAD:docs/releases/{version}.md"], cwd=ROOT)
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for package_name in MODS:
        files = dict(shared)
        files["RELEASE-NOTES.md"] = release_notes
        for mod in MODS if package_name == "spell_rev" else (package_name,):
            prefix = "spell_rev/" if mod == "spell_rev" else f"live-patch/{mod}/"
            for name, data in payload.items():
                if name.startswith(prefix):
                    files[name.removeprefix("live-patch/")] = data
            files[f"Setup-{mod}.exe"] = executable
        if package_name == "spell_rev":
            files["README.md"] = payload["README.md"]
        destination = output / f"{package_name}-{version.replace('.', '-')}.zip"
        if destination.exists():
            raise FileExistsError(destination)
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(files.items()):
                entry = zipfile.ZipInfo(name, timestamp)
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, data, compresslevel=9)
        with zipfile.ZipFile(destination) as archive:
            if archive.testzip() is not None or set(archive.namelist()) != set(files):
                raise ValueError(f"Archive verification failed: {destination}")
            for name, data in files.items():
                if archive.read(name) != data:
                    raise ValueError(f"Archive content mismatch: {name}")
        results.append({"file": str(destination), "revision": revision, "version": version,
                        "size": destination.stat().st_size,
                        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                        "files": len(files), "roots": sorted({name.split('/')[0] for name in files})})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weidu-donor", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    options = parser.parse_args()
    print(json.dumps(package(options.weidu_donor, options.output), indent=2))
