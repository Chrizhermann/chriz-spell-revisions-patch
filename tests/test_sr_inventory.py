from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pytest

from tools.sr_config.__main__ import main
from tools.sr_config.catalog import Catalog, SourceSpan
from tools.sr_config.coverage import audit_catalog_coverage
from tools.sr_config.inventory import (
    build_inventory_report,
    inventory,
    inventory_tree,
    report_json_bytes,
)
from tools.sr_config.source import SourceError, inventory_nested, resolve_span


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


@pytest.mark.parametrize(
    ("name", "source", "message"),
    [
        ("quote", b"PRINT ~unterminated\n", "unterminated quote.*line 1"),
        ("comment", b"/* unterminated\n", "unterminated block comment.*line 1"),
        (
            "inline-file",
            b"<<<<<<<< generated\nPRINT ~opaque~\n",
            "unterminated inline-file.*line 1",
        ),
    ],
)
def test_inventory_rejects_unterminated_opaque_regions_with_opener_context(
    tmp_path: Path, name: str, source: bytes, message: str
) -> None:
    path = tmp_path / f"{name}.tpa"
    path.write_bytes(source)

    with pytest.raises(SourceError, match=message) as error:
        inventory(path)

    assert path.name in str(error.value)


@pytest.mark.parametrize(
    ("name", "source", "message"),
    [
        (
            "action-block",
            "ACTION_IF (1) BEGIN\n  PRINT ~inside~\n",
            "unterminated ACTION_IF block.*line 1",
        ),
        (
            "patch-block",
            "OUTER_INNER_PATCH ~abc~ BEGIN\n  READ_BYTE 0 value\n",
            "unterminated OUTER_INNER_PATCH block.*line 1",
        ),
        (
            "call",
            "LAF Example\n  INT_VAR value = 1\n",
            "unterminated LAF call.*line 1",
        ),
    ],
)
def test_inventory_rejects_unterminated_blocks_and_calls_with_opener_context(
    tmp_path: Path, name: str, source: str, message: str
) -> None:
    path = tmp_path / f"{name}.tpa"
    path.write_text(source, encoding="utf-8")

    with pytest.raises(SourceError, match=message) as error:
        inventory(path)

    assert path.name in str(error.value)


@pytest.mark.parametrize(
    ("name", "source", "message"),
    [
        ("unmatched-end", "END\n", "unmatched END.*line 1"),
        ("unclosed-begin", "BEGIN\n", "unterminated BEGIN delimiter.*line 1"),
    ],
)
def test_inventory_rejects_unmatched_structural_delimiters(
    tmp_path: Path, name: str, source: str, message: str
) -> None:
    path = tmp_path / f"{name}.tpa"
    path.write_text(source, encoding="utf-8")

    with pytest.raises(SourceError, match=message) as error:
        inventory(path)

    assert path.name in str(error.value)


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


def test_nested_inventory_keeps_decompile_and_patch_through_but_only_in_copy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "decompile-copy.tpa"
    path.write_text(
        "ACTION_IF (1) BEGIN\n"
        "  COPY_EXISTING ~cut01b.bcs~ ~override~\n"
        "    DECOMPILE_AND_PATCH BEGIN\n"
        "      REPLACE_TEXTUALLY ~OLD~ ~NEW~\n"
        "    END\n"
        "    BUT_ONLY\n"
        "  PRINT ~after copy~\n"
        "END\n",
        encoding="utf-8",
    )

    outer = next(node for node in inventory(path) if node.command == "ACTION_IF")
    nested = inventory_nested(outer)

    assert [(node.kind, node.command) for node in nested] == [
        ("executable", "COPY_EXISTING"),
        ("executable", "PRINT"),
    ]
    assert b"DECOMPILE_AND_PATCH" in nested[0].raw
    assert b"REPLACE_TEXTUALLY" in nested[0].raw
    assert b"BUT_ONLY" in nested[0].raw


def test_nested_inventory_keeps_assignments_loops_reads_and_writes_in_copy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "patch-stream-copy.tpa"
    path.write_text(
        "DEFINE_ACTION_FUNCTION patch_files BEGIN\n"
        "  COPY ~spell_rev/a.spl~ ~override~\n"
        "    arbitrary_offset = 0\n"
        "    FOR (index = 0; index < 2; ++index) BEGIN\n"
        "      READ_LONG arbitrary_offset value\n"
        "      PATCH_IF value BEGIN\n"
        "        WRITE_LONG arbitrary_offset 0\n"
        "      END\n"
        "    END\n"
        "  GET_DIRECTORY_ARRAY folders ~spell_rev~ ~^sp.+$~\n"
        "  MYSTERY_ACTION ~outside patch stream~\n"
        "END\n",
        encoding="utf-8",
    )

    outer = next(
        node for node in inventory(path) if node.command == "DEFINE_ACTION_FUNCTION"
    )
    nested = inventory_nested(outer)

    assert [(node.kind, node.command) for node in nested] == [
        ("executable", "COPY"),
        ("executable", "GET_DIRECTORY_ARRAY"),
        ("unknown", "MYSTERY_ACTION"),
    ]
    assert b"arbitrary_offset = 0" in nested[0].raw
    assert b"FOR (index = 0" in nested[0].raw
    assert b"READ_LONG" in nested[0].raw
    assert b"PATCH_IF" in nested[0].raw
    assert b"WRITE_LONG" in nested[0].raw


