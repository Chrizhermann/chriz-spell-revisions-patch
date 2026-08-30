"""Exhaustive catalog coverage checks for component-zero source and resources."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .catalog import Catalog, Change, Infrastructure
from .inventory import (
    DEFAULT_ENTRY,
    DEFAULT_RESOURCE_ROOT,
    IncludeEdge,
    inventory_tree_with_edges,
)
from .resources import scan_package_resources
from .source import (
    SourceError,
    SourceNode,
    inventory_nested,
    resolve_span,
    resolve_span_offsets,
)
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
_SHIPPED_RESOURCE_KINDS = frozenset({"asset", "resource", "source"})
_GENERATED_RESOURCE_KINDS = frozenset({"generated_resource"})
_NON_OWNING_RESOURCE_KINDS = frozenset(
    {"2da_write", "ids_write", "table_write", "tlk_write"}
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
    resource_kind: str | None = None


@dataclass(frozen=True)
class _PositionedNode:
    node: SourceNode
    start: int
    end: int


@dataclass(frozen=True)
class _PreparedIncludeResolution:
    targets: tuple[str, ...]
    owner: _Owner
    declaration: str


@dataclass(frozen=True)
class _PreparedSourceResolution:
    targets: tuple[str, ...]
    external: bool
    owner: _Owner
    declaration: str


def audit_catalog_coverage(
    root: str | Path,
    catalog: Catalog,
    *,
    entry: str | Path = DEFAULT_ENTRY,
    resource_root: str | Path = DEFAULT_RESOURCE_ROOT,
) -> CoverageResult:
    """Audit all component-zero evidence without mutating the checkout."""

    root_path = Path(root).resolve()
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
    component_zero_owners = tuple(
        owner
        for owner in change_owners
        if isinstance(owner.record, Change) and owner.record.component == 0
    ) + infrastructure_owners

    _audit_change_documentation(change_owners, texts, issues)

    include_resolutions = _prepare_include_resolutions(
        root_path, infrastructure_owners, issues
    )
    source_nodes, include_edges = inventory_tree_with_edges(
        root_path,
        entry,
        include_resolutions={
            key: resolution.targets
            for key, resolution in include_resolutions.items()
        },
    )
    _audit_include_resolutions(include_resolutions, include_edges, issues)
    executable_nodes = tuple(node for node in source_nodes if node.kind != "trivia")
    nested_nodes = tuple(
        (node, child)
        for node in executable_nodes
        for child in inventory_nested(node)
    )
    scanned_resources = scan_package_resources(root_path / resource_root)

    positioned = _position_nodes(source_nodes)
    node_hits: dict[tuple[str, int], list[_OwnershipHit]] = {
        (node.node.path, node.start): []
        for nodes in positioned.values()
        for node in nodes
        if node.node.kind != "trivia"
    }
    _collect_source_ownership(root_path, positioned, owners, node_hits, issues)
    _audit_source_node_ownership(positioned, node_hits, issues)

    resource_owners = _resource_ownership(
        root_path, component_zero_owners, issues
    )
    source_resolutions = _prepare_source_resolutions(
        root_path,
        infrastructure_owners,
        component_zero_owners,
        resource_owners,
        issues,
    )
    source_file_owners = _source_file_ownership(positioned, node_hits)
    source_edges = _audit_source_edges(
        root_path,
        executable_nodes,
        nested_nodes,
        positioned,
        node_hits,
        resource_owners,
        source_file_owners,
        include_edges,
        source_resolutions,
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
        source_node_count=len(executable_nodes) + len(nested_nodes),
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


def _prepare_include_resolutions(
    root: Path,
    owners: tuple[_Owner, ...],
    issues: list[CoverageIssue],
) -> dict[tuple[str, str], _PreparedIncludeResolution]:
    prepared: dict[tuple[str, str], _PreparedIncludeResolution] = {}
    for owner in owners:
        record = owner.record
        assert isinstance(record, Infrastructure)
        for resolution_index, resolution in enumerate(record.include_resolutions):
            declaration = (
                f"{owner.location}.include_resolutions[{resolution_index}]"
            )
            if not _repository_file_exists_exact(root, resolution.source):
                issues.append(
                    CoverageIssue(
                        "stale_include_resolution",
                        f"{declaration}.source",
                        f"source {resolution.source!r} does not exactly match an existing file",
                    )
                )
            targets: list[str] = []
            for target_index, target in enumerate(resolution.targets):
                if not _repository_file_exists_exact(root, target):
                    issues.append(
                        CoverageIssue(
                            "missing_include_target",
                            f"{declaration}.targets[{target_index}]",
                            f"target {target!r} does not exactly match an existing file",
                        )
                    )
                    continue
                targets.append(target)
            prepared[_include_key(resolution.source, resolution.operand)] = (
                _PreparedIncludeResolution(tuple(targets), owner, declaration)
            )
    return prepared


def _audit_include_resolutions(
    resolutions: dict[tuple[str, str], _PreparedIncludeResolution],
    edges: tuple[IncludeEdge, ...],
    issues: list[CoverageIssue],
) -> None:
    consumed: set[tuple[str, str]] = set()
    for edge in edges:
        if "%" not in edge.operand:
            continue
        key = _include_key(edge.source, edge.operand)
        consumed.add(key)
        if edge.resolved is None:
            issues.append(
                CoverageIssue(
                    "unresolved_dynamic_include",
                    f"{edge.source}:{edge.line}:INCLUDE",
                    f"dynamic INCLUDE operand {edge.operand!r} has no concrete catalog resolution",
                )
            )
    for key, resolution in resolutions.items():
        if key not in consumed:
            issues.append(
                CoverageIssue(
                    "stale_include_resolution",
                    resolution.declaration,
                    "declared dynamic INCLUDE does not occur in the component-zero closure",
                )
            )


def _include_key(source: str, operand: str) -> tuple[str, str]:
    return source.casefold(), operand.replace("\\", "/").casefold()


def _prepare_source_resolutions(
    root: Path,
    owners: tuple[_Owner, ...],
    component_zero_owners: tuple[_Owner, ...],
    resource_owners: dict[str, tuple[_OwnershipHit, ...]],
    issues: list[CoverageIssue],
) -> dict[tuple[str, int, str, int, str], _PreparedSourceResolution]:
    prepared: dict[
        tuple[str, int, str, int, str], _PreparedSourceResolution
    ] = {}
    owners_by_id = {
        owner.id.casefold(): owner for owner in component_zero_owners
    }
    for owner in owners:
        record = owner.record
        assert isinstance(record, Infrastructure)
        for resolution_index, resolution in enumerate(record.source_resolutions):
            declaration = (
                f"{owner.location}.source_resolutions[{resolution_index}]"
            )
            if not _repository_file_exists_exact(root, resolution.source):
                issues.append(
                    CoverageIssue(
                        "stale_source_resolution",
                        f"{declaration}.source",
                        f"source {resolution.source!r} does not exactly match an existing file",
                    )
                )
            targets: list[str] = []
            for target_index, target in enumerate(resolution.targets):
                if not _repository_file_exists_exact(root, target):
                    issues.append(
                        CoverageIssue(
                            "missing_dynamic_source_target",
                            f"{declaration}.targets[{target_index}]",
                            f"target {target!r} does not exactly match an existing file",
                        )
                    )
                    continue
                targets.append(target)
            for generated_index, generated_owner_id in enumerate(
                resolution.generated_owners
            ):
                generated_owner = owners_by_id.get(generated_owner_id.casefold())
                generated_path = (
                    f"{declaration}.generated_owners[{generated_index}]"
                )
                if generated_owner is None:
                    issues.append(
                        CoverageIssue(
                            "undeclared_generated_source_target",
                            generated_path,
                            f"owner {generated_owner_id!r} is unavailable to component zero",
                        )
                    )
                    continue
                generated_targets = tuple(
                    resource.path
                    for resource in generated_owner.record.resources
                    if resource.kind in _GENERATED_RESOURCE_KINDS
                    and any(
                        hit.owner == generated_owner
                        and hit.resource_kind in _GENERATED_RESOURCE_KINDS
                        for hit in resource_owners.get(
                            resource.path.casefold(), ()
                        )
                    )
                )
                if not generated_targets:
                    issues.append(
                        CoverageIssue(
                            "undeclared_generated_source_target",
                            generated_path,
                            f"owner {generated_owner_id!r} declares no generated_resource",
                        )
                    )
                    continue
                targets.extend(generated_targets)
            prepared[
                _source_resolution_key(
                    resolution.source,
                    resolution.line,
                    resolution.command,
                    resolution.operand_index,
                    resolution.operand,
                )
            ] = _PreparedSourceResolution(
                tuple(targets),
                resolution.external,
                owner,
                declaration,
            )
    return prepared


def _source_resolution_key(
    source: str,
    line: int,
    command: str,
    operand_index: int,
    operand: str,
) -> tuple[str, int, str, int, str]:
    return source, line, command, operand_index, operand


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
    elif not texts[canonical].strip():
        issues.append(
            CoverageIssue(
                "blank_english_reference",
                f"{owner.location}.{field}",
                f"{reference} resolves to blank English text",
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
                resolved = resolve_span_offsets(root, span)
            except SourceError as error:
                issues.append(
                    CoverageIssue("invalid_source_span", declaration, str(error))
                )
                continue
            start = resolved.start
            end = resolved.end
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
            if node.kind == "unknown":
                issues.append(
                    CoverageIssue(
                        "unknown_source_node",
                        location,
                        f"{identity} needs explicit parser support or review",
                    )
                )
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
    root: Path,
    owners: tuple[_Owner, ...],
    issues: list[CoverageIssue],
) -> dict[str, tuple[_OwnershipHit, ...]]:
    by_path: dict[str, list[_OwnershipHit]] = {}
    for owner in owners:
        for resource_index, resource in enumerate(owner.record.resources):
            normalized = resource.path.casefold()
            declaration = f"{owner.location}.resources[{resource_index}]"
            if resource.kind in _NON_OWNING_RESOURCE_KINDS:
                continue
            if resource.kind not in (
                _SHIPPED_RESOURCE_KINDS | _GENERATED_RESOURCE_KINDS
            ):
                issues.append(
                    CoverageIssue(
                        "unknown_resource_kind",
                        f"{declaration}.kind",
                        f"resource kind {resource.kind!r} has no coverage semantics",
                    )
                )
                continue
            if (
                resource.kind in _SHIPPED_RESOURCE_KINDS
                and not _repository_file_exists_exact(root, resource.path)
            ):
                issues.append(
                    CoverageIssue(
                        "missing_shipped_resource",
                        declaration,
                        f"{resource.path!r} does not exactly match an existing file",
                    )
                )
                continue
            by_path.setdefault(normalized, []).append(
                _OwnershipHit(owner, declaration, resource.kind)
            )
    for path, hits in by_path.items():
        if len(hits) > 1:
            declarations = ", ".join(hit.declaration for hit in hits)
            issues.append(
                CoverageIssue(
                    "multiply_declared_resource",
                    hits[1].declaration,
                    f"resource {path!r} is declared by {declarations}",
                )
            )
    return {path: tuple(hits) for path, hits in by_path.items()}


def _source_file_ownership(
    positioned: dict[str, tuple[_PositionedNode, ...]],
    node_hits: dict[tuple[str, int], list[_OwnershipHit]],
) -> dict[str, tuple[_OwnershipHit, ...]]:
    result: dict[str, tuple[_OwnershipHit, ...]] = {}
    for path, nodes in positioned.items():
        unique: dict[tuple[str, int], _OwnershipHit] = {}
        for positioned_node in nodes:
            if positioned_node.node.kind == "trivia":
                continue
            for hit in node_hits[(path, positioned_node.start)]:
                unique[(hit.owner.collection, hit.owner.index)] = hit
        result[path.casefold()] = tuple(unique.values())
    return result


def _repository_file_exists_exact(root: Path, relative: str) -> bool:
    current = root
    for part in PurePosixPath(relative).parts:
        try:
            names = {entry.name for entry in current.iterdir()}
        except OSError:
            return False
        if part not in names:
            return False
        current = current / part
    return current.is_file()


def _audit_source_edges(
    root: Path,
    executable_nodes: tuple[SourceNode, ...],
    nested_nodes: tuple[tuple[SourceNode, SourceNode], ...],
    positioned: dict[str, tuple[_PositionedNode, ...]],
    node_hits: dict[tuple[str, int], list[_OwnershipHit]],
    resource_owners: dict[str, tuple[_OwnershipHit, ...]],
    source_file_owners: dict[str, tuple[_OwnershipHit, ...]],
    include_edges: tuple[IncludeEdge, ...],
    source_resolutions: dict[
        tuple[str, int, str, int, str], _PreparedSourceResolution
    ],
    package_resources: tuple[str, ...],
    issues: list[CoverageIssue],
) -> list[CoveredEdge]:
    node_offsets = {
        id(positioned_node.node): positioned_node.start
        for nodes in positioned.values()
        for positioned_node in nodes
    }
    includes_by_operand: dict[tuple[str, int, str], list[IncludeEdge]] = {}
    for edge in include_edges:
        key = (
            edge.source.casefold(),
            edge.line,
            edge.operand.replace("\\", "/").casefold(),
        )
        includes_by_operand.setdefault(key, []).append(edge)
    children_by_parent: dict[int, list[SourceNode]] = {}
    for parent, child in nested_nodes:
        children_by_parent.setdefault(id(parent), []).append(child)

    result: list[CoveredEdge] = []
    consumed_source_resolutions: Counter[
        tuple[str, int, str, int, str]
    ] = Counter()

    def audit_node(
        node: SourceNode,
        source_hits: tuple[_OwnershipHit, ...] | list[_OwnershipHit],
        *,
        nested: bool,
    ) -> None:
        if nested:
            _audit_contextual_node_ownership(node, source_hits, issues)
        for operand_index, operand in enumerate(node.resource_operands):
            if operand.role == "include":
                key = (
                    node.path.casefold(),
                    node.line,
                    operand.value.replace("\\", "/").casefold(),
                )
                matched_includes = includes_by_operand.get(key, ())
                if matched_includes:
                    for include_edge in matched_includes:
                        location = (
                            f"{node.path}:{node.line}:{node.command}.operand"
                            f"[{operand_index}]"
                        )
                        if include_edge.resolved is None:
                            result.append(
                                CoveredEdge(
                                    "source",
                                    node.path,
                                    location,
                                    operand.value,
                                    None,
                                )
                            )
                            continue
                        candidate_hits = (
                            _candidate_ownership_hits(
                                include_edge.resolved,
                                resource_owners,
                                source_file_owners,
                            ),
                        )
                        classification = _classify_candidate_hits(
                            tuple(source_hits), candidate_hits
                        )
                        target_hits = tuple(
                            hit for hits in candidate_hits for hit in hits
                        )
                        result.append(
                            CoveredEdge(
                                "source",
                                node.path,
                                location,
                                include_edge.resolved,
                                classification,
                            )
                        )
                        if classification is None:
                            issues.append(
                                CoverageIssue(
                                    "unclassified_local_source_edge",
                                    location,
                                    _unclassified_message(
                                        include_edge.resolved,
                                        source_hits,
                                        target_hits,
                                    ),
                                )
                            )
                    continue
            literal_operand = operand.value
            normalized_operand = _normalize_source_operand(operand.value)
            if (
                node.kind != "unknown"
                and operand.role != "include"
                and "%" in normalized_operand
                and _is_dynamic_source_operand(
                    node, operand.role, operand.value
                )
            ):
                location = (
                    f"{node.path}:{node.line}:{node.command}.operand"
                    f"[{operand_index}]"
                )
                assert node.command is not None
                key = _source_resolution_key(
                    node.path,
                    node.line,
                    node.command,
                    operand_index,
                    literal_operand,
                )
                consumed_source_resolutions[key] += 1
                resolution = source_resolutions.get(key)
                if resolution is None:
                    result.append(
                        CoveredEdge(
                            "source",
                            node.path,
                            location,
                            literal_operand,
                            None,
                        )
                    )
                    issues.append(
                        CoverageIssue(
                            "unresolved_dynamic_source",
                            location,
                            f"dynamic source operand {literal_operand!r} has no "
                            "concrete catalog resolution",
                        )
                    )
                    continue
                related = _source_resolution_owner_is_reciprocal(
                    resolution.owner, source_hits
                )
                if not related:
                    issues.append(
                        CoverageIssue(
                            "unrelated_source_resolution",
                            resolution.declaration,
                            "resolution infrastructure is not reciprocally related "
                            "to this occurrence's exact source owner",
                        )
                    )
                if resolution.external:
                    result.append(
                        CoveredEdge(
                            "source",
                            node.path,
                            location,
                            literal_operand,
                            "external" if related else None,
                        )
                    )
                    continue
                if not resolution.targets:
                    result.append(
                        CoveredEdge(
                            "source",
                            node.path,
                            location,
                            literal_operand,
                            None,
                        )
                    )
                    continue
                for target in resolution.targets:
                    candidate_hits = (
                        _candidate_ownership_hits(
                            target, resource_owners, source_file_owners
                        ),
                    )
                    classification = _classify_candidate_hits(
                        tuple(source_hits), candidate_hits
                    )
                    if not related:
                        classification = None
                    target_hits = tuple(
                        hit for hits in candidate_hits for hit in hits
                    )
                    result.append(
                        CoveredEdge(
                            "source",
                            node.path,
                            location,
                            target,
                            classification,
                        )
                    )
                    if classification is None and related:
                        issues.append(
                            CoverageIssue(
                                "unclassified_local_source_edge",
                                location,
                                _unclassified_message(
                                    target, source_hits, target_hits
                                ),
                            )
                        )
                continue
            reference = _source_reference(
                root,
                node,
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
                    _candidate_ownership_hits(
                        candidate, resource_owners, source_file_owners
                    )
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

    for node in executable_nodes:
        source_hits = node_hits[(node.path, node_offsets[id(node)])]
        audit_node(node, source_hits, nested=False)
        for child in children_by_parent.get(id(node), ()):
            audit_node(child, source_hits, nested=True)
    for key, resolution in source_resolutions.items():
        consumed = consumed_source_resolutions[key]
        if consumed == 0:
            issues.append(
                CoverageIssue(
                    "stale_source_resolution",
                    resolution.declaration,
                    "declared dynamic source does not occur in the component-zero closure",
                )
            )
        elif consumed > 1:
            issues.append(
                CoverageIssue(
                    "multiply_consumed_source_resolution",
                    resolution.declaration,
                    f"declared dynamic source matched {consumed} occurrences; expected exactly 1",
                )
            )
    return result


def _source_resolution_owner_is_reciprocal(
    resolution_owner: _Owner,
    source_hits: tuple[_OwnershipHit, ...] | list[_OwnershipHit],
) -> bool:
    if len(source_hits) != 1:
        return False
    source_owner = source_hits[0].owner
    if (
        source_owner.collection == resolution_owner.collection
        and source_owner.index == resolution_owner.index
    ):
        return True
    if not isinstance(source_owner.record, Change) or not isinstance(
        resolution_owner.record, Infrastructure
    ):
        return False
    return _contains_id(
        source_owner.record.processors, resolution_owner.record.id
    ) and _contains_id(
        resolution_owner.record.consumers, source_owner.record.id
    )


def _audit_contextual_node_ownership(
    node: SourceNode,
    hits: tuple[_OwnershipHit, ...] | list[_OwnershipHit],
    issues: list[CoverageIssue],
) -> None:
    location = f"{node.path}:{node.line}"
    identity = f"nested {node.kind} command {node.command!r}"
    if node.kind == "unknown":
        issues.append(
            CoverageIssue(
                "unknown_source_node",
                location,
                f"{identity} needs explicit parser support or review",
            )
        )
    if not hits:
        issues.append(
            CoverageIssue(
                "unowned_source_node",
                location,
                f"{identity} inherits no catalog owner",
            )
        )
    elif len(hits) > 1:
        declarations = ", ".join(hit.declaration for hit in hits)
        issues.append(
            CoverageIssue(
                "multiply_owned_source_node",
                location,
                f"{identity} inherits owners {declarations}",
            )
        )


def _candidate_ownership_hits(
    candidate: str,
    resource_owners: dict[str, tuple[_OwnershipHit, ...]],
    source_file_owners: dict[str, tuple[_OwnershipHit, ...]],
) -> tuple[_OwnershipHit, ...]:
    key = candidate.casefold()
    unique: dict[tuple[str, int], _OwnershipHit] = {}
    for hit in resource_owners.get(key, ()) + source_file_owners.get(key, ()):
        unique[(hit.owner.collection, hit.owner.index)] = hit
    return tuple(unique.values())


def _is_create_spell_resource(node: SourceNode, role: str) -> bool:
    return (
        role == "argument"
        and node.command == "LAF"
        and re.search(rb"(?i)\bLAF\s+CREATE_SPELL\b", node.raw) is not None
    )


def _is_resource_operand(node: SourceNode, role: str, value: str) -> bool:
    laf_resource = _is_laf_resource(node, role, value)
    return (
        role in {"include", "source", "target"}
        or (role == "argument" and node.command == "ADD_PROJECTILE")
        or (role == "argument" and node.kind == "unknown")
        or laf_resource
        or _is_create_spell_resource(node, role)
    )


def _is_dynamic_source_operand(
    node: SourceNode, role: str, value: str
) -> bool:
    return (
        role in {"source", "target"}
        or (role == "argument" and node.command == "ADD_PROJECTILE")
        or _is_laf_resource(node, role, value)
        or _is_create_spell_resource(node, role)
    )


def _is_laf_resource(node: SourceNode, role: str, value: str) -> bool:
    return (
        role == "argument"
        and node.command == "LAF"
        and PurePosixPath(value.replace("\\", "/")).suffix.casefold()
        in _RESOURCE_SUFFIXES
    )


def _normalize_source_operand(value: str) -> str:
    normalized = value.replace("\\", "/")
    return re.sub(r"(?i)%MOD_FOLDER%", "spell_rev", normalized)


def _source_reference(
    root: Path,
    node: SourceNode,
    role: str,
    value: str,
    resource_owners: dict[str, tuple[_OwnershipHit, ...]],
    package_resources: tuple[str, ...],
) -> tuple[str, bool | None, tuple[str, ...]] | None:
    if not _is_resource_operand(node, role, value):
        return None
    create_spell_resource = _is_create_spell_resource(node, role)
    laf_resource = _is_laf_resource(node, role, value)
    normalized = _normalize_source_operand(value)
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
    qualified_package_path = (
        len(path.parts) > 1
        and canonical.casefold().startswith("spell_rev/")
    )
    if (
        qualified_package_path
        and "%" not in canonical
        and not _repository_file_exists_exact(root, canonical)
    ):
        return canonical, True, ()
    bare_fallback = len(path.parts) == 1 and (
        laf_resource or create_spell_resource
    )
    basename_candidates = (
        tuple(
            candidate
            for candidate in package_resources
            if PurePosixPath(candidate).name.casefold() == path.name.casefold()
        )
        if bare_fallback
        else ()
    )
    if role == "include":
        if "%" in canonical:
            return canonical, None, ()
        return canonical, True, (canonical,)
    if node.command in {"APPEND", "APPEND_OUTER"}:
        return canonical, False, ()
    local = (
        canonical.casefold().startswith("spell_rev/")
        or canonical.casefold() in resource_owners
        or ("%" not in canonical and _repository_file_exists_exact(root, canonical))
        or bool(basename_candidates)
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
