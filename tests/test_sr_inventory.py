from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import pytest

from tools.sr_config.catalog import SourceSpan
from tools.sr_config.inventory import (
    build_inventory_report,
    inventory,
    inventory_tree,
    report_json_bytes,
)
from tools.sr_config.source import SourceError, resolve_span


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/sr_config/main_component_sample.tpa"


def _executable_nodes():
    return tuple(node for node in inventory(FIXTURE) if node.kind != "trivia")


def test_inventory_reconstructs_input_byte_exact() -> None:
    source = FIXTURE.read_bytes()

    assert b"".join(node.raw for node in inventory(FIXTURE)) == source


def test_inventory_classifies_top_level_statements_and_nested_bodies() -> None:
    nodes = _executable_nodes()

    assert [(node.kind, node.command) for node in nodes] == [
        ("executable", "COPY"),
        ("executable", "COPY_EXISTING"),
        ("executable", "ADD_SPELL"),
        ("executable", "INCLUDE"),
        ("executable", "LAF"),
        ("executable", "LAM"),
        ("executable", "ACTION_IF"),
        ("unknown", "MYSTERY_STATEMENT"),
    ]
    assert b"LPF ALTER_EFFECT" in nodes[0].raw
    assert b"WRITE_BYTE 0x27 1" in nodes[1].raw
    assert b"COPY ~spell_rev/conditional.spl~" in nodes[6].raw


def test_inventory_records_stable_location_section_and_resource_operands() -> None:
    nodes = _executable_nodes()
    copy, copy_existing, add_spell, include, laf, lam, action_if, unknown = nodes

    assert copy.path == FIXTURE.name
    assert copy.line == 6
    assert copy.section_comments == ("Arcane level one",)
    assert [(operand.role, operand.value) for operand in copy.resource_operands] == [
        ("source", "spell_rev/a.spl"),
        ("destination", "override/a.spl"),
        ("source", "spell_rev/b.spl"),
        ("destination", "override/b.spl"),
    ]
    assert "ignored.spl" not in tuple(
        operand.value for operand in copy.resource_operands
    )
    assert [(operand.role, operand.value) for operand in copy_existing.resource_operands] == [
        ("source", "SpWi123.SPL"),
        ("destination", "override"),
    ]
    assert add_spell.line == 25
    assert [(operand.role, operand.value) for operand in add_spell.resource_operands] == [
        ("source", "spell_rev/new.spl"),
        ("symbol", "WIZARD_NEW_SPELL"),
    ]
    assert [(operand.role, operand.value) for operand in include.resource_operands] == [
        ("include", "spell_rev/lib/library.tph")
    ]
    assert [(operand.role, operand.value) for operand in laf.resource_operands] == [
        ("argument", "SPWI225.SPL")
    ]
    assert lam.resource_operands == ()
    assert [(operand.role, operand.value) for operand in action_if.resource_operands] == [
        ("condition", "spwi225.spl")
    ]
    assert unknown.line == 39
    assert [(operand.role, operand.value) for operand in unknown.resource_operands] == [
        ("argument", "odd.res")
    ]


def test_inventory_path_is_relative_to_explicit_root() -> None:
    nodes = inventory(FIXTURE, root=ROOT)

    assert {node.path for node in nodes} == {
        "tests/fixtures/sr_config/main_component_sample.tpa"
    }