def test_nested_inventory_keeps_count_set_and_for_patch_stream_in_copy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "count-copy.tpa"
    path.write_text(
        "WITH_SCOPE BEGIN\n"
        "  COPY ~spell_rev/table.2da~ ~override~\n"
        "    COUNT_2DA_COLS cols\n"
        "    COUNT_2DA_ROWS cols rows\n"
        "    SET total = 0\n"
        "    FOR (row = 0; row < rows; ++row) BEGIN\n"
        "      SET total += 1\n"
        "    END\n"
        "  PRINT ~after table patch~\n"
        "END\n",
        encoding="utf-8",
    )

    outer = next(node for node in inventory(path) if node.command == "WITH_SCOPE")
    nested = inventory_nested(outer)

    assert [(node.kind, node.command) for node in nested] == [
        ("executable", "COPY"),
        ("executable", "PRINT"),
    ]
    assert b"COUNT_2DA_COLS" in nested[0].raw
    assert b"COUNT_2DA_ROWS" in nested[0].raw
    assert b"SET total = 0" in nested[0].raw
    assert b"FOR (row = 0" in nested[0].raw


def test_unknown_depth_zero_statement_ends_complete_copy_operands(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unknown-after-copy.tpa"
    path.write_text(
        "COPY ~a.spl~ ~override~\n"
        "MYSTERY_STATEMENT ~odd.res~\n"
        "PRINT ~next action~\n",
        encoding="utf-8",
    )

    nodes = tuple(node for node in inventory(path) if node.kind != "trivia")

    assert [(node.kind, node.command) for node in nodes] == [
        ("executable", "COPY"),
        ("unknown", "MYSTERY_STATEMENT"),
        ("executable", "PRINT"),
    ]
    assert [(operand.role, operand.value) for operand in nodes[0].resource_operands] == [
        ("source", "a.spl"),
        ("destination", "override"),
    ]
    assert b"".join(node.raw for node in inventory(path)) == path.read_bytes()


@pytest.mark.parametrize(
    ("command", "head"),
    [
        ("ADD_SPELL", "ADD_SPELL ~a.spl~ 2 3 ~WIZARD_A~\n"),
        ("APPEND", "APPEND ~spell.ids~ ~1702 CLERIC_TEST~\n"),
    ],
)
def test_unknown_depth_zero_statement_ends_complete_non_copy_pipeline(
    tmp_path: Path, command: str, head: str
) -> None:
    path = tmp_path / f"unknown-after-{command.casefold()}.tpa"
    path.write_text(
        head
        + "MYSTERY_STATEMENT ~odd~\n"
        + "PRINT ~next action~\n",
        encoding="utf-8",
    )

    nodes = tuple(node for node in inventory(path) if node.kind != "trivia")

    assert [(node.kind, node.command) for node in nodes] == [
        ("executable", command),
        ("unknown", "MYSTERY_STATEMENT"),
        ("executable", "PRINT"),
    ]
    assert b"".join(node.raw for node in inventory(path)) == path.read_bytes()


def test_multiline_add_spell_waits_for_all_four_operands(tmp_path: Path) -> None:
    path = tmp_path / "multiline-add-spell.tpa"
    path.write_text(
        "ADD_SPELL ~a.spl~\n"
        "  2 3\n"
        "  ~WIZARD_A~\n"
        "MYSTERY_STATEMENT ~odd~\n"
        "PRINT ~next action~\n",
        encoding="utf-8",
    )

    nodes = tuple(node for node in inventory(path) if node.kind != "trivia")

    assert [(node.kind, node.command) for node in nodes] == [
        ("executable", "ADD_SPELL"),
        ("unknown", "MYSTERY_STATEMENT"),
        ("executable", "PRINT"),
    ]
    assert b"2 3" in nodes[0].raw
    assert b"WIZARD_A" in nodes[0].raw


def test_incomplete_add_spell_fails_closed_before_unknown_statement(
    tmp_path: Path,
) -> None:
    path = tmp_path / "incomplete-add-spell.tpa"
    path.write_text(
        "ADD_SPELL ~a.spl~ 2\n"
        "MYSTERY_STATEMENT ~odd~\n",
        encoding="utf-8",
    )

    with pytest.raises(
        SourceError,
        match="incomplete ADD_SPELL operands.*line 1.*MYSTERY_STATEMENT.*line 2",
    ) as error:
        inventory(path)

    assert path.name in str(error.value)


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


def test_resolve_span_supports_an_explicit_eof_end_anchor(tmp_path: Path) -> None:
    source = b"preamble\r\n// final\r\nPRINT ~last~\r\n"
    path = tmp_path / "main.tpa"
    path.write_bytes(source)
    original_span = b"// final\r\nPRINT ~last~\r\n"
    span = SourceSpan(
        path="main.tpa",
        start="// final",
        end=None,
        sha256=hashlib.sha256(b"// final\nPRINT ~last~\n").hexdigest(),
    )

    assert resolve_span(tmp_path, span) == original_span


@pytest.mark.parametrize(
    ("source_newline", "anchor_newline"),
    [
        (b"\r\n", "\n"),
        (b"\n", "\r\n"),
        (b"\r", "\n"),
        (b"\n", "\r"),
    ],
)
def test_resolve_span_matches_multiline_anchors_across_newline_styles(
    tmp_path: Path,
    source_newline: bytes,
    anchor_newline: str,
) -> None:
    source = source_newline.join(
        (
            b"preamble",
            b"// unique start",
            b"COPY ~a.spl~ ~override~",
            b"// unique end",
            b"tail",
            b"",
        )
    )
    path = tmp_path / "main.tpa"
    path.write_bytes(source)
    start = f"// unique start{anchor_newline}COPY ~a.spl~ ~override~"
    end = f"// unique end{anchor_newline}tail"
    start_offset = source.index(b"// unique start")
    end_offset = source.index(b"// unique end")
    original = source[start_offset:end_offset]
    normalized = original.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    span = SourceSpan(
        path="main.tpa",
        start=start,
        end=end,
        sha256=hashlib.sha256(normalized).hexdigest(),
    )

    assert resolve_span(tmp_path, span) == original


def test_resolve_span_rejects_newline_normalized_anchor_ambiguity(
    tmp_path: Path,
) -> None:
    source = (
        b"// repeated\r\nCOPY ~a.spl~ ~override~\r\n"
        b"// repeated\nCOPY ~a.spl~ ~override~\n"
        b"// end\n"
    )
    (tmp_path / "main.tpa").write_bytes(source)
    span = SourceSpan(
        path="main.tpa",
        start="// repeated\r\nCOPY ~a.spl~ ~override~",
        end="// end",
        sha256="0" * 64,
    )

    with pytest.raises(SourceError, match="start anchor.*2 matches"):
        resolve_span(tmp_path, span)


def test_resolve_span_rejects_reversed_normalized_multiline_anchors(
    tmp_path: Path,
) -> None:
    source = b"// end\r\ntail\r\n// start\r\nCOPY ~a.spl~ ~override~\r\n"
    (tmp_path / "main.tpa").write_bytes(source)
    span = SourceSpan(
        path="main.tpa",
        start="// start\nCOPY ~a.spl~ ~override~",
        end="// end\ntail",
        sha256="0" * 64,
    )

    with pytest.raises(SourceError, match="end anchor.*before start anchor"):
        resolve_span(tmp_path, span)


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
    assert edge["semantics"] == "resource"
    assert edge["expected_types"] == ["BAM"]
    assert edge["local_candidates"] == ["spell_rev/ChildSpl.bam"]


def test_inventory_report_counts_payload_semantics_separately(
    tmp_path: Path,
) -> None:
    (tmp_path / "spell_rev/components").mkdir(parents=True)
    (tmp_path / "spell_rev/components/main_component.tpa").write_text(
        "PRINT ~inventory~\n", encoding="utf-8"
    )
    ability_offset = 0x72
    effect_offset = ability_offset + 0x28
    resource = bytearray(effect_offset + 3 * 0x30)
    resource[:8] = b"SPL V1  "
    struct.pack_into("<I", resource, 0x64, ability_offset)
    struct.pack_into("<H", resource, 0x68, 1)
    struct.pack_into("<I", resource, 0x6A, effect_offset)
    struct.pack_into("<H", resource, ability_offset + 0x1E, 3)
    for index, (opcode, target) in enumerate(
        ((177, b"ChildEff"), (265, b"GLOBNAME"), (999, b"Mystery"))
    ):
        offset = effect_offset + index * 0x30
        struct.pack_into("<H", resource, offset, opcode)
        resource[offset + 0x14 : offset + 0x1C] = target.ljust(8, b"\0")
    (tmp_path / "spell_rev/source.spl").write_bytes(resource)
    child_eff = bytearray(0x110)
    child_eff[:16] = b"EFF V2.0EFF V2.0"
    (tmp_path / "spell_rev/ChildEff.eff").write_bytes(child_eff)

    report = build_inventory_report(tmp_path)

    assert [edge["semantics"] for edge in report["binary_edges"]] == [
        "resource",
        "non_resource",
        "unknown",
    ]
    assert [edge["classification"] for edge in report["binary_edges"]] == [
        "local",
        None,
        None,
    ]
    assert report["summary"] == {
        "source_file_count": 1,
        "source_node_count": 1,
        "include_edge_count": 0,
        "dynamic_include_edge_count": 0,
        "resource_file_count": 2,
        "binary_edge_count": 3,
        "resource_payload_count": 1,
        "non_resource_payload_count": 1,
        "unknown_payload_count": 1,
        "local_binary_edge_count": 1,
        "external_binary_edge_count": 0,
    }


def _write_coverage_language_files(root: Path, source: str = "") -> None:
    language = root / "spell_rev/languages/english"
    language.mkdir(parents=True, exist_ok=True)
    (language / "arcane.tra").write_text(source, encoding="utf-8")
    (language / "divine.tra").write_text("", encoding="utf-8")
    (language / "setup.tra").write_text("", encoding="utf-8")


def _coverage_catalog(
    *, changes: list[dict[str, object]] | None = None,
    infrastructure: list[dict[str, object]] | None = None,
) -> Catalog:
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
            "changes": changes or [],
            "infrastructure": infrastructure or [],
        }
    )


