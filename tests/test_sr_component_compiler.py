from __future__ import annotations

import hashlib
import importlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from tools.sr_config.catalog import Catalog
from tools.sr_config.generate import GenerationError
from tools.sr_config.resolve import feature_symbols
from tools.sr_config.source import resolve_span_offsets
from tests.weidu_env import parse_check, transcript


UPSTREAM_COMMIT = "af1dedb6d211f86ad7a321d4080e46c748e8abac"


def _span(path: str, source: bytes, start: bytes, end: bytes | None) -> dict[str, Any]:
    start_offset = source.index(start)
    end_offset = len(source) if end is None else source.index(end)
    raw = source[start_offset:end_offset].replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return {
        "path": path,
        "start": start.decode("ascii"),
        "end": None if end is None else end.decode("ascii"),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _catalog(source: bytes) -> Catalog:
    path = "spell_rev/components/main_component.tpa"
    change_span = _span(path, source, b"COPY ~arcane.spl~", b"COPY ~shared.spl~")
    infrastructure_span = _span(
        path, source, b"COPY ~shared.spl~", b"COPY ~deferred.spl~"
    )
    deferred_span = _span(
        path, source, b"COPY ~deferred.spl~", b"COPY ~hardiness.spl~"
    )
    excluded_span = _span(path, source, b"COPY ~hardiness.spl~", None)
    return Catalog.from_dict(
        {
            "schema_version": 1,
            "upstream": {"tag": "v4.21", "commit": UPSTREAM_COMMIT},
            "migration": {"complete": False, "installer_source": path},
            "groups": [
                {
                    "id": "global",
                    "setting": "sr_default",
                    "name": "All changes",
                    "default": 1,
                    "parent": None,
                }
            ],
            "changes": [
                {
                    "id": "arcane.example",
                    "setting": "sr_arcane_example",
                    "display_name": "Arcane example",
                    "default": -1,
                    "group": "global",
                    "component": 0,
                    "games": ["bg2ee"],
                    "name_ref": "@1",
                    "name_fallback": None,
                    "description_ref": "@2",
                    "member_refs": [],
                    "source_spans": [change_span],
                    "resources": [],
                    "atomic_group": None,
                    "requires": [],
                    "conflicts": [],
                    "soft_requires": [],
                    "processors": ["shared.example"],
                    "documentation_only_reason": None,
                }
            ],
            "infrastructure": [
                {
                    "id": "shared.example",
                    "activation": "consumer_selected",
                    "infrastructure_requires": [],
                    "category": "derived",
                    "source_spans": [infrastructure_span],
                    "resources": [],
                    "consumers": ["arcane.example"],
                    "include_resolutions": [],
                    "source_resolutions": [],
                }
            ],
            "component_zero_closure_roots": [],
            "dormant_resources": [],
            "deferred_source_scopes": [
                {
                    "id": "deferred.example",
                    "reason": "Kept for upstream parity in the MVP.",
                    "source_spans": [deferred_span],
                    "resources": [],
                },
                {
                    "id": "excluded.hardiness_spcl907",
                    "reason": "Owned separately by the author's balance work.",
                    "source_spans": [excluded_span],
                    "resources": [],
                },
            ],
            "binary_edge_resolutions": [],
        }
    )


def test_component_compiler_guards_owned_spans_and_preserves_deferred_code(
    tmp_path: Path,
) -> None:
    source = (
        b"COPY ~arcane.spl~ ~override~\n"
        b"COPY ~shared.spl~ ~override~\n"
        b"COPY ~deferred.spl~ ~override~\n"
        b"COPY ~hardiness.spl~ ~override~\n"
    )
    source_path = tmp_path / "spell_rev" / "components" / "main_component.tpa"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source)
    module = importlib.import_module("tools.sr_config.generate")
    compiler = getattr(module, "render_component_zero_sources", None)

    assert callable(compiler), "component-zero source compiler is missing"
    outputs = compiler(tmp_path, _catalog(source))
    generated = outputs[
        Path("spell_rev/generated/component0/components/main_component.tpa")
    ]

    assert b"ACTION_IF (sr_feature_000001 = 1) BEGIN" in generated
    assert b"ACTION_IF (sr_infra_000001 = 1) BEGIN" in generated
    assert b"COPY ~deferred.spl~ ~override~" in generated
    assert b"hardiness.spl" not in generated
    assert generated.index(b"arcane.spl") < generated.index(b"shared.spl")
    assert generated.index(b"shared.spl") < generated.index(b"deferred.spl")


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "spell_rev" / "catalog" / "changes.json"
_GUARD = re.compile(
    rb"// SR_CONFIG_GUARD_BEGIN (?P<owner>[^\r\n]+)\r?\n"
    rb"ACTION_IF \((?P<flag>sr_(?:feature|infra)_[0-9]{6}) = 1\) BEGIN\r?\n"
    rb"(?P<body>.*?)"
    rb"END\r?\n// SR_CONFIG_GUARD_END (?P=owner)\r?\n",
    re.DOTALL,
)


