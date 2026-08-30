from __future__ import annotations

import re
import struct
from collections import Counter
from pathlib import Path

import pytest

from tests.ie_formats import (
    EFF_V2_SIZE,
    SPL_ABILITY_SIZE,
    SPL_EFFECT_SIZE,
    SPL_HEADER_SIZE,
)
from tools.sr_config.catalog import Catalog, load_catalog
from tools.sr_config.coverage import audit_catalog_coverage
from tools.sr_config.resources import (
    ResourceError,
    build_resource_index,
    scan_package_resources,
    scan_resource_edges,
)
from tools.sr_config.source import resolve_span_offsets


ROOT = Path(__file__).resolve().parents[1]
DEPENDENCY_AUDIT = ROOT / "docs" / "spell-revisions-dependency-audit.md"
ATOMIC_EVIDENCE_BEGIN = "<!-- BEGIN ATOMIC COMPOSITE EVIDENCE -->"
ATOMIC_EVIDENCE_END = "<!-- END ATOMIC COMPOSITE EVIDENCE -->"
SOFT_EVIDENCE_BEGIN = "<!-- BEGIN SOFT RELATION EVIDENCE -->"
SOFT_EVIDENCE_END = "<!-- END SOFT RELATION EVIDENCE -->"


def _marked_section(document: str, begin: str, end: str) -> str:
    assert document.count(begin) == 1, f"expected exactly one {begin!r} marker"
    assert document.count(end) == 1, f"expected exactly one {end!r} marker"
    before, remainder = document.split(begin, 1)
    section, after = remainder.split(end, 1)
    assert end not in before
    assert begin not in after
    return section


def _markdown_table(section: str, header: tuple[str, ...]) -> list[tuple[str, ...]]:
    lines = [line for line in section.splitlines() if line.startswith("|")]
    assert len(lines) >= 2, "expected a Markdown evidence table"
    rows = [
        tuple(cell.strip() for cell in line.removeprefix("|").removesuffix("|").split("|"))
        for line in lines
    ]
    assert rows[0] == header
    assert rows[1] == tuple("---" for _ in header)
    assert all(len(row) == len(header) for row in rows[2:])
    return rows[2:]


def _code_cell(cell: str) -> str:
    assert cell.startswith("`") and cell.endswith("`")
    return cell[1:-1]


def _source_span_evidence(span) -> str:
    resolved = resolve_span_offsets(ROOT, span)
    start_line = resolved.source[: resolved.start].count(b"\n") + 1
    final_byte = max(resolved.start, resolved.end - 1)
    end_line = resolved.source[:final_byte].count(b"\n") + 1
    return (
        f"`{span.path}:lines {start_line}-{end_line} "
        f"[sha256:{span.sha256.lower()}]`"
    )


def test_dependency_audit_cites_every_atomic_composite_source_span() -> None:
    catalog = load_catalog(ROOT / "spell_rev/catalog/changes.json")
    composites = {
        change.id: change for change in catalog.changes if len(change.member_refs) > 1
    }
    document = DEPENDENCY_AUDIT.read_text(encoding="utf-8")
    rows = _markdown_table(
        _marked_section(document, ATOMIC_EVIDENCE_BEGIN, ATOMIC_EVIDENCE_END),
        ("Public choice", "Catalog members", "Source evidence"),
    )
    identifiers = [_code_cell(row[0]) for row in rows]

    assert Counter(identifiers) == Counter({identifier: 1 for identifier in composites})
    for row in rows:
        identifier = _code_cell(row[0])
        assert tuple(re.findall(r"`([^`]+)`", row[1])) == tuple(
            member.source_spell for member in composites[identifier].member_refs
        )
        expected = "<br>".join(
            _source_span_evidence(span)
            for span in composites[identifier].source_spans
        )
        assert row[2] == expected