def _coverage_change(
    change_id: str,
    *,
    source_spans: list[dict[str, object]] | None = None,
    resources: list[dict[str, object]] | None = None,
    name_ref: str | None = "@1",
    description_ref: str | None = "@2",
    documentation_only_reason: str | None = None,
    component: int = 0,
    processors: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": change_id,
        "setting": f"sr_{change_id}",
        "display_name": change_id,
        "default": -1,
        "group": "global",
        "component": component,
        "games": ["all"],
        "name_ref": name_ref,
        "description_ref": description_ref,
        "source_spans": source_spans or [],
        "resources": resources or [],
        "atomic_group": None,
        "requires": [],
        "conflicts": [],
        "soft_requires": [],
        "processors": processors or [],
        "documentation_only_reason": documentation_only_reason,
    }


def _coverage_span(
    path: str, source: bytes, start: bytes, end: bytes | None
) -> dict[str, object]:
    start_offset = source.index(start)
    end_offset = len(source) if end is None else source.index(end)
    payload = source[start_offset:end_offset]
    normalized = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return {
        "path": path,
        "start": start.decode("utf-8"),
        "end": None if end is None else end.decode("utf-8"),
        "sha256": hashlib.sha256(normalized).hexdigest(),
    }


def test_catalog_coverage_reports_every_unowned_and_multiply_owned_source_node(
    tmp_path: Path,
) -> None:
    source = (
        b"// first\n"
        b"COPY ~spell_rev/assets/a.txt~ ~override~\n"
        b"// second\n"
        b"MYSTERY ~spell_rev/assets/b.txt~\n"
        b"// end\n"
    )
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    assets = tmp_path / "spell_rev/assets"
    assets.mkdir()
    (assets / "a.txt").write_text("a", encoding="utf-8")
    (assets / "b.txt").write_text("b", encoding="utf-8")
    _write_coverage_language_files(tmp_path, "@1=~First~\n@2=~Description~\n")
    first_span = _coverage_span(
        "spell_rev/components/main_component.tpa", source, b"// first", b"// second"
    )
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "first",
                source_spans=[first_span],
                resources=[{"path": "spell_rev/assets/a.txt", "kind": "asset"}],
            )
        ],
        infrastructure=[
            {
                "id": "compatibility_pass",
                "category": "compatibility",
                "source_spans": [first_span],
                "resources": [],
                "consumers": [],
            }
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    source_issues = [
        issue for issue in result.issues if issue.code.endswith("source_node")
    ]
    assert [(issue.code, issue.location) for issue in source_issues] == [
        (
            "multiply_owned_source_node",
            "spell_rev/components/main_component.tpa:2",
        ),
        ("unknown_source_node", "spell_rev/components/main_component.tpa:4"),
        ("unowned_source_node", "spell_rev/components/main_component.tpa:4"),
    ]
    assert result.source_node_count == 2


def test_catalog_coverage_requires_current_english_change_text_and_code_evidence(
    tmp_path: Path,
) -> None:
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_text("", encoding="utf-8")
    _write_coverage_language_files(tmp_path)
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "undocumented", name_ref=None, description_ref=None
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert [issue.code for issue in result.issues] == [
        "missing_change_name_ref",
        "missing_change_description_ref",
        "missing_change_evidence",
    ]
    assert all(issue.location == "changes[0]" for issue in result.issues)


def test_catalog_coverage_reports_each_missing_english_reference(
    tmp_path: Path,
) -> None:
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_text("", encoding="utf-8")
    _write_coverage_language_files(tmp_path)
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "stale_text",
                name_ref="@9001",
                description_ref="@9002",
                documentation_only_reason="fixture has no executable source",
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert [issue.code for issue in result.issues] == [
        "missing_english_reference",
        "missing_english_reference",
    ]
    assert [issue.location for issue in result.issues] == [
        "changes[0].name_ref",
        "changes[0].description_ref",
    ]


def test_catalog_coverage_classifies_source_game_resources_as_external(
    tmp_path: Path,
) -> None:
    source = (
        b"// start\nCOPY_EXISTING ~GAME.SPL~ ~override~\n// end\n"
    )
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "external",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        b"// end",
                    )
                ],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert result.ok
    assert [(edge.target, edge.classification) for edge in result.source_edges] == [
        ("GAME.SPL", "external")
    ]