@pytest.fixture(scope="module")
def production_compilation() -> tuple[Catalog, dict[Path, bytes]]:
    catalog = importlib.import_module("tools.sr_config.catalog").load_catalog(
        CATALOG_PATH
    )
    compiler = importlib.import_module(
        "tools.sr_config.generate"
    ).render_component_zero_sources
    return catalog, compiler(ROOT, catalog)


def _strip_guards(source: bytes) -> bytes:
    while _GUARD.search(source):
        source = _GUARD.sub(lambda match: match.group("body"), source)
    return source


def _materialize(source: bytes, enabled: set[str]) -> bytes:
    while _GUARD.search(source):
        source = _GUARD.sub(
            lambda match: match.group("body")
            if match.group("flag").decode("ascii") in enabled
            else b"",
            source,
        )
    return source


def _generated_path(source_path: str) -> Path:
    source = Path(source_path)
    return Path("spell_rev/generated/component0").joinpath(*source.parts[1:])


def _expected_without_hardiness(catalog: Catalog, source_path: str) -> bytes:
    source = (ROOT / source_path).read_bytes()
    excluded = next(
        record
        for record in catalog.deferred_source_scopes
        if record.id == "excluded.hardiness_spcl907"
    )
    intervals = [
        resolve_span_offsets(ROOT, span)
        for span in excluded.source_spans
        if span.path == source_path
    ]
    for interval in sorted(intervals, key=lambda item: item.start, reverse=True):
        source = source[: interval.start] + source[interval.end :]
    return source


def _normalize_internal_paths(
    source: bytes, compiled_source_paths: set[str]
) -> bytes:
    for index, original in enumerate(
        sorted(compiled_source_paths, key=len, reverse=True), start=1
    ):
        path = Path(original)
        relative = "/".join(path.parts[1:])
        generated = _generated_path(original).as_posix()
        token = f"<SOURCE_{index:03d}>".encode("ascii")
        variants = {
            original.replace("\\", "/"),
            original.replace("/", "\\"),
            f"%MOD_FOLDER%/{relative}",
            f"%MOD_FOLDER%\\{relative.replace('/', chr(92))}",
            generated,
        }
        for variant in variants:
            source = source.replace(variant.encode("ascii"), token)
    return source


def test_all_on_sources_preserve_upstream_order_and_content_except_hardiness(
    production_compilation: tuple[Catalog, dict[Path, bytes]],
) -> None:
    catalog, outputs = production_compilation
    closure_paths = {
        root.source_span.path for root in catalog.component_zero_closure_roots
    }
    source_paths = {
        span.path
        for record in (*catalog.changes, *catalog.infrastructure)
        for span in record.source_spans
        if span.path not in closure_paths
    }
    source_paths.update(
        span.path
        for record in catalog.deferred_source_scopes
        for span in record.source_spans
        if span.path not in closure_paths
    )

    for source_path in source_paths:
        generated = _strip_guards(outputs[_generated_path(source_path)])
        expected = _expected_without_hardiness(catalog, source_path)
        assert _normalize_internal_paths(generated, source_paths).splitlines() == (
            _normalize_internal_paths(expected, source_paths).splitlines()
        )