def test_dependency_audit_cites_every_soft_relation_exactly_once() -> None:
    catalog = load_catalog(ROOT / "spell_rev/catalog/changes.json")
    expected_pairs = {
        (change.id, dependency)
        for change in catalog.changes
        for dependency in change.soft_requires
    }
    document = DEPENDENCY_AUDIT.read_text(encoding="utf-8")
    rows = _markdown_table(
        _marked_section(document, SOFT_EVIDENCE_BEGIN, SOFT_EVIDENCE_END),
        (
            "From",
            "To",
            "Physical edge count",
            "Evidence direction",
            "Representative source anchor",
        ),
    )
    parsed: list[tuple[tuple[str, str], int, str, str, int, str]] = []
    anchor_pattern = re.compile(
        r"^(?P<path>spell_rev/.+):(?P<offset>0x[0-9a-f]+):(?P<field>.+)$"
    )
    reverse_family_pair = (
        "divine.regenerate_light_wounds",
        "divine.mass_regenerate",
    )
    for source_cell, target_cell, count_cell, direction_cell, anchor_cell in rows:
        pair = (_code_cell(source_cell), _code_cell(target_cell))
        assert count_cell.isdecimal() and int(count_cell) > 0
        expected_direction = (
            "reverse-family" if pair == reverse_family_pair else "direct"
        )
        assert _code_cell(direction_cell) == expected_direction
        anchor = _code_cell(anchor_cell)
        match = anchor_pattern.fullmatch(anchor)
        assert match is not None, f"invalid binary source anchor for {pair}: {anchor!r}"
        parsed.append(
            (
                pair,
                int(count_cell),
                expected_direction,
                match.group("path"),
                int(match.group("offset"), 16),
                match.group("field"),
            )
        )

    assert Counter(item[0] for item in parsed) == Counter(
        {pair: 1 for pair in expected_pairs}
    )

    resource_index = build_resource_index(ROOT)
    change_resources = {
        resource.path.casefold(): (resource.path, change.id)
        for change in catalog.changes
        for resource in change.resources
    }
    reclassified_runtime_helpers = {
        "shared.contagion_delivery_spell",
        "shared.polymorph_squirrel_item",
        "shared.true_seeing_detection_spell",
    }
    infrastructure_resources = {
        resource.path.casefold(): (resource.path, infrastructure.consumers)
        for infrastructure in catalog.infrastructure
        if infrastructure.id in reclassified_runtime_helpers
        for resource in infrastructure.resources
    }
    assert {
        infrastructure.id
        for infrastructure in catalog.infrastructure
        if infrastructure.id in reclassified_runtime_helpers
        and infrastructure.activation == "consumer_selected"
    } == reclassified_runtime_helpers

    def target_choices(candidate: str) -> set[str]:
        key = candidate.casefold()
        if key in change_resources:
            return {change_resources[key][1]}
        if key in infrastructure_resources:
            return set(infrastructure_resources[key][1])
        return set()

    scanned: dict[str, tuple] = {}
    physical_counts: Counter[tuple[str, str]] = Counter()
    for path_key, (source_relative, source_owner) in change_resources.items():
        if Path(source_relative).suffix.casefold() not in {
            ".cre",
            ".eff",
            ".itm",
            ".spl",
        }:
            continue
        source_path = ROOT / source_relative
        if not source_path.is_file():
            continue
        edges = scan_resource_edges(
            source_path,
            package_root=ROOT,
            resource_index=resource_index,
        )
        scanned[path_key] = edges
        for edge in edges:
            target_owners = set().union(
                *(target_choices(candidate) for candidate in edge.local_candidates)
            )
            for target_owner in target_owners:
                if target_owner == source_owner:
                    continue
                physical_counts[(source_owner, target_owner)] += 1

    for pair, edge_count, direction, path, offset, field in parsed:
        source_path = ROOT / path
        assert source_path.is_file(), f"missing tracked source for {pair}: {path}"
        matching_edges = tuple(
            edge
            for edge in scanned[path.casefold()]
            if (edge.offset, edge.field) == (offset, field)
        )
        assert len(matching_edges) == 1, (
            f"binary source anchor for {pair} is not present: "
            f"{path}:0x{offset:x}:{field}"
        )
        physical_pair = pair if direction == "direct" else (pair[1], pair[0])
        assert change_resources[path.casefold()][1] == physical_pair[0]
        assert physical_pair[1] in set().union(
            *(
                target_choices(candidate)
                for candidate in matching_edges[0].local_candidates
            )
        )
        assert edge_count == physical_counts[physical_pair], (
            physical_pair,
            edge_count,
            physical_counts[physical_pair],
        )


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<H", data, offset, value)