def test_catalog_coverage_never_hides_unknown_source_operands(
    tmp_path: Path,
) -> None:
    source = b"// start\nMYSTERY ~odd.res~\n// end\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "unknown",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        b"// end",
                    )
                ],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert [issue.code for issue in result.issues] == [
        "unknown_source_node",
        "unknown_source_edge",
    ]
    assert [(edge.target, edge.classification) for edge in result.source_edges] == [
        ("odd.res", None)
    ]


def test_catalog_coverage_tracks_resource_arguments_passed_to_action_functions(
    tmp_path: Path,
) -> None:
    source = (
        b"// start\n"
        b"LAF ds_altered_spell STR_VAR file=~a.spl~ END\n"
        b"// end\n"
    )
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    assets = tmp_path / "spell_rev/assets"
    assets.mkdir()
    spell = bytearray(0x72)
    spell[:8] = b"SPL V1  "
    struct.pack_into("<I", spell, 0x64, len(spell))
    struct.pack_into("<I", spell, 0x6A, len(spell))
    (assets / "a.spl").write_bytes(spell)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "action_argument",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        b"// end",
                    )
                ],
                resources=[
                    {"path": "spell_rev/assets/a.spl", "kind": "asset"}
                ],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert result.ok
    action_edge = next(edge for edge in result.source_edges if edge.target == "a.spl")
    assert action_edge.classification == "owned"


def test_inventory_check_catalog_is_read_only_and_diagnostics_are_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_text("MYSTERY_ONE\nMYSTERY_TWO\n", encoding="utf-8")
    _write_coverage_language_files(tmp_path)
    catalog_path = tmp_path / "spell_rev/catalog/changes.json"
    catalog_path.parent.mkdir(parents=True)
    raw_catalog = {
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
        "changes": [],
        "infrastructure": [],
    }
    catalog_path.write_text(json.dumps(raw_catalog), encoding="utf-8")
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    monkeypatch.chdir(tmp_path)

    assert main(["inventory", "--check-catalog"]) == 1
    first = capsys.readouterr()
    assert main(["inventory", "--check-catalog"]) == 1
    second = capsys.readouterr()

    assert first == second
    assert "catalog coverage failed: 4 issue(s)" in first.err
    assert "unowned_source_node: 2" in first.err
    assert "unknown_source_node: 2" in first.err
    assert "spell_rev/components/main_component.tpa:1" in first.err
    assert "spell_rev/components/main_component.tpa:2" in first.err
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