@pytest.mark.parametrize(
    "change_id",
    ["arcane.level1.grease", "divine.bless"],
)
def test_turning_off_a_choice_suppresses_its_owned_source_and_resource_copies(
    production_compilation: tuple[Catalog, dict[Path, bytes]], change_id: str
) -> None:
    catalog, outputs = production_compilation
    change = next(record for record in catalog.changes if record.id == change_id)
    flags = feature_symbols(catalog)
    all_flags = set(flags.values())
    selected_without_choice = all_flags - {flags[change.id]}

    for span in change.source_spans:
        generated = outputs[_generated_path(span.path)]
        materialized = _materialize(generated, selected_without_choice)
        raw = resolve_span_offsets(ROOT, span).raw
        assert raw not in materialized
        assert raw in _materialize(generated, all_flags)
        for resource in change.resources:
            if resource.path.encode("ascii") in raw.replace(b"\\", b"/"):
                assert resource.path.encode("ascii") not in materialized.replace(
                    b"\\", b"/"
                )


@pytest.mark.parametrize(
    "infrastructure_id",
    [
        "shared.contagion_delivery_spell",
        "shared.polymorph_squirrel_item",
        "shared.true_seeing_detection_spell",
    ],
)
def test_new_shared_helper_activates_for_each_consumer_and_not_without_one(
    production_compilation: tuple[Catalog, dict[Path, bytes]],
    infrastructure_id: str,
) -> None:
    catalog, outputs = production_compilation
    infrastructure = next(
        record for record in catalog.infrastructure if record.id == infrastructure_id
    )
    infrastructure_index = catalog.infrastructure.index(infrastructure) + 1
    infrastructure_flag = f"sr_infra_{infrastructure_index:06d}"
    feature_flags = feature_symbols(catalog)
    entry = outputs[Path("spell_rev/generated/component0/entry.tpa")].decode("utf-8")
    section = entry.split(
        f"// SR_CONFIG_INFRA_BEGIN {infrastructure.id}", 1
    )[1].split(f"// SR_CONFIG_INFRA_END {infrastructure.id}", 1)[0]

    assert set(re.findall(r"ACTION_IF \((sr_feature_[0-9]{6}) = 1\)", section)) == {
        feature_flags[consumer] for consumer in infrastructure.consumers
    }
    for span in infrastructure.source_spans:
        generated = outputs[_generated_path(span.path)]
        raw = resolve_span_offsets(ROOT, span).raw
        assert raw not in _materialize(generated, set())
        for consumer in infrastructure.consumers:
            assert raw in _materialize(
                generated,
                {feature_flags[consumer], infrastructure_flag},
            )


def test_unassigned_infrastructure_stays_on_for_upstream_parity(
    production_compilation: tuple[Catalog, dict[Path, bytes]],
) -> None:
    catalog, outputs = production_compilation
    entry = outputs[Path("spell_rev/generated/component0/entry.tpa")].decode("utf-8")
    required = {
        requirement
        for record in catalog.infrastructure
        for requirement in record.infrastructure_requires
    }
    unassigned = [
        record
        for record in catalog.infrastructure
        if record.activation == "consumer_selected"
        and not record.consumers
        and record.id not in required
    ]

    assert {record.id for record in unassigned} == {
        "global.cre_spell_immunity_library",
        "compat.iwdee_bone_circle_cleanup",
    }
    for record in unassigned:
        index = catalog.infrastructure.index(record) + 1
        section = entry.split(
            f"// SR_CONFIG_INFRA_BEGIN {record.id}", 1
        )[1].split(f"// SR_CONFIG_INFRA_END {record.id}", 1)[0]
        assert f"OUTER_SET sr_infra_{index:06d} = 1" in section


def test_compiler_rewrites_internal_includes_and_emits_guarded_postlude(
    production_compilation: tuple[Catalog, dict[Path, bytes]],
) -> None:
    catalog, outputs = production_compilation
    main = outputs[
        Path("spell_rev/generated/component0/components/main_component.tpa")
    ]
    entry = outputs[Path("spell_rev/generated/component0/entry.tpa")]

    assert b"INCLUDE ~spell_rev/generated/component0/lib/cre_spell_immunity.tph~" in main
    assert b"INCLUDE ~spell_rev\\lib\\cre_spell_immunity.tph~" not in main
    assert b"INCLUDE ~spell_rev/generated/component0/components/main_component.tpa~" in entry
    closure_paths = {
        root.source_span.path for root in catalog.component_zero_closure_roots
    }
    compiled_source_paths = {
        span.path
        for record in (*catalog.changes, *catalog.infrastructure)
        for span in record.source_spans
        if span.path not in closure_paths
    }
    for closure_root in catalog.component_zero_closure_roots:
        expected = resolve_span_offsets(ROOT, closure_root.source_span).raw
        assert _normalize_internal_paths(expected, compiled_source_paths) in (
            _normalize_internal_paths(_strip_guards(entry), compiled_source_paths)
        )


