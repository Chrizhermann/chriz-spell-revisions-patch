"""Shared WeiDU test plumbing: locate weidu.exe, run it, build synthetic fake games.

Two patterns (see chriz-bg-rebalance/tests and the bg-modding `weidu-testing` notes):

* ``--nogame`` harness — a tp2 whose components COPY a fixture file to an output path and
  run production patch functions on it (unit-tests file-based library code).
* synthetic fake game — a minimal ``chitin.key`` + one BIFF + TLKs that ``weidu --game``
  accepts, so code that needs ``COPY_EXISTING`` / ``IDS_OF_SYMBOL`` / ``GAME_IS`` runs its
  real path.  No live game directory is ever touched.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RESOURCE_TYPE = {"SPL": 1006, "IDS": 1008, "CRE": 1009, "ARE": 1010, "2DA": 1012}

ONE_EMPTY_STRING_TLK = (
    struct.pack("<8sHII", b"TLK V1  ", 0, 1, 0x2C)
    + struct.pack("<H8siiII", 0, b"\0" * 8, 0, 0, 0, 0)
)

MIN_WEIDU_VERSION = 24900  # --parse-check arrived with 249


def find_weidu() -> Path:
    candidates: list[Path] = []
    env = os.environ.get("WEIDU")
    if env:
        candidates.append(Path(env))
    candidates.append(ROOT.parent / "chriz-bg-rebalance" / "weidu.exe")
    for name in ("weidu.exe", "weidu"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "weidu.exe not found. Set WEIDU=<path to weidu.exe v249 or newer> "
        "(any Setup-*.exe from a WeiDU mod works, copied to a neutral name)."
    )


WEIDU = find_weidu()


def weidu_version() -> int:
    process = subprocess.run(
        [str(WEIDU), "--version"], capture_output=True, text=True, timeout=60, check=False
    )
    match = re.search(r"WeiDU version (\d+)", process.stdout + process.stderr)
    if not match:
        raise RuntimeError(f"cannot parse WeiDU version from: {process.stdout!r}")
    return int(match.group(1))


def run_weidu(args: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(WEIDU), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def transcript(process: subprocess.CompletedProcess[str]) -> str:
    return f"{process.stdout}\n{process.stderr}".strip()


def assert_installed(process: subprocess.CompletedProcess[str]) -> None:
    text = transcript(process)
    assert ("SUCCESSFULLY INSTALLED" in text) or ("INSTALLED WITH WARNINGS" in text), text
    assert "NOT INSTALLED DUE TO ERRORS" not in text, text


def parse_check(kind: str, path: Path) -> subprocess.CompletedProcess[str]:
    """`weidu --nogame --parse-check TYPE file` (order matters; no trailing flags)."""
    return run_weidu(["--nogame", "--parse-check", kind, str(path)], cwd=path.parent)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nogame_harness(
    harness_tp2: Path,
    component: int,
    run_dir: Path,
    args: list[str],
) -> subprocess.CompletedProcess[str]:
    """Run one component of a --nogame harness tp2 with one value per --args."""
    run_dir.mkdir(parents=True, exist_ok=True)
    command = [str(harness_tp2), "--nogame", "--force-install-list", str(component)]
    for value in args:
        command += ["--args", value]
    command += ["--no-exit-pause", "--quick-log"]
    return run_weidu(command, cwd=run_dir)


def write_key_and_bif(
    game_root: Path,
    resources: tuple[tuple[str, str, bytes], ...],
    bif_relative: Path = Path("DATA/SRCBTEST.BIF"),
) -> Path:
    """Write one uncompressed BIFF V1 and a KEY V1 that indexes every resource."""
    bif_path = game_root / bif_relative
    bif_path.parent.mkdir(parents=True, exist_ok=True)

    table_offset = 0x14
    payload_offset = table_offset + len(resources) * 0x10
    table = bytearray()
    payloads = bytearray()
    key_entries: list[tuple[str, int, int]] = []
    for index, (resref, extension, payload) in enumerate(resources):
        resource_type = RESOURCE_TYPE[extension.upper()]
        table.extend(
            struct.pack("<IIIHH", index, payload_offset + len(payloads), len(payload), resource_type, 0)
        )
        payloads.extend(payload)
        key_entries.append((resref.upper(), resource_type, index))
    bif_path.write_bytes(
        struct.pack("<4s4sIII", b"BIFF", b"V1  ", len(resources), 0, table_offset) + table + payloads
    )

    encoded_bif_name = (str(bif_relative).replace("/", "\\") + "\0").encode("ascii")
    bif_table_offset = 0x18
    resource_table_offset = bif_table_offset + 0x0C
    names_offset = resource_table_offset + len(resources) * 0x0E
    key = bytearray(
        struct.pack("<4s4sIIII", b"KEY ", b"V1  ", 1, len(resources), bif_table_offset, resource_table_offset)
    )
    key.extend(struct.pack("<IIHH", bif_path.stat().st_size, names_offset, len(encoded_bif_name), 0))
    for resref, resource_type, locator in key_entries:
        key.extend(struct.pack("<8sHI", resref.encode("ascii").ljust(8, b"\0"), resource_type, locator))
    key.extend(encoded_bif_name)
    (game_root / "chitin.key").write_bytes(key)
    return bif_path


class FakeGame:
    """A throwaway BG2:EE-shaped game directory for `weidu --game`."""

    def __init__(self, root: Path, resources: tuple[tuple[str, str, bytes], ...]):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.override = self.root / "override"
        self.override.mkdir(exist_ok=True)
        self.bif_path = write_key_and_bif(self.root, resources)
        self.lang_tlk = self.root / "lang" / "en_US" / "dialog.tlk"
        self.lang_tlk.parent.mkdir(parents=True, exist_ok=True)
        self.lang_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.root_tlk = self.root / "dialog.tlk"
        self.root_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.stable_hashes = self._input_hashes()

    def _input_hashes(self) -> dict[str, str]:
        return {
            "key": sha256(self.root / "chitin.key"),
            "bif": sha256(self.bif_path),
            "lang_tlk": sha256(self.lang_tlk),
            "root_tlk": sha256(self.root_tlk),
        }

    def assert_inputs_unchanged(self) -> None:
        assert self._input_hashes() == self.stable_hashes

    def run(self, tp2_relative: str, operation: str, component: int) -> subprocess.CompletedProcess[str]:
        return run_weidu(
            [
                tp2_relative,
                "--game",
                str(self.root),
                operation,
                str(component),
                "--language",
                "0",
                "--use-lang",
                "en_US",
                "--no-exit-pause",
                "--quick-log",
            ],
            cwd=self.root,
        )

    def install(self, tp2_relative: str, component: int) -> subprocess.CompletedProcess[str]:
        return self.run(tp2_relative, "--force-install-list", component)

    def uninstall(self, tp2_relative: str, component: int) -> subprocess.CompletedProcess[str]:
        return self.run(tp2_relative, "--force-uninstall-list", component)

    def weidu_log(self) -> str:
        path = self.root / "WeiDU.log"
        return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""

    def active_weidu_log(self) -> str:
        return "\n".join(
            line for line in self.weidu_log().splitlines() if not line.lstrip().startswith("//")
        )

    def append_weidu_log(self, line: str) -> None:
        path = self.root / "WeiDU.log"
        existing = self.weidu_log()
        if existing and not existing.endswith("\n"):
            existing += "\n"
        path.write_text(existing + line + "\n", encoding="utf-8")

    def override_file(self, name: str) -> Path | None:
        wanted = name.upper()
        for candidate in self.override.iterdir():
            if candidate.name.upper() == wanted:
                return candidate
        return None

    def override_tree(self) -> dict[str, bytes]:
        return {
            path.name.upper(): path.read_bytes()
            for path in sorted(self.override.iterdir())
            if path.is_file()
        }