def _minimal_coverage_spl() -> bytes:
    spell = bytearray(0x72)
    spell[:8] = b"SPL V1  "
    struct.pack_into("<I", spell, 0x64, len(spell))
    struct.pack_into("<I", spell, 0x6A, len(spell))
    return bytes(spell)


def test_eof_source_span_owns_the_final_executable_node(tmp_path: Path) -> None:
    source = b"// final\nPRINT ~last~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "final",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// final",
                        None,
                    )
                ],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert result.ok


def test_coverage_uses_newline_normalized_multiline_span_offsets(
    tmp_path: Path,
) -> None:
    source = b"// unique start\r\nPRINT ~owned~\r\n// unique end\r\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    original = source[: source.index(b"// unique end")]
    normalized = original.replace(b"\r\n", b"\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "normalized",
                source_spans=[
                    {
                        "path": "spell_rev/components/main_component.tpa",
                        "start": "// unique start\nPRINT ~owned~",
                        "end": "// unique end\n",
                        "sha256": hashlib.sha256(normalized).hexdigest(),
                    }
                ],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert result.ok


def test_nested_action_commands_expose_all_local_dependency_edges(
    tmp_path: Path,
) -> None:
    source = (
        b"// start\n"
        b"ACTION_IF (1) BEGIN\n"
        b"  COPY ~spell_rev/assets/nested.txt~ ~override~\n"
        b"  ADD_SPELL ~spell_rev/assets/deep.spl~ 2 1 ~WIZARD_DEEP~\n"
        b"  INCLUDE ~spell_rev/lib/nested.tph~\n"
        b"END\n"
    )
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    assets = tmp_path / "spell_rev/assets"
    assets.mkdir()
    (assets / "nested.txt").write_text("nested", encoding="utf-8")
    (assets / "deep.spl").write_bytes(_minimal_coverage_spl())
    library = tmp_path / "spell_rev/lib/nested.tph"
    library.parent.mkdir()
    library.write_text("", encoding="utf-8")
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "outer",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    unclassified = [
        edge.target
        for edge in result.source_edges
        if edge.classification is None
    ]
    assert unclassified == [
        "spell_rev/assets/nested.txt",
        "spell_rev/assets/deep.spl",
        "spell_rev/lib/nested.tph",
    ]
    assert sum(
        issue.code == "unclassified_local_source_edge" for issue in result.issues
    ) == 3


def test_nested_action_try_streams_are_inventoried_recursively(
    tmp_path: Path,
) -> None:
    source = (
        b"// start\n"
        b"DEFINE_ACTION_FUNCTION guarded_copy BEGIN\n"
        b"  ACTION_TRY\n"
        b"    COPY ~spell_rev/assets/nested.txt~ ~override~\n"
        b"  WITH\n"
        b"    DEFAULT\n"
        b"  END\n"
        b"END\n"
    )
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    asset = tmp_path / "spell_rev/assets/nested.txt"
    asset.parent.mkdir(parents=True)
    asset.write_text("nested", encoding="utf-8")
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "guarded",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
                resources=[
                    {"path": "spell_rev/assets/nested.txt", "kind": "asset"}
                ],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert result.ok
    assert result.source_node_count == 3
    assert [(edge.target, edge.classification) for edge in result.source_edges] == [
        ("spell_rev/assets/nested.txt", "owned")
    ]


def test_owned_unknown_node_without_operands_still_fails_coverage(
    tmp_path: Path,
) -> None:
    source = b"// start\nMYSTERY_COMMAND\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "mystery",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert [issue.code for issue in result.issues] == ["unknown_source_node"]


def test_dynamic_include_must_be_explicitly_resolved_and_inventoried(
    tmp_path: Path,
) -> None:
    source = b"// start\nINCLUDE ~spell_rev/lib/%GAME%.tph~\n"
    target_source = b"// target\nPRINT ~loaded~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    target = tmp_path / "spell_rev/lib/bg2ee.tph"
    target.parent.mkdir()
    target.write_bytes(target_source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    main_span = _coverage_span(
        "spell_rev/components/main_component.tpa", source, b"// start", None
    )
    unresolved = _coverage_catalog(
        changes=[_coverage_change("main", source_spans=[main_span])]
    )

    unresolved_result = audit_catalog_coverage(tmp_path, unresolved)

    assert "unresolved_dynamic_include" in {
        issue.code for issue in unresolved_result.issues
    }

    resolved = _coverage_catalog(
        changes=[
            _coverage_change(
                "main", source_spans=[main_span], processors=["game_include"]
            )
        ],
        infrastructure=[
            {
                "id": "game_include",
                "category": "compatibility",
                "source_spans": [
                    _coverage_span(
                        "spell_rev/lib/bg2ee.tph",
                        target_source,
                        b"// target",
                        None,
                    )
                ],
                "resources": [],
                "consumers": ["main"],
                "include_resolutions": [
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "operand": "spell_rev/lib/%GAME%.tph",
                        "targets": ["spell_rev/lib/bg2ee.tph"],
                    }
                ],
            }
        ],
    )

    resolved_result = audit_catalog_coverage(tmp_path, resolved)

    assert resolved_result.ok
    include_edge = next(
        edge
        for edge in resolved_result.source_edges
        if edge.target == "spell_rev/lib/bg2ee.tph"
    )
    assert include_edge.classification == "shared"
    assert resolved_result.source_node_count == 2


def test_dynamic_reinclude_is_not_hidden_outside_the_include_graph(
    tmp_path: Path,
) -> None:
    source = b"// start\nREINCLUDE ~spell_rev/lib/%GAME%.tph~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert [issue.code for issue in result.issues] == [
        "unresolved_dynamic_include"
    ]
    assert [(edge.target, edge.classification) for edge in result.source_edges] == [
        ("spell_rev/lib/%GAME%.tph", None)
    ]