def test_inventory_keeps_end_delimited_patch_calls_inside_their_owner(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nested.tpa"
    path.write_text(
        "ACTION_IF (1) BEGIN\n"
        "  COPY ~a.spl~ ~override~\n"
        "    LPF ADD_SPELL_EFFECT\n"
        "      INT_VAR\n"
        "        opcode = 206\n"
        "      STR_VAR\n"
        "        resource = ~SPWI225~\n"
        "    END\n"
        "END\n"
        "MYSTERY_STATEMENT ~odd.res~\n",
        encoding="utf-8",
    )

    nodes = tuple(node for node in inventory(path) if node.kind != "trivia")

    assert [(node.kind, node.command) for node in nodes] == [
        ("executable", "ACTION_IF"),
        ("unknown", "MYSTERY_STATEMENT"),
    ]
    assert b"opcode = 206" in nodes[0].raw
    assert b"resource = ~SPWI225~" in nodes[0].raw
    assert nodes[0].raw.replace(b"\r\n", b"\n").endswith(b"    END\nEND\n")


def test_inventory_keeps_patch_fields_and_modifiers_inside_copy_pipeline(
    tmp_path: Path,
) -> None:
    path = tmp_path / "copy.tpa"
    path.write_text(
        "COPY_EXISTING ~a.spl~ ~override~\n"
        "  LPF ADD_SPELL_EFFECT\n"
        "    INT_VAR\n"
        "      opcode = 206\n"
        "    STR_VAR\n"
        "      resource = ~SPWI225~\n"
        "  END\n"
        "BUT_ONLY\n"
        "MYSTERY_STATEMENT ~odd.res~\n"
        "PRINT ~next action~\n",
        encoding="utf-8",
    )

    nodes = tuple(node for node in inventory(path) if node.kind != "trivia")

    assert [(node.kind, node.command) for node in nodes] == [
        ("executable", "COPY_EXISTING"),
        ("unknown", "MYSTERY_STATEMENT"),
        ("executable", "PRINT"),
    ]
    assert b"opcode = 206" in nodes[0].raw
    assert b"BUT_ONLY" in nodes[0].raw
    assert nodes[1].raw.strip().startswith(b"MYSTERY_STATEMENT")


def test_inventory_keeps_unless_modifier_with_append(tmp_path: Path) -> None:
    path = tmp_path / "append.tpa"
    path.write_text(
        "APPEND ~spell.ids~ ~1702 CLERIC_STALKER~\n"
        "  UNLESS ~^1702[ %TAB%]+CLERIC_STALKER\\b~\n"
        "PRINT ~next action~\n",
        encoding="utf-8",
    )

    nodes = tuple(node for node in inventory(path) if node.kind != "trivia")

    assert [(node.kind, node.command) for node in nodes] == [
        ("executable", "APPEND"),
        ("executable", "PRINT"),
    ]
    assert b"UNLESS" in nodes[0].raw


@pytest.mark.parametrize(
    "else_header",
    [
        "END ELSE\nBEGIN\n",
        "END ELSE ACTION_IF (2)\nBEGIN\n",
        "END ELSE PATCH_IF (2)\nBEGIN\n",
    ],
)
def test_inventory_keeps_split_else_headers_in_one_action_node(
    tmp_path: Path, else_header: str
) -> None:
    path = tmp_path / "split-else.tpa"
    path.write_text(
        "ACTION_IF (1) BEGIN\n"
        "  PRINT ~first branch~\n"
        f"{else_header}"
        "  PRINT ~else branch~\n"
        "END\n"
        "MYSTERY_STATEMENT ~after~\n",
        encoding="utf-8",
    )

    nodes = tuple(node for node in inventory(path) if node.kind != "trivia")

    assert [(node.kind, node.command) for node in nodes] == [
        ("executable", "ACTION_IF"),
        ("unknown", "MYSTERY_STATEMENT"),
    ]
    normalized = nodes[0].raw.replace(b"\r\n", b"\n")
    assert else_header.encode() in normalized
    assert normalized.endswith(b"  PRINT ~else branch~\nEND\n")


def test_inventory_closes_fully_inline_else_branch(tmp_path: Path) -> None:
    path = tmp_path / "inline-else.tpa"
    path.write_text(
        "ACTION_IF (1) BEGIN PRINT ~first~ END "
        "ELSE BEGIN PRINT ~second~ END\n"
        "MYSTERY_STATEMENT ~after~\n",
        encoding="utf-8",
    )

    nodes = tuple(node for node in inventory(path) if node.kind != "trivia")

    assert [(node.kind, node.command) for node in nodes] == [
        ("executable", "ACTION_IF"),
        ("unknown", "MYSTERY_STATEMENT"),
    ]


def test_patch_read_fallback_else_does_not_extend_action_block(
    tmp_path: Path,
) -> None:
    path = tmp_path / "patch-fallback-else.tpa"
    path.write_text(
        "ACTION_IF (1) BEGIN\n"
        "  OUTER_INNER_PATCH ~abc~ BEGIN\n"
        "    READ_BYTE 0 value ELSE 0 END END\n"
        "PRINT ~after action~\n",
        encoding="utf-8",
    )

    nodes = tuple(node for node in inventory(path) if node.kind != "trivia")

    assert [(node.kind, node.command) for node in nodes] == [
        ("executable", "ACTION_IF"),
        ("executable", "PRINT"),
    ]
    normalized = nodes[0].raw.replace(b"\r\n", b"\n")
    assert normalized.endswith(b"READ_BYTE 0 value ELSE 0 END END\n")
    assert b"".join(node.raw for node in inventory(path)) == path.read_bytes()


def test_unknown_action_forms_end_copy_pipeline_without_losing_text(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unknown-actions.tpa"
    path.write_text(
        "COPY ~a.spl~ ~override~\n"
        "  INNER_ACTION BEGIN\n"
        "    PRINT ~nested action~\n"
        "  END\n"
        "AT_UNINSTALL ~cleanup command~\n"
        "ACTION_READLN answer\n"
        "PRINT ~next known action~\n",
        encoding="utf-8",
    )

    nodes = tuple(node for node in inventory(path) if node.kind != "trivia")

    assert [(node.kind, node.command) for node in nodes] == [
        ("executable", "COPY"),
        ("unknown", "AT_UNINSTALL"),
        ("unknown", "ACTION_READLN"),
        ("executable", "PRINT"),
    ]
    assert b"INNER_ACTION BEGIN" in nodes[0].raw
    assert [(operand.role, operand.value) for operand in nodes[0].resource_operands] == [
        ("source", "a.spl"),
        ("destination", "override"),
    ]
    assert b"".join(node.raw for node in inventory(path)) == path.read_bytes()


def test_inventory_and_closure_support_multi_file_and_multiline_include(
    tmp_path: Path,
) -> None:
    (tmp_path / "spell_rev/components").mkdir(parents=True)
    (tmp_path / "spell_rev/lib").mkdir()
    main = tmp_path / "spell_rev/components/main_component.tpa"
    main.write_text(
        "INCLUDE ~spell_rev/lib/a.tph~ ~spell_rev/lib/b.tph~\n"
        "INCLUDE\n"
        "  ~spell_rev/lib/c.tph~\n"
        "PRINT ~done~\n",
        encoding="utf-8",
    )
    for name in ("a", "b", "c"):
        (tmp_path / f"spell_rev/lib/{name}.tph").write_text(
            f"PRINT ~{name}~\n", encoding="utf-8"
        )

    main_nodes = tuple(
        node for node in inventory(main, root=tmp_path) if node.kind != "trivia"
    )
    tree = inventory_tree(tmp_path)

    assert [(node.command, node.line) for node in main_nodes] == [
        ("INCLUDE", 1),
        ("INCLUDE", 2),
        ("PRINT", 4),
    ]
    assert [
        operand.value for operand in main_nodes[0].resource_operands
    ] == ["spell_rev/lib/a.tph", "spell_rev/lib/b.tph"]
    assert [
        operand.value for operand in main_nodes[1].resource_operands
    ] == ["spell_rev/lib/c.tph"]
    assert tuple(dict.fromkeys(node.path for node in tree)) == (
        "spell_rev/components/main_component.tpa",
        "spell_rev/lib/a.tph",
        "spell_rev/lib/b.tph",
        "spell_rev/lib/c.tph",
    )

    report = build_inventory_report(tmp_path)
    assert [
        (edge["line"], edge["operand"], edge["resolved"])
        for edge in report["include_edges"]
    ] == [
        (1, "spell_rev/lib/a.tph", "spell_rev/lib/a.tph"),
        (1, "spell_rev/lib/b.tph", "spell_rev/lib/b.tph"),
        (2, "spell_rev/lib/c.tph", "spell_rev/lib/c.tph"),
    ]


def test_shipped_copy_operands_include_bare_destination_and_exclude_patch_body() -> None:
    path = ROOT / "spell_rev/lib/dispelling_screen.tph"
    nodes = {
        node.line: node
        for node in inventory(path, root=ROOT)
        if node.kind != "trivia"
    }

    assert [
        (operand.role, operand.value) for operand in nodes[9].resource_operands
    ] == [("source", "msectype.2da"), ("destination", "override")]
    assert [
        (operand.role, operand.value) for operand in nodes[18].resource_operands
    ] == [("source", "k1#scre.spl"), ("destination", "override")]


def test_resolve_span_returns_original_bytes_and_hashes_lf_normalized_bytes(
    tmp_path: Path,
) -> None:
    source = b"preamble\r\n// A\r\nCOPY ~a.spl~ ~override~\r\n// B\r\ntail\r\n"
    path = tmp_path / "main.tpa"
    path.write_bytes(source)
    original_span = b"// A\r\nCOPY ~a.spl~ ~override~\r\n"
    normalized_span = b"// A\nCOPY ~a.spl~ ~override~\n"
    span = SourceSpan(
        path="main.tpa",
        start="// A",
        end="// B",
        sha256=hashlib.sha256(normalized_span).hexdigest(),
    )

    assert resolve_span(tmp_path, span) == original_span


def test_anchor_hash_rejects_upstream_drift(tmp_path: Path) -> None:
    path = tmp_path / "main.tpa"
    path.write_text("// A\nCOPY ~a.spl~ ~override~\n// B\n", encoding="utf-8")
    span = SourceSpan(path="main.tpa", start="// A", end="// B", sha256="0" * 64)

    with pytest.raises(SourceError, match="anchor hash changed"):
        resolve_span(tmp_path, span)


@pytest.mark.parametrize(
    ("source", "start", "end", "message"),
    [
        ("// B\n", "// A", "// B", "start anchor.*// A"),
        ("// A\n// A\n// B\n", "// A", "// B", "start anchor.*2 matches"),
        ("// A\n// B\n// B\n", "// A", "// B", "end anchor.*2 matches"),
        ("// B\n// A\n", "// A", "// B", "end anchor.*before start anchor"),
    ],
)
def test_resolve_span_rejects_missing_duplicate_or_reversed_anchors(
    tmp_path: Path,
    source: str,
    start: str,
    end: str,
    message: str,
) -> None:
    path = tmp_path / "main.tpa"
    path.write_text(source, encoding="utf-8")
    span = SourceSpan(path="main.tpa", start=start, end=end, sha256="0" * 64)

    with pytest.raises(SourceError, match=message) as error:
        resolve_span(tmp_path, span)

    assert "main.tpa" in str(error.value)


def test_resolve_span_names_an_unreadable_path(tmp_path: Path) -> None:
    span = SourceSpan(
        path="missing.tpa", start="// A", end="// B", sha256="0" * 64
    )

    with pytest.raises(SourceError, match="missing.tpa"):
        resolve_span(tmp_path, span)


def test_inventory_tree_follows_nested_includes_once_and_ignores_opaque_text(
    tmp_path: Path,
) -> None:
    (tmp_path / "spell_rev/components").mkdir(parents=True)
    (tmp_path / "spell_rev/lib").mkdir()
    main = tmp_path / "spell_rev/components/main_component.tpa"
    main.write_text(
        "INCLUDE ~spell_rev/lib/a.tph~\n"
        "ACTION_IF (1) BEGIN\n"
        "  INCLUDE \"%MOD_FOLDER%/lib/b.tph\"\n"
        "END\n"
        "INCLUDE ~%dynamic_library%/optional.tph~\n"
        "// INCLUDE ~spell_rev/lib/commented.tph~\n"
        "<<<<<<<< inline-source\n"
        "INCLUDE ~spell_rev/lib/inline.tph~\n"
        ">>>>>>>>\n",
        encoding="utf-8",
    )
    (tmp_path / "spell_rev/lib/a.tph").write_text(
        "INCLUDE ~spell_rev/lib/b.tph~\n", encoding="utf-8"
    )
    (tmp_path / "spell_rev/lib/b.tph").write_text(
        "PRINT ~loaded~\n", encoding="utf-8"
    )

    nodes = inventory_tree(tmp_path, "spell_rev/components/main_component.tpa")
    paths = tuple(dict.fromkeys(node.path for node in nodes))

    assert paths == (
        "spell_rev/components/main_component.tpa",
        "spell_rev/lib/a.tph",
        "spell_rev/lib/b.tph",
    )

    report = build_inventory_report(tmp_path)
    assert report["include_edges"] == [
        {
            "source": "spell_rev/components/main_component.tpa",
            "line": 1,
            "operand": "spell_rev/lib/a.tph",
            "resolved": "spell_rev/lib/a.tph",
            "status": "resolved",
        },
        {
            "source": "spell_rev/lib/a.tph",
            "line": 1,
            "operand": "spell_rev/lib/b.tph",
            "resolved": "spell_rev/lib/b.tph",
            "status": "resolved",
        },
        {
            "source": "spell_rev/components/main_component.tpa",
            "line": 3,
            "operand": "%MOD_FOLDER%/lib/b.tph",
            "resolved": "spell_rev/lib/b.tph",
            "status": "resolved",
        },
        {
            "source": "spell_rev/components/main_component.tpa",
            "line": 5,
            "operand": "%dynamic_library%/optional.tph",
            "resolved": None,
            "status": "dynamic",
        },
    ]


def test_real_component_zero_include_closure_is_stable() -> None:
    nodes = inventory_tree(ROOT, "spell_rev/components/main_component.tpa")

    assert tuple(dict.fromkeys(node.path for node in nodes)) == (
        "spell_rev/components/main_component.tpa",
        "spell_rev/lib/cre_spell_immunity.tph",
        "spell_rev/lib/manage_add_spell_references.tpa",
        "spell_rev/lib/ardanis_spell_shield.tph",
        "spell_rev/lib/ds.tph",
        "spell_rev/lib/kreso_haste_slow.tph",
        "spell_rev/lib/kreso_petrification.tph",
        "spell_rev/lib/dispelling_screen.tph",
        "spell_rev/lib/macros.tpa",
        "spell_rev/lib/insects.tph",
        "spell_rev/lib/refinements.tph",
        "spell_rev/lib/imprisonment.tph",
        "spell_rev/lib/utilities/utilities.tpa",
        "spell_rev/lib/inquisitor_true_seeing.tph",
        "spell_rev/lib/kreso_extra.tph",
        "spell_rev/lib/kreso_ee.tph",
        "spell_rev/lib/refresh_non_stacking.tpa",
        "spell_rev/lib/kreso_eestatsr.tph",
        "spell_rev/lib/d5_spell_school_list.tpa",
        "spell_rev/lib/d5_set_spell_schools.tpa",
        "spell_rev/lib/handle_spell_flags.tph",
        "spell_rev/lib/fix_displayed_strings.tph",
    )


def test_inventory_report_bytes_are_deterministic_and_machine_relative(
    tmp_path: Path,
) -> None:
    (tmp_path / "spell_rev/components").mkdir(parents=True)
    (tmp_path / "spell_rev/lib").mkdir()
    (tmp_path / "spell_rev/components/main_component.tpa").write_text(
        "INCLUDE ~spell_rev/lib/helper.tph~\nCOPY ~spell_rev/a.spl~ ~override~\n",
        encoding="utf-8",
    )
    (tmp_path / "spell_rev/lib/helper.tph").write_text(
        "PRINT ~helper~\n", encoding="utf-8"
    )

    first = report_json_bytes(build_inventory_report(tmp_path))
    second = report_json_bytes(build_inventory_report(tmp_path))

    assert first == second
    assert str(tmp_path).encode() not in first
    assert b'"generated_at"' not in first
    assert b'"source_files": [' in first
    assert b'"binary_edges": []' in first


def test_inventory_report_uses_repository_relative_binary_paths(
    tmp_path: Path,
) -> None:
    (tmp_path / "spell_rev/components").mkdir(parents=True)
    (tmp_path / "spell_rev/components/main_component.tpa").write_text(
        "PRINT ~inventory~\n", encoding="utf-8"
    )
    resource = bytearray(0x72)
    resource[:8] = b"SPL V1  "
    resource[0x3A:0x42] = b"ChildSpl"
    struct.pack_into("<I", resource, 0x64, 0x72)
    struct.pack_into("<I", resource, 0x6A, 0x72)
    (tmp_path / "spell_rev/source.spl").write_bytes(resource)
    (tmp_path / "spell_rev/ChildSpl.bam").write_bytes(b"not scanned")

    report = build_inventory_report(tmp_path)

    assert report["resources"] == [
        {"path": "spell_rev/source.spl", "format": "SPL V1", "edge_count": 1}
    ]
    edge = report["binary_edges"][0]
    assert edge["source"] == "spell_rev/source.spl"
    assert edge["local_candidates"] == ["spell_rev/ChildSpl.bam"]
