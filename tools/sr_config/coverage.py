"""Exhaustive catalog coverage checks for component-zero source and resources."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .catalog import Catalog, Change, Infrastructure
from .inventory import DEFAULT_ENTRY, DEFAULT_RESOURCE_ROOT, inventory_tree
from .resources import scan_package_resources
from .source import SourceError, SourceNode, resolve_span
from .text import load_english_tra


EDGE_CLASSIFICATIONS = frozenset(
    {"owned", "atomic", "hard", "soft", "shared", "external"}
)
_RESOURCE_SUFFIXES = frozenset(
    {
        ".2da",
        ".bam",
        ".bcs",
        ".cre",
        ".eff",
        ".itm",
        ".pro",
        ".spl",
        ".vvc",
        ".wav",
    }
)


@dataclass(frozen=True)
class CoverageIssue:
    """One deterministic, actionable catalog coverage failure."""

    code: str
    location: str
    message: str


@dataclass(frozen=True)
class CoveredEdge:
    """One source or binary reference and its catalog-derived relationship."""

    kind: str
    source: str
    location: str
    target: str
    classification: str | None


@dataclass(frozen=True)
class CoverageResult:
    """Complete coverage evidence; an empty issue tuple means the gate passes."""

    issues: tuple[CoverageIssue, ...]
    source_node_count: int
    source_edges: tuple[CoveredEdge, ...]
    binary_edges: tuple[CoveredEdge, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class _Owner:
    collection: str
    index: int
    id: str
    record: Change | Infrastructure

    @property
    def location(self) -> str:
        return f"{self.collection}[{self.index}]"


@dataclass(frozen=True)
class _OwnershipHit:
    owner: _Owner
    declaration: str


@dataclass(frozen=True)
class _PositionedNode:
    node: SourceNode
    start: int
    end: int


def audit_catalog_coverage(
    root: str | Path,
    catalog: Catalog,
    *,
    entry: str | Path = DEFAULT_ENTRY,
    resource_root: str | Path = DEFAULT_RESOURCE_ROOT,
) -> CoverageResult:
    """Audit all component-zero evidence without mutating the checkout."""

    root_path = Path(root).resolve()
    source_nodes = inventory_tree(root_path, entry)
    executable_nodes = tuple(node for node in source_nodes if node.kind != "trivia")
    scanned_resources = scan_package_resources(root_path / resource_root)
    resource_root_name = PurePosixPath(
        str(resource_root).replace("\\", "/")
    ).as_posix()
    texts = load_english_tra(root_path)
    issues: list[CoverageIssue] = []

    change_owners = tuple(
        _Owner("changes", index, record.id, record)
        for index, record in enumerate(catalog.changes)
    )
    infrastructure_owners = tuple(
        _Owner("infrastructure", index, record.id, record)
        for index, record in enumerate(catalog.infrastructure)
    )
    owners = change_owners + infrastructure_owners

    _audit_change_documentation(change_owners, texts, issues)

    positioned = _position_nodes(source_nodes)
    node_hits: dict[tuple[str, int], list[_OwnershipHit]] = {
        (node.node.path, node.start): []
        for nodes in positioned.values()
        for node in nodes
        if node.node.kind != "trivia"
    }
    _collect_source_ownership(root_path, positioned, owners, node_hits, issues)
    _audit_source_node_ownership(positioned, node_hits, issues)

    resource_owners = _resource_ownership(owners)
    source_edges = _audit_source_edges(
        root_path,
        executable_nodes,
        positioned,
        node_hits,
        resource_owners,
        tuple(
            f"{resource_root_name}/{resource.path}"
            for resource in scanned_resources
        ),
        issues,
    )
    binary_edges = _audit_binary_edges(
        scanned_resources,
        resource_root=resource_root_name,
        resource_owners=resource_owners,
        issues=issues,
    )
    return CoverageResult(
        issues=tuple(issues),
        source_node_count=len(executable_nodes),
        source_edges=tuple(source_edges),
        binary_edges=tuple(binary_edges),
    )


def format_coverage_diagnostics(result: CoverageResult) -> str:
    """Render every issue in stable audit order, preceded by deterministic counts."""

    if result.ok:
        return (
            "catalog coverage passed: "
            f"{result.source_node_count} source node(s), "
            f"{len(result.source_edges)} local source edge(s), "
            f"{len(result.binary_edges)} binary edge(s)\n"
        )
    counts = Counter(issue.code for issue in result.issues)
    lines = [f"catalog coverage failed: {len(result.issues)} issue(s)", "issue counts:"]
    for code in sorted(counts):
        lines.append(f"  {code}: {counts[code]}")
    lines.append("issues:")
    lines.extend(
        f"[{issue.code}] {issue.location}: {issue.message}"
        for issue in result.issues
    )
    return "\n".join(lines) + "\n"


def _audit_change_documentation(
    owners: tuple[_Owner, ...], texts: dict[str, str], issues: list[CoverageIssue]
) -> None:
    for owner in owners:
        record = owner.record
        assert isinstance(record, Change)
        if record.name_ref is None:
            issues.append(
                CoverageIssue(
                    "missing_change_name_ref",
                    owner.location,
                    "public change must cite its current English TRA name",
                )
            )
        else:
            _audit_tra_reference(owner, "name_ref", record.name_ref, texts, issues)
        if record.description_ref is None:
            issues.append(
                CoverageIssue(
                    "missing_change_description_ref",
                    owner.location,
                    "public change must cite its current English TRA description",
                )
            )
        else:
            _audit_tra_reference(
                owner, "description_ref", record.description_ref, texts, issues
            )
        if not record.source_spans and record.documentation_only_reason is None:
            issues.append(
                CoverageIssue(
                    "missing_change_evidence",
                    owner.location,
                    "public change needs a source span or documentation_only_reason",
                )
            )


def _audit_tra_reference(
    owner: _Owner,
    field: str,
    reference: str,
    texts: dict[str, str],
    issues: list[CoverageIssue],
) -> None:
    canonical = f"@{int(reference[1:])}"
    if canonical not in texts:
        issues.append(
            CoverageIssue(
                "missing_english_reference",
                f"{owner.location}.{field}",
                f"{reference} is absent from the current English TRA sources",
            )
        )


def _position_nodes(
    source_nodes: tuple[SourceNode, ...],
) -> dict[str, tuple[_PositionedNode, ...]]:
    by_path: dict[str, list[_PositionedNode]] = {}
    offsets: dict[str, int] = {}
    for node in source_nodes:
        start = offsets.get(node.path, 0)
        end = start + len(node.raw)
        by_path.setdefault(node.path, []).append(_PositionedNode(node, start, end))
        offsets[node.path] = end
    return {path: tuple(nodes) for path, nodes in by_path.items()}


def _collect_source_ownership(
    root: Path,
    positioned: dict[str, tuple[_PositionedNode, ...]],
    owners: tuple[_Owner, ...],
    node_hits: dict[tuple[str, int], list[_OwnershipHit]],
    issues: list[CoverageIssue],
) -> None:
    source_cache: dict[str, bytes] = {}
    for owner in owners:
        if isinstance(owner.record, Change) and owner.record.component != 0:
            for span_index, span in enumerate(owner.record.source_spans):
                declaration = f"{owner.location}.source_spans[{span_index}]"
                try:
                    resolve_span(root, span)
                except SourceError as error:
                    issues.append(
                        CoverageIssue("invalid_source_span", declaration, str(error))
                    )
            continue
        for span_index, span in enumerate(owner.record.source_spans):
            declaration = f"{owner.location}.source_spans[{span_index}]"
            nodes = positioned.get(span.path)
            if nodes is None:
                issues.append(
                    CoverageIssue(
                        "source_span_outside_inventory",
                        declaration,
                        f"{span.path} is not in the component-zero INCLUDE closure",
                    )
                )
                continue
            try:
                resolve_span(root, span)
                source = source_cache.get(span.path)
                if source is None:
                    source = (root / PurePosixPath(span.path)).read_bytes()
                    source_cache[span.path] = source
            except (OSError, SourceError) as error:
                issues.append(
                    CoverageIssue("invalid_source_span", declaration, str(error))
                )
                continue
            start = source.index(span.start.encode("utf-8"))
            end = source.index(span.end.encode("utf-8"))
            owned_count = 0
            for positioned_node in nodes:
                node = positioned_node.node
                if node.kind == "trivia":
                    continue
                if positioned_node.start >= start and positioned_node.end <= end:
                    node_hits[(node.path, positioned_node.start)].append(
                        _OwnershipHit(owner, declaration)
                    )
                    owned_count += 1
                elif positioned_node.start < end and positioned_node.end > start:
                    issues.append(
                        CoverageIssue(
                            "partial_source_node",
                            declaration,
                            f"span cuts through {node.path}:{node.line} {node.command}",
                        )
                    )
            if owned_count == 0:
                issues.append(
                    CoverageIssue(
                        "empty_source_span",
                        declaration,
                        "span owns no executable inventory node",
                    )
                )


def _audit_source_node_ownership(
    positioned: dict[str, tuple[_PositionedNode, ...]],
    node_hits: dict[tuple[str, int], list[_OwnershipHit]],
    issues: list[CoverageIssue],
) -> None:
    for nodes in positioned.values():
        for positioned_node in nodes:
            node = positioned_node.node
            if node.kind == "trivia":
                continue
            hits = node_hits[(node.path, positioned_node.start)]
            location = f"{node.path}:{node.line}"
            identity = f"{node.kind} command {node.command!r}"
            if not hits:
                issues.append(
                    CoverageIssue(
                        "unowned_source_node",
                        location,
                        f"{identity} is not owned by any catalog record",
                    )
                )
            elif len(hits) > 1:
                declarations = ", ".join(hit.declaration for hit in hits)
                issues.append(
                    CoverageIssue(
                        "multiply_owned_source_node",
                        location,
                        f"{identity} is owned by {declarations}",
                    )
                )


def _resource_ownership(
    owners: tuple[_Owner, ...],
) -> dict[str, tuple[_OwnershipHit, ...]]:
    by_path: dict[str, list[_OwnershipHit]] = {}
    for owner in owners:
        for resource_index, resource in enumerate(owner.record.resources):
            normalized = resource.path.casefold()
            declaration = f"{owner.location}.resources[{resource_index}]"
            by_path.setdefault(normalized, []).append(
                _OwnershipHit(owner, declaration)
            )
    return {path: tuple(hits) for path, hits in by_path.items()}


def _audit_source_edges(
    root: Path,
    executable_nodes: tuple[SourceNode, ...],
    positioned: dict[str, tuple[_PositionedNode, ...]],
    node_hits: dict[tuple[str, int], list[_OwnershipHit]],
    resource_owners: dict[str, tuple[_OwnershipHit, ...]],
    package_resources: tuple[str, ...],
    issues: list[CoverageIssue],
) -> list[CoveredEdge]:
    node_offsets = {
        id(positioned_node.node): positioned_node.start
        for nodes in positioned.values()
        for positioned_node in nodes
    }
    result: list[CoveredEdge] = []
    for node in executable_nodes:
        source_hits = node_hits[(node.path, node_offsets[id(node)])]
        for operand_index, operand in enumerate(node.resource_operands):
            reference = _source_reference(
                root,
                node,
                operand_index,
                operand.role,
                operand.value,
                resource_owners,
                package_resources,
            )
            if reference is None:
                continue
            target, local, candidates = reference
            location = (
                f"{node.path}:{node.line}:{node.command}.operand[{operand_index}]"
            )
            if local is None:
                classification = None
                target_hits: tuple[_OwnershipHit, ...] = ()
                issues.append(
                    CoverageIssue(
                        "unknown_source_edge",
                        location,
                        f"unknown command operand {target!r} needs explicit review",
                    )
                )
            elif not local:
                classification = "external"
                target_hits = ()
            else:
                candidate_hits = tuple(
                    resource_owners.get(candidate.casefold(), ())
                    for candidate in candidates
                )
                classification = _classify_candidate_hits(
                    tuple(source_hits), candidate_hits
                )
                target_hits = tuple(
                    hit for hits in candidate_hits for hit in hits
                )
            result.append(
                CoveredEdge(
                    kind="source",
                    source=node.path,
                    location=location,
                    target=target,
                    classification=classification,
                )
            )
            if local and classification is None:
                issues.append(
                    CoverageIssue(
                        "unclassified_local_source_edge",
                        location,
                        _unclassified_message(target, source_hits, target_hits),
                    )
                )
    return result


def _source_reference(
    root: Path,
    node: SourceNode,
    operand_index: int,
    role: str,
    value: str,
    resource_owners: dict[str, tuple[_OwnershipHit, ...]],
    package_resources: tuple[str, ...],
) -> tuple[str, bool | None, tuple[str, ...]] | None:
    laf_resource = (
        role == "argument"
        and node.command == "LAF"
        and PurePosixPath(value.replace("\\", "/")).suffix.casefold()
        in _RESOURCE_SUFFIXES
    )
    create_spell_resource = (
        role == "argument"
        and node.command == "LAF"
        and re.search(rb"(?i)\bLAF\s+CREATE_SPELL\b", node.raw) is not None
    )
    is_resource_operand = (
        role == "source"
        or (role == "argument" and node.command == "ADD_PROJECTILE")
        or (
            role == "argument"
            and node.command in {"APPEND", "APPEND_OUTER"}
            and operand_index == 0
        )
        or (role == "argument" and node.kind == "unknown")
        or laf_resource
        or create_spell_resource
    )
    if not is_resource_operand:
        return None
    normalized = value.replace("\\", "/")
    normalized = re.sub(
        r"(?i)%MOD_FOLDER%", "spell_rev", normalized
    )
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return (
            (normalized, None, ())
            if node.kind == "unknown"
            else (normalized, False, ())
        )
    canonical = path.as_posix()
    if create_spell_resource and not path.suffix:
        canonical += ".spl"
        path = PurePosixPath(canonical)
    basename_candidates = tuple(
        candidate
        for candidate in package_resources
        if PurePosixPath(candidate).name.casefold() == path.name.casefold()
    )
    if node.command == "APPEND":
        return canonical, False, ()
    local = (
        canonical.casefold().startswith("spell_rev/")
        or canonical.casefold() in resource_owners
        or ("%" not in canonical and (root / path).is_file())
        or bool(basename_candidates and (laf_resource or create_spell_resource))
    )
    if local:
        candidates = basename_candidates or (canonical,)
        return canonical, True, candidates
    if node.kind == "unknown":
        return canonical, None, ()
    if create_spell_resource:
        return canonical, True, (canonical,)
    return canonical, False, ()


def _audit_binary_edges(
    scanned_resources,
    *,
    resource_root: str,
    resource_owners: dict[str, tuple[_OwnershipHit, ...]],
    issues: list[CoverageIssue],
) -> list[CoveredEdge]:
    result: list[CoveredEdge] = []
    for resource in scanned_resources:
        source = f"{resource_root}/{resource.path}"
        source_hits = resource_owners.get(source.casefold(), ())
        for edge in resource.edges:
            location = f"{source}:0x{edge.offset:x}:{edge.field}"
            if edge.semantics == "non_resource":
                continue
            if edge.semantics == "unknown":
                result.append(
                    CoveredEdge("binary", source, location, edge.target, None)
                )
                issues.append(
                    CoverageIssue(
                        "unknown_binary_edge",
                        location,
                        f"opcode {edge.opcode} payload {edge.target!r} has "
                        "unknown semantics",
                    )
                )
                continue
            if edge.classification == "external":
                classification = "external"
            elif edge.classification == "local":
                target_hits = tuple(
                    resource_owners.get(
                        f"{resource_root}/{candidate}".casefold(), ()
                    )
                    for candidate in edge.local_candidates
                )
                classification = _classify_candidate_hits(source_hits, target_hits)
                if classification is None:
                    flattened = tuple(hit for group in target_hits for hit in group)
                    issues.append(
                        CoverageIssue(
                            "unclassified_local_binary_edge",
                            location,
                            _unclassified_message(
                                ", ".join(edge.local_candidates),
                                source_hits,
                                flattened,
                            ),
                        )
                    )
            else:
                classification = None
                issues.append(
                    CoverageIssue(
                        "unknown_binary_edge",
                        location,
                        f"resource payload {edge.target!r} has no scanner "
                        "classification",
                    )
                )
            result.append(
                CoveredEdge("binary", source, location, edge.target, classification)
            )
    return result


def _classify_candidate_hits(
    source_hits: tuple[_OwnershipHit, ...],
    candidate_hits: tuple[tuple[_OwnershipHit, ...], ...],
) -> str | None:
    if len(source_hits) != 1 or not candidate_hits:
        return None
    classifications: list[str] = []
    for hits in candidate_hits:
        if len(hits) != 1:
            return None
        classification = _classify_owners(source_hits[0].owner, hits[0].owner)
        if classification is None:
            return None
        classifications.append(classification)
    return classifications[0] if len(set(classifications)) == 1 else None


def _classify_hits(
    source_hits: tuple[_OwnershipHit, ...] | list[_OwnershipHit],
    target_hits: tuple[_OwnershipHit, ...],
) -> str | None:
    if len(source_hits) != 1 or len(target_hits) != 1:
        return None
    return _classify_owners(source_hits[0].owner, target_hits[0].owner)


def _classify_owners(source: _Owner, target: _Owner) -> str | None:
    if source.collection == target.collection and source.index == target.index:
        return "owned"
    if isinstance(source.record, Change) and isinstance(target.record, Change):
        if (
            source.record.atomic_group is not None
            and target.record.atomic_group is not None
            and source.record.atomic_group.casefold()
            == target.record.atomic_group.casefold()
        ):
            return "atomic"
        if _contains_id(source.record.requires, target.record.id):
            return "hard"
        if _contains_id(source.record.soft_requires, target.record.id):
            return "soft"
        return None
    if isinstance(source.record, Change) and isinstance(target.record, Infrastructure):
        if _contains_id(source.record.processors, target.record.id) or _contains_id(
            target.record.consumers, source.record.id
        ):
            return "shared"
        return None
    if isinstance(source.record, Infrastructure) and isinstance(target.record, Change):
        return (
            "shared"
            if _contains_id(source.record.consumers, target.record.id)
            else None
        )
    if isinstance(source.record, Infrastructure) and isinstance(
        target.record, Infrastructure
    ):
        return "shared"
    return None


def _contains_id(values: tuple[str, ...], target: str) -> bool:
    normalized = target.casefold()
    return any(value.casefold() == normalized for value in values)


def _unclassified_message(
    target: str,
    source_hits: tuple[_OwnershipHit, ...] | list[_OwnershipHit],
    target_hits: tuple[_OwnershipHit, ...],
) -> str:
    if len(source_hits) != 1:
        source_state = f"source has {len(source_hits)} ownership declaration(s)"
    else:
        source_state = f"source owner is {source_hits[0].owner.id!r}"
    if len(target_hits) != 1:
        target_state = f"target has {len(target_hits)} ownership declaration(s)"
    else:
        target_state = f"target owner is {target_hits[0].owner.id!r}"
    return f"local target {target!r} is unclassified; {source_state}; {target_state}"


__all__ = [
    "CoverageIssue",
    "CoverageResult",
    "CoveredEdge",
    "EDGE_CLASSIFICATIONS",
    "audit_catalog_coverage",
    "format_coverage_diagnostics",
]