def test_known_dynamic_source_operand_requires_explicit_resolution(
    tmp_path: Path,
) -> None:
    source = b"// start\nCOPY ~spell_rev/assets/%SPELL%.spl~ ~override~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert [issue.code for issue in result.issues] == [
        "unresolved_dynamic_source"
    ]
    assert [(edge.target, edge.classification) for edge in result.source_edges] == [
        ("spell_rev/assets/%SPELL%.spl", None)
    ]


def test_dynamic_append_payload_is_not_mistaken_for_a_source_operand(
    tmp_path: Path,
) -> None:
    source = b"// start\nAPPEND stats.ids ~%ind% %res%~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert "unresolved_dynamic_source" not in {
        issue.code for issue in result.issues
    }
    assert [(edge.target, edge.classification) for edge in result.source_edges] == [
        ("stats.ids", "external")
    ]


@pytest.mark.parametrize("command", ["APPEND", "APPEND_OUTER"])
def test_dynamic_append_target_requires_occurrence_resolution(
    tmp_path: Path,
    command: str,
) -> None:
    source = (
        b"// start\n"
        + f"{command} ~spell_rev/data/%TABLE%.2da~ ~ROW~\n".encode()
    )
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert [issue.code for issue in result.issues] == [
        "unresolved_dynamic_source"
    ]
    assert [(edge.target, edge.classification) for edge in result.source_edges] == [
        ("spell_rev/data/%TABLE%.2da", None)
    ]


def test_generated_dynamic_target_links_to_declared_runtime_resource(
    tmp_path: Path,
) -> None:
    source = b"// start\nCOPY_EXISTING ~%spell%.spl~ ~override~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
                processors=["generated_spells"],
            )
        ],
        infrastructure=[
            {
                "id": "generated_spells",
                "category": "derived",
                "source_spans": [],
                "resources": [
                    {"path": "SPPR116.SPL", "kind": "generated_resource"}
                ],
                "consumers": ["main"],
                "source_resolutions": [
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "line": 2,
                        "command": "COPY_EXISTING",
                        "operand_index": 0,
                        "operand": "%spell%.spl",
                        "reason": "Generated spell lookup",
                        "generated_owners": ["generated_spells"],
                    }
                ],
            }
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert result.ok
    assert [(edge.target, edge.classification) for edge in result.source_edges] == [
        ("SPPR116.SPL", "shared")
    ]


def test_generated_dynamic_target_requires_generated_resource_ownership(
    tmp_path: Path,
) -> None:
    source = b"// start\nCOPY_EXISTING ~%spell%.spl~ ~override~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
                processors=["generated_spells"],
            )
        ],
        infrastructure=[
            {
                "id": "generated_spells",
                "category": "derived",
                "source_spans": [],
                "resources": [],
                "consumers": ["main"],
                "source_resolutions": [
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "line": 2,
                        "command": "COPY_EXISTING",
                        "operand_index": 0,
                        "operand": "%spell%.spl",
                        "reason": "Generated spell lookup",
                        "generated_owners": ["generated_spells"],
                    }
                ],
            }
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert "undeclared_generated_source_target" in {
        issue.code for issue in result.issues
    }


def test_generated_dynamic_target_rejects_shipped_resource_ownership(
    tmp_path: Path,
) -> None:
    source = b"// start\nCOPY_EXISTING ~%spell%.spl~ ~override~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    (tmp_path / "SPPR116.SPL").write_bytes(_minimal_coverage_spl())
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
                processors=["generated_spells"],
            )
        ],
        infrastructure=[
            {
                "id": "generated_spells",
                "category": "derived",
                "source_spans": [],
                "resources": [{"path": "SPPR116.SPL", "kind": "asset"}],
                "consumers": ["main"],
                "source_resolutions": [
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "line": 2,
                        "command": "COPY_EXISTING",
                        "operand_index": 0,
                        "operand": "%spell%.spl",
                        "reason": "Generated spell lookup",
                        "generated_owners": ["generated_spells"],
                    }
                ],
            }
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert "undeclared_generated_source_target" in {
        issue.code for issue in result.issues
    }


def test_generated_dynamic_target_rejects_non_component_zero_owner(
    tmp_path: Path,
) -> None:
    source = b"// start\nCOPY_EXISTING ~%spell%.spl~ ~override~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
                processors=["generated_spells"],
            ),
            _coverage_change(
                "optional_generator",
                component=65,
                resources=[
                    {"path": "SPPR116.SPL", "kind": "generated_resource"}
                ],
                documentation_only_reason="optional component fixture",
            ),
        ],
        infrastructure=[
            {
                "id": "generated_spells",
                "category": "derived",
                "source_spans": [],
                "resources": [],
                "consumers": ["main"],
                "source_resolutions": [
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "line": 2,
                        "command": "COPY_EXISTING",
                        "operand_index": 0,
                        "operand": "%spell%.spl",
                        "reason": "Generated spell lookup",
                        "generated_owners": ["optional_generator"],
                    }
                ],
            }
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert "undeclared_generated_source_target" in {
        issue.code for issue in result.issues
    }