def _put_u32(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<I", data, offset, value)


def _put_resref(data: bytearray, offset: int, value: str) -> None:
    encoded = value.encode("ascii")
    assert len(encoded) <= 8
    data[offset : offset + 8] = encoded.ljust(8, b"\0")


def _make_spl(effect_resources: tuple[tuple[int, str], ...] = ((146, "ChildSpl"),)) -> bytes:
    ability_offset = SPL_HEADER_SIZE
    effect_offset = ability_offset + SPL_ABILITY_SIZE
    data = bytearray(effect_offset + len(effect_resources) * SPL_EFFECT_SIZE)
    data[:8] = b"SPL V1  "
    _put_resref(data, 0x10, "DoneSnd")
    _put_resref(data, 0x3A, "BookIcon")
    _put_resref(data, 0x44, "GroundIc")
    _put_resref(data, 0x58, "DescIcon")
    _put_u32(data, 0x64, ability_offset)
    _put_u16(data, 0x68, 1)
    _put_u32(data, 0x6A, effect_offset)
    _put_u16(data, 0x6E, 0)
    _put_u16(data, 0x70, 0)
    _put_resref(data, ability_offset + 0x04, "MemIcon")
    _put_u16(data, ability_offset + 0x1E, len(effect_resources))
    _put_u16(data, ability_offset + 0x20, 0)
    for index, (opcode, target) in enumerate(effect_resources):
        offset = effect_offset + index * SPL_EFFECT_SIZE
        _put_u16(data, offset, opcode)
        _put_resref(data, offset + 0x14, target)
    return bytes(data)


def _make_itm() -> bytes:
    ability_offset = 0x72
    effect_offset = ability_offset + 0x38
    data = bytearray(effect_offset + 2 * 0x30)
    data[:8] = b"ITM V1  "
    _put_resref(data, 0x10, "Replace")
    _put_resref(data, 0x3A, "InvIcon")
    _put_resref(data, 0x44, "Ground")
    _put_resref(data, 0x58, "Desc")
    _put_u32(data, 0x64, ability_offset)
    _put_u16(data, 0x68, 1)
    _put_u32(data, 0x6A, effect_offset)
    _put_u16(data, 0x6E, 1)
    _put_u16(data, 0x70, 1)
    _put_resref(data, ability_offset + 0x04, "UseIcon")
    _put_u16(data, ability_offset + 0x1E, 1)
    _put_u16(data, ability_offset + 0x20, 0)
    _put_u16(data, effect_offset, 177)
    _put_resref(data, effect_offset + 0x14, "Ability")
    _put_u16(data, effect_offset + 0x30, 272)
    _put_resref(data, effect_offset + 0x30 + 0x14, "Equipped")
    return bytes(data)


def _make_eff(
    secondary_preamble: bytes = b"EFF V2.0",
    *,
    opcode: int = 326,
    parameter1: int = 0,
    parameter2: int = 0,
    parent_type: int = 1,
) -> bytes:
    assert len(secondary_preamble) == 8
    data = bytearray(EFF_V2_SIZE)
    data[:8] = b"EFF V2.0"
    data[8:16] = secondary_preamble
    _put_u32(data, 0x10, opcode)
    _put_u32(data, 0x1C, parameter1)
    _put_u32(data, 0x20, parameter2)
    _put_resref(data, 0x30, "Primary")
    _put_resref(data, 0x70, "Visual")
    _put_resref(data, 0x78, "Tertiary")
    _put_u32(data, 0x90, parent_type)
    _put_resref(data, 0x94, "Parent")
    return bytes(data)


def _make_cre() -> bytes:
    known_offset = 0x2D4
    memorization_offset = known_offset + 0x0C
    memorized_offset = memorization_offset + 0x10
    items_offset = memorized_offset + 0x0C
    effects_offset = items_offset + 0x14
    slots_offset = effects_offset + 0x108
    data = bytearray(slots_offset + 0x50)
    data[:8] = b"CRE V1.0"
    data[0x33] = 1
    _put_resref(data, 0x34, "SmallPor")
    _put_resref(data, 0x3C, "LargePor")
    for offset, value in (
        (0x248, "Override"),
        (0x250, "ClassScr"),
        (0x258, "RaceScr"),
        (0x260, "General"),
        (0x268, "Default"),
        (0x2CC, "Dialog"),
    ):
        _put_resref(data, offset, value)
    for field_offset, value in (
        (0x2A0, known_offset),
        (0x2A4, 1),
        (0x2A8, memorization_offset),
        (0x2AC, 1),
        (0x2B0, memorized_offset),
        (0x2B4, 1),
        (0x2B8, slots_offset),
        (0x2BC, items_offset),
        (0x2C0, 1),
        (0x2C4, effects_offset),
        (0x2C8, 1),
    ):
        _put_u32(data, field_offset, value)
    _put_resref(data, known_offset, "KnownSpl")
    _put_resref(data, memorized_offset, "MemoSpl")
    _put_resref(data, items_offset, "ItemRef")
    _put_u32(data, effects_offset + 0x08, 232)
    _put_resref(data, effects_offset + 0x28, "EffSpell")
    _put_resref(data, effects_offset + 0x68, "EffVvc")
    _put_resref(data, effects_offset + 0x70, "EffThird")
    _put_resref(data, effects_offset + 0x8C, "EfParent")
    return bytes(data)


def _edge(edges, field: str):
    matches = [edge for edge in edges if edge.field == field]
    assert len(matches) == 1, (field, matches)
    return matches[0]


def test_spl_v1_edges_include_icons_and_effect_opcode_provenance(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    source = package / "source.spl"
    source.write_bytes(_make_spl())
    (package / "CHILDSPL.spl").write_bytes(b"")
    index = build_resource_index(package)

    edges = scan_resource_edges(source, package_root=package, resource_index=index)

    assert _edge(edges, "header.spellbook_icon").target == "BookIcon"
    assert _edge(edges, "ability[0].icon").offset == 0x72 + 0x04
    effect = _edge(edges, "ability[0].effect[0].resource")
    assert (effect.target, effect.opcode, effect.offset) == (
        "ChildSpl",
        146,
        0x72 + 0x28 + 0x14,
    )
    assert effect.classification == "local"
    assert effect.local_candidates == ("CHILDSPL.spl",)


def test_itm_v1_edges_cover_header_ability_and_equipped_effects(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sample.itm"
    path.write_bytes(_make_itm())

    edges = scan_resource_edges(path)

    assert _edge(edges, "header.replacement_item").target == "Replace"
    assert _edge(edges, "header.inventory_icon").offset == 0x3A
    assert _edge(edges, "ability[0].icon").target == "UseIcon"
    assert _edge(edges, "ability[0].effect[0].resource").opcode == 177
    equipped = _edge(edges, "equipped_effect[0].resource")
    assert (equipped.target, equipped.opcode) == ("Equipped", 272)


def test_opcode_177_payload_matches_only_eff_candidates(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    source = package / "source.spl"
    source.write_bytes(_make_spl(((177, "SPWI118C"),)))
    (package / "SPWI118C.eff").write_bytes(b"")
    (package / "spwi118c.SPL").write_bytes(b"")

    payload = _edge(
        scan_resource_edges(source, package_root=package),
        "ability[0].effect[0].resource",
    )

    assert payload.semantics == "resource"
    assert payload.expected_types == ("EFF",)
    assert payload.classification == "local"
    assert payload.local_candidates == ("SPWI118C.eff",)


@pytest.mark.parametrize(
    ("opcode", "expected_types"),
    [
        (67, ("CRE",)),
        (82, ("BCS",)),
        (111, ("ITM",)),
        (112, ("ITM",)),
        (122, ("ITM",)),
        (135, ("CRE",)),
        (146, ("SPL",)),
        (147, ("SPL",)),
        (148, ("SPL",)),
        (171, ("SPL",)),
        (172, ("SPL",)),
        (174, ("WAV",)),
        (177, ("EFF",)),
        (201, ("SPL",)),
        (206, ("SPL",)),
        (214, ("2DA",)),
        (215, ("BAM", "VVC")),
        (232, ("SPL",)),
        (248, ("EFF",)),
        (251, ("SPL",)),
        (255, ("ITM",)),
        (296, ("BAM", "VVC")),
    ],
)
def test_documented_primary_effect_resource_types(
    tmp_path: Path, opcode: int, expected_types: tuple[str, ...]
) -> None:
    path = tmp_path / "typed.spl"
    path.write_bytes(_make_spl(((opcode, "Target"),)))

    payload = _edge(
        scan_resource_edges(path), "ability[0].effect[0].resource"
    )

    assert payload.semantics == "resource"
    assert payload.expected_types == expected_types


@pytest.mark.parametrize(
    ("opcode", "parameter1", "field", "expected_types"),
    [
        (67, 0, "effect.resource2", ("VVC", "BAM")),
        (67, 0, "effect.resource3", ("VVC", "BAM")),
        (112, 2, "effect.resource2", ("WAV",)),
        (122, 0, "effect.resource2", ("ITM",)),
        (122, 0, "effect.resource3", ("ITM",)),
    ],
)
def test_documented_secondary_effect_resource_types(
    tmp_path: Path,
    opcode: int,
    parameter1: int,
    field: str,
    expected_types: tuple[str, ...],
) -> None:
    path = tmp_path / "typed.eff"
    path.write_bytes(_make_eff(opcode=opcode, parameter1=parameter1))

    payload = _edge(scan_resource_edges(path), field)

    assert payload.semantics == "resource"
    assert payload.expected_types == expected_types


@pytest.mark.parametrize(
    ("opcode", "parameter1", "parameter2", "field"),
    [
        (112, 1, 0, "effect.resource2"),
        (214, 0, 1, "effect.resource"),
        (214, 0, 2, "effect.resource"),
    ],
)
def test_conditionally_ignored_effect_payloads_are_non_resources(
    tmp_path: Path,
    opcode: int,
    parameter1: int,
    parameter2: int,
    field: str,
) -> None:
    path = tmp_path / "ignored.eff"
    path.write_bytes(
        _make_eff(
            opcode=opcode,
            parameter1=parameter1,
            parameter2=parameter2,
        )
    )

    payload = _edge(scan_resource_edges(path), field)

    assert payload.semantics == "non_resource"
    assert payload.expected_types == ()
    assert payload.classification is None


@pytest.mark.parametrize(
    ("opcode", "target"),
    [
        (258, "ACTKEY"),
        (265, "GLOBNAME"),
        (267, "STALE"),
        (309, "dvgldust"),
    ],
)
def test_documented_non_resource_effect_payloads_remain_visible_without_edges(
    tmp_path: Path, opcode: int, target: str
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    source = package / "source.spl"
    source.write_bytes(_make_spl(((opcode, target),)))
    (package / f"{target}.spl").write_bytes(b"")

    payload = _edge(
        scan_resource_edges(source, package_root=package),
        "ability[0].effect[0].resource",
    )

    assert (payload.target, payload.opcode) == (target, opcode)
    assert payload.semantics == "non_resource"
    assert payload.expected_types == ()
    assert payload.classification is None
    assert payload.local_candidates == ()


def test_unknown_effect_payload_remains_visible_without_dependency_classification(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    source = package / "source.spl"
    source.write_bytes(_make_spl(((999, "Mystery"),)))
    (package / "Mystery.spl").write_bytes(b"")

    payload = _edge(
        scan_resource_edges(source, package_root=package),
        "ability[0].effect[0].resource",
    )

    assert payload.semantics == "unknown"
    assert payload.expected_types == ()
    assert payload.classification is None
    assert payload.local_candidates == ()


@pytest.mark.parametrize("opcode", [265, 309])
def test_concatenated_variable_payload_fields_are_all_non_resources(
    tmp_path: Path, opcode: int
) -> None:
    path = tmp_path / "variable.eff"
    path.write_bytes(_make_eff(opcode=opcode))

    edges = scan_resource_edges(path)

    for field in ("effect.resource", "effect.resource2", "effect.resource3"):
        payload = _edge(edges, field)
        assert payload.semantics == "non_resource"
        assert payload.expected_types == ()
        assert payload.classification is None


def test_itm_zero_ability_offset_is_independent_from_effect_table(
    tmp_path: Path,
) -> None:
    effect_offset = 0x72
    data = bytearray(effect_offset + 3 * 0x30)
    data[:8] = b"ITM V1  "
    _put_u32(data, 0x64, len(data))
    _put_u16(data, 0x68, 0)
    _put_u32(data, 0x6A, effect_offset)
    _put_u16(data, 0x6E, 0)
    _put_u16(data, 0x70, 3)
    for index, target in enumerate(("First", "Second", "Third")):
        effect = effect_offset + index * 0x30
        _put_u16(data, effect, 206)
        _put_resref(data, effect + 0x14, target)
    path = tmp_path / "zero-ability.itm"
    path.write_bytes(data)

    edges = scan_resource_edges(path)

    assert [edge.target for edge in edges] == ["First", "Second", "Third"]


def test_eff_v2_edges_cover_all_resource_fields(tmp_path: Path) -> None:
    path = tmp_path / "sample.eff"
    path.write_bytes(_make_eff())

    edges = scan_resource_edges(path)

    assert [edge.field for edge in edges] == [
        "effect.resource",
        "effect.resource2",
        "effect.resource3",
        "effect.parent_resource",
    ]
    assert [edge.offset for edge in edges] == [0x30, 0x70, 0x78, 0x94]
    assert {edge.opcode for edge in edges} == {326}
    parent = _edge(edges, "effect.parent_resource")
    assert parent.semantics == "resource"
    assert parent.expected_types == ("SPL",)


@pytest.mark.parametrize(
    ("parent_type", "expected_type", "wrong_type"),
    [(1, "SPL", "ITM"), (2, "ITM", "SPL")],
)
def test_eff_parent_resource_uses_declared_parent_type(
    tmp_path: Path, parent_type: int, expected_type: str, wrong_type: str
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    source = package / "source.eff"
    source.write_bytes(_make_eff(parent_type=parent_type))
    (package / f"Parent.{expected_type.lower()}").write_bytes(b"")
    (package / f"parent.{wrong_type.lower()}").write_bytes(b"")

    parent = _edge(
        scan_resource_edges(source, package_root=package),
        "effect.parent_resource",
    )

    assert parent.semantics == "resource"
    assert parent.expected_types == (expected_type,)
    assert parent.classification == "local"
    assert parent.local_candidates == (f"Parent.{expected_type.lower()}",)


@pytest.mark.parametrize(
    "secondary_preamble",
    [b"\0" * 8, b" " * 8, b"EFF V2.0"],
)
def test_eff_v2_accepts_known_secondary_preamble_variants(
    tmp_path: Path, secondary_preamble: bytes
) -> None:
    path = tmp_path / "variant.eff"
    path.write_bytes(_make_eff(secondary_preamble))

    assert scan_resource_edges(path)


def test_eff_v2_rejects_unknown_secondary_preamble_with_context(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bad-secondary.eff"
    path.write_bytes(_make_eff(b"BADBODY!"))

    with pytest.raises(ResourceError) as error:
        scan_resource_edges(path)

    message = str(error.value)
    assert path.as_posix() in message
    assert "secondary preamble" in message
    assert "0x8" in message
    assert "BADBODY!" in message


def test_cre_v1_edges_cover_spells_items_scripts_portraits_and_effects(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sample.cre"
    path.write_bytes(_make_cre())

    edges = scan_resource_edges(path)

    expected = {
        "header.small_portrait": "SmallPor",
        "header.large_portrait": "LargePor",
        "header.override_script": "Override",
        "header.class_script": "ClassScr",
        "header.race_script": "RaceScr",
        "header.general_script": "General",
        "header.default_script": "Default",
        "header.dialog": "Dialog",
        "known_spell[0]": "KnownSpl",
        "memorized_spell[0]": "MemoSpl",
        "item[0]": "ItemRef",
        "effect[0].resource": "EffSpell",
        "effect[0].resource2": "EffVvc",
        "effect[0].resource3": "EffThird",
        "effect[0].parent_resource": "EfParent",
    }
    assert {field: _edge(edges, field).target for field in expected} == expected
    assert _edge(edges, "effect[0].resource").opcode == 232


def test_local_classification_is_case_insensitive_and_filters_candidate_types(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    (package / "a").mkdir(parents=True)
    (package / "b").mkdir()
    source = package / "source.spl"
    source.write_bytes(_make_spl(((146, "mIxEd"),)))
    (package / "a/MIXED.SPL").write_bytes(b"")
    (package / "b/mixed.itm").write_bytes(b"")

    edges = scan_resource_edges(source, package_root=package)
    effect = _edge(edges, "ability[0].effect[0].resource")

    assert effect.target == "mIxEd"
    assert effect.expected_types == ("SPL",)
    assert effect.classification == "local"
    assert effect.local_candidates == ("a/MIXED.SPL",)
    assert _edge(edges, "header.spellbook_icon").classification == "external"


def test_fixed_icon_matches_only_same_type_candidates_in_stable_order(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    (package / "a").mkdir(parents=True)
    (package / "b").mkdir()
    (package / "c").mkdir()
    source = package / "source.spl"
    payload = bytearray(_make_spl(()))
    _put_resref(payload, 0x3A, "SPWI118C")
    source.write_bytes(payload)
    (package / "a/SPWI118C.bam").write_bytes(b"")
    (package / "b/spwi118c.BAM").write_bytes(b"")
    (package / "c/SPWI118C.spl").write_bytes(b"")

    icon = _edge(
        scan_resource_edges(source, package_root=package),
        "header.spellbook_icon",
    )

    assert icon.semantics == "resource"
    assert icon.expected_types == ("BAM",)
    assert icon.classification == "local"
    assert icon.local_candidates == (
        "a/SPWI118C.bam",
        "b/spwi118c.BAM",
    )


def test_cre_script_does_not_match_same_stem_cre_or_itm(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    source = package / "source.cre"
    source.write_bytes(_make_cre())
    (package / "Override.cre").write_bytes(b"")
    (package / "override.ITM").write_bytes(b"")

    script = _edge(
        scan_resource_edges(source, package_root=package),
        "header.override_script",
    )

    assert script.semantics == "resource"
    assert script.expected_types == ("BCS",)
    assert script.classification == "external"
    assert script.local_candidates == ()


def test_duplicate_edges_are_preserved_in_source_offset_order(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.spl"
    path.write_bytes(_make_spl(((146, "Same"), (146, "Same"))))

    edges = scan_resource_edges(path)
    duplicates = [edge for edge in edges if edge.target == "Same"]

    assert len(duplicates) == 2
    assert [edge.offset for edge in duplicates] == sorted(
        edge.offset for edge in duplicates
    )


@pytest.mark.parametrize(
    ("name", "payload", "message"),
    [
        ("bad.spl", b"BAD V1  " + bytes(0x70), "bad.spl.*signature"),
        ("bad.itm", b"ITM V1  " + bytes(12), "bad.itm.*header"),
        ("bad.eff", b"EFF V2.0" + bytes(8), "bad.eff.*size"),
        ("bad.cre", b"CRE V1.0" + bytes(12), "bad.cre.*header"),
    ],
)
def test_signature_version_and_header_bounds_are_checked(
    tmp_path: Path, name: str, payload: bytes, message: str
) -> None:
    path = tmp_path / name
    path.write_bytes(payload)

    with pytest.raises(ResourceError, match=message):
        scan_resource_edges(path)


@pytest.mark.parametrize("kind", ["spl", "itm", "cre"])
def test_bad_table_offsets_name_the_file_and_field(tmp_path: Path, kind: str) -> None:
    builders = {"spl": _make_spl, "itm": _make_itm, "cre": _make_cre}
    payload = bytearray(builders[kind]())
    fields = {"spl": 0x64, "itm": 0x6A, "cre": 0x2A0}
    _put_u32(payload, fields[kind], len(payload) + 1)
    path = tmp_path / f"bad.{kind}"
    path.write_bytes(payload)

    with pytest.raises(ResourceError) as error:
        scan_resource_edges(path)

    assert path.name in str(error.value)
    assert f"0x{fields[kind]:x}" in str(error.value).lower()


@pytest.mark.parametrize(
    ("items_count", "slot_index", "slot_value"),
    [
        (0, 0, 0),
        (1, 37, 1),
    ],
)
def test_cre_item_slots_reject_indices_outside_item_table(
    tmp_path: Path, items_count: int, slot_index: int, slot_value: int
) -> None:
    payload = bytearray(_make_cre())
    slots_offset = struct.unpack_from("<I", payload, 0x2B8)[0]
    _put_u32(payload, 0x2C0, items_count)
    _put_u16(payload, slots_offset + slot_index * 2, slot_value)
    path = tmp_path / "bad-slot.cre"
    path.write_bytes(payload)

    with pytest.raises(ResourceError) as error:
        scan_resource_edges(path)

    message = str(error.value)
    assert path.as_posix() in message
    assert f"slot[{slot_index}]" in message
    assert f"0x{slots_offset + slot_index * 2:x}" in message.lower()


def test_cre_non_item_slot_tail_words_are_not_item_indices(tmp_path: Path) -> None:
    payload = bytearray(_make_cre())
    slots_offset = struct.unpack_from("<I", payload, 0x2B8)[0]
    _put_u16(payload, slots_offset + 0x4C, 0x1234)
    _put_u16(payload, slots_offset + 0x4E, 0x5678)
    path = tmp_path / "slot-tail.cre"
    path.write_bytes(payload)

    assert scan_resource_edges(path)


def test_unsupported_or_missing_resource_paths_fail_with_context(tmp_path: Path) -> None:
    unsupported = tmp_path / "sample.bin"
    unsupported.write_bytes(b"data")

    with pytest.raises(ResourceError, match="sample.bin.*unsupported"):
        scan_resource_edges(unsupported)
    with pytest.raises(ResourceError, match="missing.spl"):
        scan_resource_edges(tmp_path / "missing.spl")


def test_package_root_and_resource_membership_are_checked(tmp_path: Path) -> None:
    missing = tmp_path / "missing-package"

    with pytest.raises(ResourceError, match="missing-package.*directory"):
        scan_package_resources(missing)

    package = tmp_path / "package"
    package.mkdir()
    source = tmp_path / "outside.spl"
    source.write_bytes(_make_spl())

    with pytest.raises(ResourceError, match="outside.spl.*outside package root"):
        scan_resource_edges(source, package_root=package)


def test_package_scan_never_silently_skips_a_malformed_resource(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "good.spl").write_bytes(_make_spl())
    (package / "bad.itm").write_bytes(b"ITM V1  ")

    with pytest.raises(ResourceError, match="bad.itm"):
        scan_package_resources(package)


def test_package_scan_inventories_every_supported_shipped_resource() -> None:
    package = ROOT / "spell_rev"
    expected = tuple(
        sorted(
            (
                path.relative_to(package).as_posix()
                for path in package.rglob("*")
                if path.is_file()
                and path.suffix.casefold() in {".spl", ".itm", ".eff", ".cre"}
            ),
            key=lambda value: (value.casefold(), value),
        )
    )

    scanned = scan_package_resources(package)

    assert tuple(resource.path for resource in scanned) == expected


def test_binary_edges_include_dynamic_spell_reference() -> None:
    path = ROOT / "spell_rev/sppr2##/sppr210.spl"

    edges = scan_resource_edges(path, package_root=ROOT / "spell_rev")

    matches = [edge for edge in edges if edge.target.upper() == "SPWI225"]
    assert matches
    assert all(edge.opcode == 206 for edge in matches)
    assert all(edge.field.endswith(".resource") for edge in matches)
    assert all(edge.expected_types == ("SPL",) for edge in matches)
    assert all(edge.classification == "local" for edge in matches)


@pytest.mark.parametrize(
    ("relative", "field", "target", "offset", "opcode"),
    [
        (
            "shared/dvbanish.spl",
            "ability[0].effect[0].resource",
            "SPPOWRRD",
            0xAE,
            215,
        ),
        (
            "sppr1##/batsu.itm",
            "equipped_effect[0].resource",
            "DVRSWARM",
            0xBE,
            232,
        ),
        ("shared/dvbanish.eff", "effect.resource", "DVBANISH", 0x30, 146),
        (
            "sppr7##/devaevil.cre",
            "header.override_script",
            "DVDEVAE",
            0x248,
            None,
        ),
        (
            "spwi7##/dvdjinni.cre",
            "effect[0].parent_resource",
            "MISC9Y",
            0x578,
            206,
        ),
    ],
)
def test_representative_shipped_edges_have_exact_provenance(
    relative: str,
    field: str,
    target: str,
    offset: int,
    opcode: int | None,
) -> None:
    package = ROOT / "spell_rev"

    edge = _edge(
        scan_resource_edges(package / relative, package_root=package), field
    )

    assert (edge.target, edge.offset, edge.opcode) == (target, offset, opcode)


def _coverage_change_record(
    change_id: str,
    resources: list[str],
    *,
    atomic_group: str | None = None,
    requires: list[str] | None = None,
    soft_requires: list[str] | None = None,
    processors: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": change_id,
        "setting": f"sr_{change_id}",
        "display_name": change_id,
        "default": -1,
        "group": "global",
        "component": 0,
        "games": ["all"],
        "name_ref": "@1",
        "name_fallback": None,
        "description_ref": "@2",
        "member_refs": [],
        "source_spans": [],
        "resources": [{"path": path, "kind": "asset"} for path in resources],
        "atomic_group": atomic_group,
        "requires": requires or [],
        "conflicts": [],
        "soft_requires": soft_requires or [],
        "processors": processors or [],
        "documentation_only_reason": "binary-only coverage fixture",
    }


def _write_binary_coverage_fixture(
    root: Path,
    effects: tuple[tuple[int, str], ...],
) -> Catalog:
    component = root / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_text("", encoding="utf-8")
    language = root / "spell_rev/languages/english"
    language.mkdir(parents=True)
    (language / "arcane.tra").write_text(
        "@1=~Fixture name~\n@2=~Fixture description~\n", encoding="utf-8"
    )
    (language / "divine.tra").write_text("", encoding="utf-8")
    (language / "setup.tra").write_text("", encoding="utf-8")
    assets = root / "spell_rev/assets"
    assets.mkdir()
    (assets / "source.spl").write_bytes(_make_spl(effects))
    for target in ("same", "atomic", "hard", "soft", "shared", "mystery"):
        (assets / f"{target}.spl").write_bytes(_make_spl(()))

    return Catalog.from_dict(
        {
            "schema_version": 1,
            "upstream": {
                "tag": "v4.21",
                "commit": "af1dedb6d211f86ad7a321d4080e46c748e8abac",
            },
            "migration": {
                "complete": False,
                "installer_source": "spell_rev/components/main_component.tpa",
            },
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
                _coverage_change_record(
                    "source",
                    ["spell_rev/assets/source.spl", "spell_rev/assets/same.spl"],
                    atomic_group="family",
                    requires=["hard"],
                    soft_requires=["soft"],
                    processors=["shared_processor"],
                ),
                _coverage_change_record(
                    "atomic",
                    ["spell_rev/assets/atomic.spl"],
                    atomic_group="family",
                ),
                _coverage_change_record("hard", ["spell_rev/assets/hard.spl"]),
                _coverage_change_record("soft", ["spell_rev/assets/soft.spl"]),
            ],
            "infrastructure": [
                {
                    "id": "shared_processor",
                    "category": "derived",
                    "activation": "consumer_selected",
                    "infrastructure_requires": [],
                    "source_spans": [],
                    "resources": [
                        {"path": "spell_rev/assets/shared.spl", "kind": "asset"}
                    ],
                    "consumers": ["source"],
                }
            ],
            "component_zero_closure_roots": [],
            "dormant_resources": [],
            "deferred_source_scopes": [],
            "binary_edge_resolutions": [],
        }
    )


def test_catalog_coverage_derives_every_binary_reference_classification(
    tmp_path: Path,
) -> None:
    catalog = _write_binary_coverage_fixture(
        tmp_path,
        (
            (146, "SAME"),
            (146, "ATOMIC"),
            (146, "HARD"),
            (206, "SOFT"),
            (146, "SHARED"),
            (146, "EXTERN"),
        ),
    )

    result = audit_catalog_coverage(tmp_path, catalog)
    classifications = {
        edge.target.casefold(): edge.classification
        for edge in result.binary_edges
        if edge.target.casefold()
        in {"same", "atomic", "hard", "soft", "shared", "extern"}
    }

    assert classifications == {
        "same": "owned",
        "atomic": "atomic",
        "hard": "hard",
        "soft": "soft",
        "shared": "shared",
        "extern": "external",
    }
    assert result.ok


def test_soft_relation_cannot_supply_required_runtime_payload_but_shared_infrastructure_can(
    tmp_path: Path,
) -> None:
    unsafe = audit_catalog_coverage(
        tmp_path / "unsafe",
        _write_binary_coverage_fixture(
            tmp_path / "unsafe", ((146, "SOFT"),)
        ),
    )

    assert [issue.code for issue in unsafe.issues] == [
        "unsafe_soft_runtime_resource"
    ]
    assert next(
        edge for edge in unsafe.binary_edges if edge.target == "SOFT"
    ).classification is None

    shared_root = tmp_path / "shared"
    shared = audit_catalog_coverage(
        shared_root,
        _write_binary_coverage_fixture(shared_root, ((146, "SHARED"),)),
    )

    assert shared.ok
    assert next(
        edge for edge in shared.binary_edges if edge.target == "SHARED"
    ).classification == "shared"


def test_catalog_coverage_never_hides_unknown_binary_payloads(
    tmp_path: Path,
) -> None:
    catalog = _write_binary_coverage_fixture(tmp_path, ((999, "MYSTERY"),))

    result = audit_catalog_coverage(tmp_path, catalog)

    assert [issue.code for issue in result.issues] == ["unknown_binary_edge"]
    mystery = next(edge for edge in result.binary_edges if edge.target == "MYSTERY")
    assert mystery.classification is None