def test_primary_component_stream_is_never_hidden_by_a_processor_guard(
    production_compilation: tuple[Catalog, dict[Path, bytes]],
) -> None:
    _, outputs = production_compilation
    entry = outputs[Path("spell_rev/generated/component0/entry.tpa")]

    assert (
        b"INCLUDE ~spell_rev/generated/component0/components/main_component.tpa~"
        in _materialize(entry, set())
    )


def test_compiler_rejects_overlapping_spans(tmp_path: Path) -> None:
    source = (
        b"COPY ~arcane.spl~ ~override~\n"
        b"COPY ~shared.spl~ ~override~\n"
        b"COPY ~deferred.spl~ ~override~\n"
        b"COPY ~hardiness.spl~ ~override~\n"
    )
    source_path = tmp_path / "spell_rev" / "components" / "main_component.tpa"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source)
    raw = json.loads(json.dumps(asdict(_catalog(source))))
    raw["changes"][0]["source_spans"][0] = _span(
        "spell_rev/components/main_component.tpa",
        source,
        b"COPY ~arcane.spl~",
        b"COPY ~deferred.spl~",
    )

    with pytest.raises(GenerationError, match="overlapping source span"):
        importlib.import_module("tools.sr_config.generate").render_component_zero_sources(
            tmp_path, Catalog.from_dict(raw)
        )


def test_compiler_rejects_uncovered_executable_source(tmp_path: Path) -> None:
    source = (
        b"COPY ~arcane.spl~ ~override~\n"
        b"COPY ~unowned.spl~ ~override~\n"
        b"COPY ~shared.spl~ ~override~\n"
        b"COPY ~deferred.spl~ ~override~\n"
        b"COPY ~hardiness.spl~ ~override~\n"
    )
    source_path = tmp_path / "spell_rev" / "components" / "main_component.tpa"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source)
    raw = json.loads(json.dumps(asdict(_catalog(source))))
    raw["changes"][0]["source_spans"][0] = _span(
        "spell_rev/components/main_component.tpa",
        source,
        b"COPY ~arcane.spl~",
        b"COPY ~unowned.spl~",
    )

    with pytest.raises(GenerationError, match="uncovered executable source"):
        importlib.import_module("tools.sr_config.generate").render_component_zero_sources(
            tmp_path, Catalog.from_dict(raw)
        )


def test_generated_component_sources_match_the_catalog_and_setup_uses_entrypoint(
    production_compilation: tuple[Catalog, dict[Path, bytes]],
) -> None:
    _, expected = production_compilation
    for relative, payload in expected.items():
        path = ROOT / relative
        assert path.is_file(), f"missing generated component source {relative}"
        assert path.read_bytes() == payload

    setup = (ROOT / "spell_rev" / "setup-spell_rev.tp2").read_text(encoding="utf-8")
    component_zero = setup.split("DESIGNATED 0", 1)[1].split(
        "/*------Deva and Planetar Animations------*/", 1
    )[0]
    assert component_zero.count(
        "INCLUDE ~spell_rev/generated/component0/entry.tpa~"
    ) == 1
    assert "INCLUDE ~spell_rev/components/main_component.tpa~" not in component_zero
    assert "INCLUDE ~spell_rev/lib/ds.tph~" not in component_zero
    assert "INCLUDE ~spell_rev/lib/hidespl_patching.tph~" not in component_zero


def test_readme_directs_players_to_the_config_instead_of_editing_the_installer() -> None:
    readme = (ROOT / "spell_rev" / "readme-spell_rev.html").read_text(
        encoding="iso-8859-1"
    )

    assert "open the file <strong>spell_rev/setup-spell_rev.tp2</strong>" not in readme
    assert "<strong>spell_rev/settings.ini</strong>" in readme
    assert "sr_wizard_oracle = 0" in readme
    assert "<code>-1</code>" in readme


def test_every_generated_component_source_parse_checks_under_weidu_249(
    production_compilation: tuple[Catalog, dict[Path, bytes]], tmp_path: Path
) -> None:
    _, outputs = production_compilation
    for relative, payload in outputs.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        process = parse_check("TPA", path)
        assert process.returncode == 0, f"{relative}\n{transcript(process)}"