def test_dynamic_resolution_is_scoped_to_one_exact_occurrence(
    tmp_path: Path,
) -> None:
    source = (
        b"// start\n"
        b"COPY_EXISTING ~%spell%.spl~ ~override~\n"
        b"COPY_EXISTING ~%spell%.spl~ ~override~\n"
    )
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
                processors=["game_lookup"],
            )
        ],
        infrastructure=[
            {
                "id": "game_lookup",
                "category": "compatibility",
                "source_spans": [],
                "resources": [],
                "consumers": ["main"],
                "source_resolutions": [
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "line": 2,
                        "command": "COPY_EXISTING",
                        "operand_index": 0,
                        "operand": "%spell%.spl",
                        "reason": "Base-game lookup",
                        "external": True,
                    }
                ],
            }
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert [issue.code for issue in result.issues] == [
        "unresolved_dynamic_source"
    ]
    assert [(edge.location, edge.classification) for edge in result.source_edges] == [
        (
            "spell_rev/components/main_component.tpa:2:COPY_EXISTING.operand[0]",
            "external",
        ),
        (
            "spell_rev/components/main_component.tpa:3:COPY_EXISTING.operand[0]",
            None,
        ),
    ]


@pytest.mark.parametrize("consumers", [[], ["main"]])
def test_dynamic_resolution_requires_reciprocal_exact_source_owner(
    tmp_path: Path,
    consumers: list[str],
) -> None:
    source = b"// start\nCOPY_EXISTING ~%spell%.spl~ ~override~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
            )
        ],
        infrastructure=[
            {
                "id": "unrelated_lookup",
                "category": "compatibility",
                "source_spans": [],
                "resources": [],
                "consumers": consumers,
                "source_resolutions": [
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "line": 2,
                        "command": "COPY_EXISTING",
                        "operand_index": 0,
                        "operand": "%spell%.spl",
                        "reason": "Base-game lookup",
                        "external": True,
                    }
                ],
            }
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert "unrelated_source_resolution" in {
        issue.code for issue in result.issues
    }


def test_shifted_dynamic_occurrence_makes_resolution_stale(
    tmp_path: Path,
) -> None:
    source = (
        b"// shifted\n"
        b"PRINT ~new line~\n"
        b"COPY_EXISTING ~%spell%.spl~ ~override~\n"
    )
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// shifted",
                        None,
                    )
                ],
                processors=["game_lookup"],
            )
        ],
        infrastructure=[
            {
                "id": "game_lookup",
                "category": "compatibility",
                "source_spans": [],
                "resources": [],
                "consumers": ["main"],
                "source_resolutions": [
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "line": 2,
                        "command": "COPY_EXISTING",
                        "operand_index": 0,
                        "operand": "%spell%.spl",
                        "reason": "Base-game lookup",
                        "external": True,
                    }
                ],
            }
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert [issue.code for issue in result.issues] == [
        "unresolved_dynamic_source",
        "stale_source_resolution",
    ]


def test_dynamic_source_resolution_follows_concrete_owned_targets(
    tmp_path: Path,
) -> None:
    source = b"// start\nCOPY ~spell_rev/assets/%SPELL%.spl~ ~override~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    target = tmp_path / "spell_rev/assets/a.spl"
    target.parent.mkdir(parents=True)
    target.write_bytes(_minimal_coverage_spl())
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    span = _coverage_span(
        "spell_rev/components/main_component.tpa", source, b"// start", None
    )
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main", source_spans=[span], processors=["dynamic_sources"]
            )
        ],
        infrastructure=[
            {
                "id": "dynamic_sources",
                "category": "derived",
                "source_spans": [],
                "resources": [
                    {"path": "spell_rev/assets/a.spl", "kind": "asset"}
                ],
                "consumers": ["main"],
                "source_resolutions": [
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "line": 2,
                        "command": "COPY",
                        "operand_index": 0,
                        "operand": "spell_rev/assets/%SPELL%.spl",
                        "reason": "Loop expands the reviewed asset set",
                        "targets": ["spell_rev/assets/a.spl"],
                    }
                ],
            }
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert result.ok
    assert [(edge.target, edge.classification) for edge in result.source_edges] == [
        ("spell_rev/assets/a.spl", "shared")
    ]


def test_dynamic_source_resolution_can_explicitly_document_external_lookup(
    tmp_path: Path,
) -> None:
    source = b"// start\nCOPY_EXISTING ~%spell%.spl~ ~override~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
                processors=["game_lookup"],
            )
        ],
        infrastructure=[
            {
                "id": "game_lookup",
                "category": "compatibility",
                "source_spans": [],
                "resources": [],
                "consumers": ["main"],
                "source_resolutions": [
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "line": 2,
                        "command": "COPY_EXISTING",
                        "operand_index": 0,
                        "operand": "%spell%.spl",
                        "reason": "Resolved from the base game at install time",
                        "external": True,
                    }
                ],
            }
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert result.ok
    assert [(edge.target, edge.classification) for edge in result.source_edges] == [
        ("%spell%.spl", "external")
    ]


