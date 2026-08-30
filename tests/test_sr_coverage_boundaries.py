from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools.sr_config.catalog import Catalog
from tools.sr_config.coverage import audit_catalog_coverage


UPSTREAM_COMMIT = "af1dedb6d211f86ad7a321d4080e46c748e8abac"
ENTRY = "spell_rev/components/main_component.tpa"


def _write_languages(root: Path) -> None:
    language = root / "spell_rev/languages/english"
    language.mkdir(parents=True, exist_ok=True)
    for filename in ("arcane.tra", "divine.tra", "setup.tra"):
        (language / filename).write_text("", encoding="utf-8")


def _write(root: Path, path: str, source: bytes) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source)


def _span(
    path: str,
    source: bytes,
    start: bytes,
    end: bytes | None = None,
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


def _infra(
    owner_id: str,
    *,
    source_spans: list[dict[str, object]] | None = None,
    resources: list[dict[str, object]] | None = None,
    include_resolutions: list[dict[str, object]] | None = None,
    source_resolutions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "id": owner_id,
        "activation": "consumer_selected",
        "infrastructure_requires": [],
        "source_spans": source_spans or [],
        "resources": resources or [],
        "consumers": [],
        "include_resolutions": include_resolutions or [],
        "source_resolutions": source_resolutions or [],
    }


def _deferred(
    owner_id: str,
    *,
    source_spans: list[dict[str, object]],
    resources: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "id": owner_id,
        "reason": "Explicit boundary regression fixture.",
        "source_spans": source_spans,
        "resources": resources or [],
    }


def _catalog(
    *,
    infrastructure: list[dict[str, object]],
    deferred: list[dict[str, object]] | None = None,
    closure_roots: list[dict[str, object]] | None = None,
) -> Catalog:
    return Catalog.from_dict(
        {
            "schema_version": 1,
            "upstream": {"tag": "v4.21", "commit": UPSTREAM_COMMIT},
            "migration": {
                "complete": False,
                "installer_source": ENTRY,
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
            "infrastructure": infrastructure,
            "component_zero_closure_roots": closure_roots or [],
            "dormant_resources": [],
            "deferred_source_scopes": deferred or [],
            "binary_edge_resolutions": [],
        }
    )


def _resolution(
    *,
    source: str = ENTRY,
    line: int = 2,
    operand: str = "spell_rev/assets/%FILE%.txt",
    targets: list[str],
    access: str = "read_only",
) -> dict[str, object]:
    return {
        "source": source,
        "line": line,
        "command": "COPY",
        "operand_index": 0,
        "operand": operand,
        "reason": "Exact preprocessing input set.",
        "targets": targets,
        "access": access,
    }


@pytest.mark.parametrize("resource_kind", ["asset", "resource"])
def test_read_only_resolution_accepts_exact_deferred_runtime_resource(
    tmp_path: Path, resource_kind: str
) -> None:
    main = (
        b"// reader\n"
        b"COPY ~spell_rev/assets/%FILE%.txt~ ~override~\n"
        b"// deferred marker\n"
        b"PRINT ~future~\n"
    )
    target = "spell_rev/assets/deferred.txt"
    _write(tmp_path, ENTRY, main)
    _write(tmp_path, target, b"deferred bytes")
    _write_languages(tmp_path)
    reader_span = _span(ENTRY, main, b"// reader", b"// deferred marker")
    deferred_span = _span(ENTRY, main, b"// deferred marker")
    catalog = _catalog(
        infrastructure=[
            _infra(
                "reader",
                source_spans=[reader_span],
                source_resolutions=[_resolution(targets=[target])],
            )
        ],
        deferred=[
            _deferred(
                "deferred.future",
                source_spans=[deferred_span],
                resources=[{"path": target, "kind": resource_kind}],
            )
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert result.issues == ()
    assert [(edge.target, edge.classification) for edge in result.source_edges] == [
        (target, "read_only")
    ]


@pytest.mark.parametrize("resource_kind", ["source", "generated_resource"])
def test_read_only_resolution_rejects_ineligible_deferred_resource_kinds(
    tmp_path: Path, resource_kind: str
) -> None:
    main = (
        b"// reader\n"
        b"COPY ~spell_rev/assets/%FILE%.txt~ ~override~\n"
        b"// deferred marker\n"
        b"PRINT ~future~\n"
    )
    target = "spell_rev/assets/deferred.txt"
    _write(tmp_path, ENTRY, main)
    _write(tmp_path, target, b"deferred bytes")
    _write_languages(tmp_path)
    catalog = _catalog(
        infrastructure=[
            _infra(
                "reader",
                source_spans=[
                    _span(ENTRY, main, b"// reader", b"// deferred marker")
                ],
                source_resolutions=[_resolution(targets=[target])],
            )
        ],
        deferred=[
            _deferred(
                "deferred.future",
                source_spans=[_span(ENTRY, main, b"// deferred marker")],
                resources=[{"path": target, "kind": resource_kind}],
            )
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert "deferred_read_only_source_target" in {
        issue.code for issue in result.issues
    }
    assert next(edge for edge in result.source_edges if edge.target == target).classification is None


def test_read_only_resolution_rejects_deferred_source_path_ownership(
    tmp_path: Path,
) -> None:
    main = (
        b"// reader\n"
        b"COPY ~spell_rev/lib/%FILE%.tph~ ~override~\n"
        b"INCLUDE ~spell_rev/lib/deferred.tph~\n"
    )
    deferred_source = b"// deferred code\nPRINT ~future~\n"
    target = "spell_rev/lib/deferred.tph"
    _write(tmp_path, ENTRY, main)
    _write(tmp_path, target, deferred_source)
    _write_languages(tmp_path)
    catalog = _catalog(
        infrastructure=[
            _infra(
                "reader",
                source_spans=[_span(ENTRY, main, b"// reader")],
                source_resolutions=[
                    _resolution(
                        operand="spell_rev/lib/%FILE%.tph",
                        targets=[target],
                    )
                ],
            )
        ],
        deferred=[
            _deferred(
                "deferred.code",
                source_spans=[_span(target, deferred_source, b"// deferred code")],
            )
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert "deferred_read_only_source_target" in {
        issue.code for issue in result.issues
    }
    matching = [edge for edge in result.source_edges if edge.target == target]
    assert any(edge.classification is None for edge in matching)


def test_deferred_runtime_target_exception_is_read_only_and_still_reciprocal(
    tmp_path: Path,
) -> None:
    main = (
        b"// reader\n"
        b"COPY ~spell_rev/assets/%FILE%.txt~ ~override~\n"
        b"// deferred marker\n"
        b"PRINT ~future~\n"
    )
    target = "spell_rev/assets/deferred.txt"
    _write(tmp_path, ENTRY, main)
    _write(tmp_path, target, b"deferred bytes")
    _write_languages(tmp_path)
    reader_span = _span(ENTRY, main, b"// reader", b"// deferred marker")
    deferred_span = _span(ENTRY, main, b"// deferred marker")
    target_resource = [{"path": target, "kind": "asset"}]

    dependency_catalog = _catalog(
        infrastructure=[
            _infra(
                "reader",
                source_spans=[reader_span],
                source_resolutions=[
                    _resolution(targets=[target], access="dependency")
                ],
            )
        ],
        deferred=[
            _deferred(
                "deferred.future",
                source_spans=[deferred_span],
                resources=target_resource,
            )
        ],
    )
    unrelated_catalog = _catalog(
        infrastructure=[
            _infra("source_owner", source_spans=[reader_span]),
            _infra(
                "unrelated_reader",
                source_resolutions=[_resolution(targets=[target])],
            ),
        ],
        deferred=[
            _deferred(
                "deferred.future",
                source_spans=[deferred_span],
                resources=target_resource,
            )
        ],
    )

    dependency_result = audit_catalog_coverage(tmp_path, dependency_catalog)
    unrelated_result = audit_catalog_coverage(tmp_path, unrelated_catalog)

    assert next(
        edge for edge in dependency_result.source_edges if edge.target == target
    ).classification is None
    assert "unclassified_local_source_edge" in {
        issue.code for issue in dependency_result.issues
    }
    assert next(
        edge for edge in unrelated_result.source_edges if edge.target == target
    ).classification is None
    assert "unrelated_source_resolution" in {
        issue.code for issue in unrelated_result.issues
    }


def test_read_only_resolution_rejects_active_plus_deferred_resource_ownership(
    tmp_path: Path,
) -> None:
    main = (
        b"// reader\n"
        b"COPY ~spell_rev/assets/%FILE%.txt~ ~override~\n"
        b"// deferred marker\n"
        b"PRINT ~future~\n"
    )
    target = "spell_rev/assets/shared.txt"
    _write(tmp_path, ENTRY, main)
    _write(tmp_path, target, b"shared bytes")
    _write_languages(tmp_path)
    catalog = _catalog(
        infrastructure=[
            _infra(
                "reader",
                source_spans=[
                    _span(ENTRY, main, b"// reader", b"// deferred marker")
                ],
                resources=[{"path": target, "kind": "asset"}],
                source_resolutions=[_resolution(targets=[target])],
            )
        ],
        deferred=[
            _deferred(
                "deferred.future",
                source_spans=[_span(ENTRY, main, b"// deferred marker")],
                resources=[{"path": target, "kind": "asset"}],
            )
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert "multiply_owned_read_only_source_target" in {
        issue.code for issue in result.issues
    }
    assert next(edge for edge in result.source_edges if edge.target == target).classification is None


def _mixed_include_fixture(
    tmp_path: Path,
) -> tuple[bytes, dict[str, bytes], dict[str, dict[str, object]]]:
    main = (
        b"// main\n"
        b"INCLUDE ~spell_rev/lib/same.tph~\n"
        b"INCLUDE ~spell_rev/lib/different.tph~\n"
        b"INCLUDE ~spell_rev/lib/multiple.tph~\n"
        b"INCLUDE ~spell_rev/lib/deferred-only.tph~\n"
        b"INCLUDE ~spell_rev/lib/copy-target.tph~\n"
        b"COPY ~spell_rev/lib/copy-target.tph~ ~override~\n"
        b"INCLUDE ~spell_rev/lib/%DYNAMIC%.tph~\n"
    )
    files = {
        "spell_rev/lib/same.tph": b"// same active\nPRINT ~a~\n// same deferred\nPRINT ~d~\n",
        "spell_rev/lib/different.tph": b"// different active\nPRINT ~b~\n// different deferred\nPRINT ~d~\n",
        "spell_rev/lib/multiple.tph": b"// multiple a\nPRINT ~a~\n// multiple b\nPRINT ~b~\n// multiple deferred\nPRINT ~d~\n",
        "spell_rev/lib/deferred-only.tph": b"// only deferred\nPRINT ~d~\n",
        "spell_rev/lib/copy-target.tph": b"// copy active\nPRINT ~a~\n// copy deferred\nPRINT ~d~\n",
        "spell_rev/lib/dynamic.tph": b"// dynamic active\nPRINT ~a~\n// dynamic deferred\nPRINT ~d~\n",
    }
    for path, source in files.items():
        _write(tmp_path, path, source)
    spans = {
        "main": _span(ENTRY, main, b"// main"),
        "same_active": _span(
            "spell_rev/lib/same.tph",
            files["spell_rev/lib/same.tph"],
            b"// same active",
            b"// same deferred",
        ),
        "same_deferred": _span(
            "spell_rev/lib/same.tph",
            files["spell_rev/lib/same.tph"],
            b"// same deferred",
        ),
        "different_active": _span(
            "spell_rev/lib/different.tph",
            files["spell_rev/lib/different.tph"],
            b"// different active",
            b"// different deferred",
        ),
        "different_deferred": _span(
            "spell_rev/lib/different.tph",
            files["spell_rev/lib/different.tph"],
            b"// different deferred",
        ),
        "multiple_a": _span(
            "spell_rev/lib/multiple.tph",
            files["spell_rev/lib/multiple.tph"],
            b"// multiple a",
            b"// multiple b",
        ),
        "multiple_b": _span(
            "spell_rev/lib/multiple.tph",
            files["spell_rev/lib/multiple.tph"],
            b"// multiple b",
            b"// multiple deferred",
        ),
        "multiple_deferred": _span(
            "spell_rev/lib/multiple.tph",
            files["spell_rev/lib/multiple.tph"],
            b"// multiple deferred",
        ),
        "deferred_only": _span(
            "spell_rev/lib/deferred-only.tph",
            files["spell_rev/lib/deferred-only.tph"],
            b"// only deferred",
        ),
        "copy_active": _span(
            "spell_rev/lib/copy-target.tph",
            files["spell_rev/lib/copy-target.tph"],
            b"// copy active",
            b"// copy deferred",
        ),
        "copy_deferred": _span(
            "spell_rev/lib/copy-target.tph",
            files["spell_rev/lib/copy-target.tph"],
            b"// copy deferred",
        ),
        "dynamic_active": _span(
            "spell_rev/lib/dynamic.tph",
            files["spell_rev/lib/dynamic.tph"],
            b"// dynamic active",
            b"// dynamic deferred",
        ),
        "dynamic_deferred": _span(
            "spell_rev/lib/dynamic.tph",
            files["spell_rev/lib/dynamic.tph"],
            b"// dynamic deferred",
        ),
    }
    return main, files, spans


def test_literal_include_filters_only_same_owner_deferred_path_hits(
    tmp_path: Path,
) -> None:
    main, _, spans = _mixed_include_fixture(tmp_path)
    _write(tmp_path, ENTRY, main)
    _write_languages(tmp_path)
    owner_a_spans = [
        spans["main"],
        spans["same_active"],
        spans["multiple_a"],
        spans["copy_active"],
        spans["dynamic_active"],
    ]
    owner_b_spans = [spans["different_active"], spans["multiple_b"]]
    deferred_spans = [
        spans["same_deferred"],
        spans["different_deferred"],
        spans["multiple_deferred"],
        spans["deferred_only"],
        spans["copy_deferred"],
        spans["dynamic_deferred"],
    ]
    catalog = _catalog(
        infrastructure=[
            _infra(
                "owner_a",
                source_spans=owner_a_spans,
                include_resolutions=[
                    {
                        "source": ENTRY,
                        "operand": "spell_rev/lib/%DYNAMIC%.tph",
                        "targets": ["spell_rev/lib/dynamic.tph"],
                    }
                ],
            ),
            _infra("owner_b", source_spans=owner_b_spans),
        ],
        deferred=[
            _deferred("deferred.mixed", source_spans=deferred_spans)
        ],
    )

    result = audit_catalog_coverage(tmp_path, catalog)
    by_location = {edge.location: edge for edge in result.source_edges}

    assert by_location[f"{ENTRY}:2:INCLUDE.operand[0]"].classification == "owned"
    assert by_location[f"{ENTRY}:3:INCLUDE.operand[0]"].classification is None
    assert by_location[f"{ENTRY}:4:INCLUDE.operand[0]"].classification is None
    assert by_location[f"{ENTRY}:5:INCLUDE.operand[0]"].classification is None
    assert by_location[f"{ENTRY}:7:COPY.operand[0]"].classification is None
    assert by_location[f"{ENTRY}:8:INCLUDE.operand[0]"].classification is None


def test_literal_include_exception_does_not_hide_unowned_deferred_nodes(
    tmp_path: Path,
) -> None:
    main = b"// main\nINCLUDE ~spell_rev/lib/mixed.tph~\n"
    mixed = b"// active\nPRINT ~a~\n// no owner\nPRINT ~missing~\n"
    target = "spell_rev/lib/mixed.tph"
    _write(tmp_path, ENTRY, main)
    _write(tmp_path, target, mixed)
    _write_languages(tmp_path)
    catalog = _catalog(
        infrastructure=[
            _infra(
                "owner",
                source_spans=[
                    _span(ENTRY, main, b"// main"),
                    _span(target, mixed, b"// active", b"// no owner"),
                ],
            )
        ]
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    assert "unowned_source_node" in {issue.code for issue in result.issues}


def _root_span(path: str, source: bytes) -> dict[str, object]:
    return _span(path, source, b"// root")


def test_supplemental_root_entry_include_is_one_exact_visible_structural_edge(
    tmp_path: Path,
) -> None:
    entry = b"// first\nPRINT ~one~\n// second\nPRINT ~two~\n"
    good = b"// root\nINCLUDE ~spell_rev/components/main_component.tpa~\n"
    dynamic = b"// root\nINCLUDE ~spell_rev/components/%ENTRY%.tpa~\n"
    case_drift = b"// root\nINCLUDE ~spell_rev/components/Main_Component.tpa~\n"
    duplicate = (
        b"// root\n"
        b"INCLUDE ~spell_rev/components/main_component.tpa~\n"
        b"INCLUDE ~spell_rev/components/main_component.tpa~\n"
    )
    outside = b"// root\nINCLUDE ~spell_rev/lib/outside.tph~\n"
    helper = b"INCLUDE ~spell_rev/components/main_component.tpa~\n"
    mismatch = b"// root\nINCLUDE ~spell_rev/components/main_component.tpa~\n"
    root_sources = {
        "spell_rev/setup-good.tp2": good,
        "spell_rev/setup-dynamic.tp2": dynamic,
        "spell_rev/setup-case.tp2": case_drift,
        "spell_rev/setup-duplicate.tp2": duplicate,
        "spell_rev/setup-outside.tp2": outside,
        "spell_rev/setup-mismatch.tp2": mismatch,
    }
    _write(tmp_path, ENTRY, entry)
    _write(tmp_path, "spell_rev/lib/outside.tph", helper)
    for path, source in root_sources.items():
        _write(tmp_path, path, source)
    _write_languages(tmp_path)

    infrastructure = [
        _infra(
            "entry_first",
            source_spans=[_span(ENTRY, entry, b"// first", b"// second")],
        ),
        _infra(
            "entry_second",
            source_spans=[_span(ENTRY, entry, b"// second")],
        ),
    ]
    closure_roots: list[dict[str, object]] = []
    for suffix, source in (
        ("good", good),
        ("dynamic", dynamic),
        ("case", case_drift),
        ("duplicate", duplicate),
        ("outside", outside),
        ("mismatch", mismatch),
    ):
        path = f"spell_rev/setup-{suffix}.tp2"
        span = _root_span(path, source)
        extra_spans = (
            [_span("spell_rev/lib/outside.tph", helper, b"INCLUDE")]
            if suffix == "outside"
            else []
        )
        include_resolutions = (
            [
                {
                    "source": path,
                    "operand": "spell_rev/components/%ENTRY%.tpa",
                    "targets": [ENTRY],
                }
            ]
            if suffix == "dynamic"
            else []
        )
        infrastructure.append(
            _infra(
                f"root_{suffix}",
                source_spans=[span, *extra_spans],
                include_resolutions=include_resolutions,
            )
        )
        closure_roots.append({"owner": f"root_{suffix}", "source_span": span})
    mismatch_span = _root_span("spell_rev/setup-mismatch.tp2", mismatch)
    infrastructure.append(
        _infra("overlapping_owner", source_spans=[mismatch_span])
    )
    catalog = _catalog(
        infrastructure=infrastructure,
        closure_roots=closure_roots,
    )

    result = audit_catalog_coverage(tmp_path, catalog)
    entry_edges = [edge for edge in result.source_edges if edge.target.casefold() == ENTRY.casefold()]

    good_edges = [
        edge for edge in entry_edges if edge.source == "spell_rev/setup-good.tp2"
    ]
    assert [(edge.target, edge.classification) for edge in good_edges] == [
        (ENTRY, "owned")
    ]
    assert next(
        edge for edge in entry_edges if edge.source == "spell_rev/setup-dynamic.tp2"
    ).classification is None
    assert next(
        edge for edge in entry_edges if edge.source == "spell_rev/setup-case.tp2"
    ).classification is None
    assert all(
        edge.classification is None
        for edge in entry_edges
        if edge.source == "spell_rev/setup-duplicate.tp2"
    )
    assert next(
        edge for edge in entry_edges if edge.source == "spell_rev/lib/outside.tph"
    ).classification is None
    assert next(
        edge for edge in entry_edges if edge.source == "spell_rev/setup-mismatch.tp2"
    ).classification is None