def test_dynamic_source_resolution_rejects_missing_targets_and_stale_rules(
    tmp_path: Path,
) -> None:
    source = b"// start\nPRINT ~no dynamic source here~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
            )
        ],
        infrastructure=[
            {
                "id": "stale_dynamic_source",
                "category": "derived",
                "source_spans": [],
                "resources": [],
                "consumers": [],
                "source_resolutions": [
                    {
                        "source": "spell_rev/components/main_component.tpa",
                        "line": 2,
                        "command": "COPY",
                        "operand_index": 0,
                        "operand": "spell_rev/assets/%SPELL%.spl",
                        "reason": "Reviewed occurrence",
                        "targets": ["spell_rev/assets/missing.spl"],
                    }
                ],
            }
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert [issue.code for issue in result.issues] == [
        "missing_dynamic_source_target",
        "stale_source_resolution",
    ]


def test_dynamic_source_resolution_source_must_exactly_exist(
    tmp_path: Path,
) -> None:
    source = b"// start\nCOPY_EXISTING ~%spell%.spl~ ~override~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "main",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
                processors=["wrong_case"],
            )
        ],
        infrastructure=[
            {
                "id": "wrong_case",
                "category": "compatibility",
                "source_spans": [],
                "resources": [],
                "consumers": ["main"],
                "source_resolutions": [
                    {
                        "source": "spell_rev/components/Main_component.tpa",
                        "line": 2,
                        "command": "COPY_EXISTING",
                        "operand_index": 0,
                        "operand": "%spell%.spl",
                        "reason": "Resolved from the base game",
                        "external": True,
                    }
                ],
            }
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert [issue.code for issue in result.issues] == [
        "stale_source_resolution",
        "unresolved_dynamic_source",
        "stale_source_resolution",
    ]


def test_non_component_zero_resource_cannot_satisfy_component_zero_edge(
    tmp_path: Path,
) -> None:
    source = b"// start\nCOPY ~spell_rev/assets/optional.txt~ ~override~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    asset = tmp_path / "spell_rev/assets/optional.txt"
    asset.parent.mkdir()
    asset.write_text("asset", encoding="utf-8")
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    span = _coverage_span(
        "spell_rev/components/main_component.tpa", source, b"// start", None
    )
    optional_owner = _coverage_change(
        "optional",
        component=65,
        resources=[{"path": "spell_rev/assets/optional.txt", "kind": "asset"}],
        documentation_only_reason="optional component fixture",
    )
    catalog = _coverage_catalog(
        changes=[_coverage_change("main", source_spans=[span]), optional_owner]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert "unclassified_local_source_edge" in {
        issue.code for issue in result.issues
    }

    catalog_with_compatibility = _coverage_catalog(
        changes=[
            _coverage_change(
                "main", source_spans=[span], processors=["compatibility_asset"]
            ),
            optional_owner,
        ],
        infrastructure=[
            {
                "id": "compatibility_asset",
                "category": "compatibility",
                "source_spans": [],
                "resources": [
                    {"path": "spell_rev/assets/optional.txt", "kind": "asset"}
                ],
                "consumers": ["main"],
            }
        ],
    )

    compatible_result = audit_catalog_coverage(tmp_path, catalog_with_compatibility)

    assert compatible_result.ok


def test_qualified_source_path_never_uses_basename_fallback(tmp_path: Path) -> None:
    source = b"// start\nCOPY ~spell_rev/wrong/a.spl~ ~override~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    right = tmp_path / "spell_rev/right/a.spl"
    right.parent.mkdir(parents=True)
    right.write_bytes(_minimal_coverage_spl())
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "qualified",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
                resources=[{"path": "spell_rev/right/a.spl", "kind": "asset"}],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    edge = next(edge for edge in result.source_edges if edge.target.endswith("a.spl"))
    assert edge.classification is None
    assert "unclassified_local_source_edge" in {
        issue.code for issue in result.issues
    }


def test_qualified_source_path_must_match_repository_spelling_exactly(
    tmp_path: Path,
) -> None:
    source = b"// start\nCOPY ~spell_rev/Right/a.spl~ ~override~\n"
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(source)
    actual = tmp_path / "spell_rev/right/a.spl"
    actual.parent.mkdir(parents=True)
    actual.write_bytes(_minimal_coverage_spl())
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "qualified",
                source_spans=[
                    _coverage_span(
                        "spell_rev/components/main_component.tpa",
                        source,
                        b"// start",
                        None,
                    )
                ],
                resources=[{"path": "spell_rev/right/a.spl", "kind": "asset"}],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    edge = next(edge for edge in result.source_edges if edge.target.endswith("a.spl"))
    assert edge.classification is None
    assert [issue.code for issue in result.issues] == [
        "unclassified_local_source_edge"
    ]


def test_blank_english_change_text_is_rejected(tmp_path: Path) -> None:
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_text("", encoding="utf-8")
    _write_coverage_language_files(tmp_path, "@1=~  \n ~\n@2=~~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "blank", documentation_only_reason="metadata-only fixture"
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert [issue.code for issue in result.issues] == [
        "blank_english_reference",
        "blank_english_reference",
    ]


def test_stale_and_multiply_declared_shipped_resources_fail_coverage(
    tmp_path: Path,
) -> None:
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_text("", encoding="utf-8")
    asset = tmp_path / "spell_rev/assets/shared.txt"
    asset.parent.mkdir()
    asset.write_text("asset", encoding="utf-8")
    _write_coverage_language_files(tmp_path, "@1=~Name~\n@2=~Description~\n")
    catalog = _coverage_catalog(
        changes=[
            _coverage_change(
                "one",
                documentation_only_reason="fixture",
                resources=[
                    {"path": "spell_rev/assets/shared.txt", "kind": "asset"},
                    {"path": "spell_rev/assets/missing.txt", "kind": "asset"},
                ],
            ),
            _coverage_change(
                "two",
                documentation_only_reason="fixture",
                resources=[
                    {"path": "spell_rev/assets/shared.txt", "kind": "asset"}
                ],
            ),
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert [issue.code for issue in result.issues] == [
        "missing_shipped_resource",
        "multiply_declared_resource",
    ]
