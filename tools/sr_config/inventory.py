"""Deterministic source/binary inventory report orchestration."""

from __future__ import annotations

import json
from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .resources import scan_package_resources
from .source import ResourceOperand, SourceError, SourceNode, inventory


DEFAULT_ENTRY = "spell_rev/components/main_component.tpa"
DEFAULT_RESOURCE_ROOT = "spell_rev"


@dataclass(frozen=True)
class IncludeEdge:
    """One literal or unresolved dynamic source include in traversal order."""

    source: str
    line: int
    operand: str
    resolved: str | None


def inventory_tree(
    root: str | Path, entry: str | Path = DEFAULT_ENTRY
) -> tuple[SourceNode, ...]:
    """Inventory *entry* and its literal INCLUDE closure in DFS source order."""

    nodes, _ = _inventory_tree(root, entry)
    return nodes


def inventory_tree_with_edges(
    root: str | Path,
    entry: str | Path = DEFAULT_ENTRY,
    *,
    include_resolutions: Mapping[tuple[str, str], tuple[str, ...]] | None = None,
) -> tuple[tuple[SourceNode, ...], tuple[IncludeEdge, ...]]:
    """Inventory a closure and retain literal and explicitly resolved edges."""

    return _inventory_tree(
        root,
        entry,
        include_resolutions=include_resolutions,
    )


def _inventory_tree(
    root: str | Path,
    entry: str | Path,
    *,
    include_resolutions: Mapping[tuple[str, str], tuple[str, ...]] | None = None,
) -> tuple[tuple[SourceNode, ...], tuple[IncludeEdge, ...]]:
    """Return lossless source nodes and every discovered INCLUDE edge."""

    root_path = Path(root).resolve()
    entry_path = _repository_include_path(str(entry), source="<entry>")
    visited: set[str] = set()
    result: list[SourceNode] = []
    include_edges: list[IncludeEdge] = []
    resolutions = include_resolutions or {}

    def visit(relative: str) -> None:
        key = relative.casefold()
        if key in visited:
            return
        visited.add(key)
        path = root_path / PurePosixPath(relative)
        if not path.is_file():
            raise SourceError(f"{relative}: included source does not exist")
        nodes = inventory(path, root=root_path)
        result.extend(nodes)
        try:
            source = path.read_bytes()
        except OSError as error:
            raise SourceError(f"{relative}: unable to read included source: {error}") from error
        for include, line in _include_occurrences(source):
            resolved = _resolve_include(include, source=relative)
            if resolved is None:
                key = (
                    relative.casefold(),
                    include.replace("\\", "/").casefold(),
                )
                explicit_targets = resolutions.get(key, ())
                if not explicit_targets:
                    include_edges.append(
                        IncludeEdge(relative, line, include, None)
                    )
                    continue
                for target in explicit_targets:
                    concrete = _repository_include_path(target, source=relative)
                    include_edges.append(
                        IncludeEdge(relative, line, include, concrete)
                    )
                    visit(concrete)
                continue
            include_edges.append(
                IncludeEdge(relative, line, include, resolved)
            )
            visit(resolved)

    visit(entry_path)
    return tuple(result), tuple(include_edges)


def build_inventory_report(root: str | Path) -> dict[str, object]:
    """Build the canonical source and binary inventory for a repository checkout."""

    root_path = Path(root).resolve()
    source_nodes, include_edges = _inventory_tree(root_path, DEFAULT_ENTRY)
    source_files = tuple(dict.fromkeys(node.path for node in source_nodes))
    executable_nodes = tuple(node for node in source_nodes if node.kind != "trivia")
    resources = scan_package_resources(root_path / DEFAULT_RESOURCE_ROOT)
    binary_edges = tuple(edge for resource in resources for edge in resource.edges)

    return {
        "schema_version": 1,
        "entry": DEFAULT_ENTRY,
        "source_files": list(source_files),
        "include_edges": [
            {
                "source": edge.source,
                "line": edge.line,
                "operand": edge.operand,
                "resolved": edge.resolved,
                "status": "resolved" if edge.resolved is not None else "dynamic",
            }
            for edge in include_edges
        ],
        "source_nodes": [
            {
                "path": node.path,
                "line": node.line,
                "kind": node.kind,
                "command": node.command,
                "section_comments": list(node.section_comments),
                "resource_operands": [
                    {"role": operand.role, "value": operand.value}
                    for operand in node.resource_operands
                ],
            }
            for node in executable_nodes
        ],
        "resources": [
            {
                "path": _resource_report_path(resource.path),
                "format": resource.format,
                "edge_count": len(resource.edges),
            }
            for resource in resources
        ],
        "binary_edges": [
            {
                "source": _resource_report_path(edge.source),
                "format": edge.format,
                "field": edge.field,
                "opcode": edge.opcode,
                "offset": edge.offset,
                "target": edge.target,
                "semantics": edge.semantics,
                "expected_types": list(edge.expected_types),
                "classification": edge.classification,
                "local_candidates": [
                    _resource_report_path(candidate)
                    for candidate in edge.local_candidates
                ],
            }
            for edge in binary_edges
        ],
        "summary": {
            "source_file_count": len(source_files),
            "source_node_count": len(executable_nodes),
            "include_edge_count": len(include_edges),
            "dynamic_include_edge_count": sum(
                edge.resolved is None for edge in include_edges
            ),
            "resource_file_count": len(resources),
            "binary_edge_count": len(binary_edges),
            "resource_payload_count": sum(
                edge.semantics == "resource" for edge in binary_edges
            ),
            "non_resource_payload_count": sum(
                edge.semantics == "non_resource" for edge in binary_edges
            ),
            "unknown_payload_count": sum(
                edge.semantics == "unknown" for edge in binary_edges
            ),
            "local_binary_edge_count": sum(
                edge.classification == "local" for edge in binary_edges
            ),
            "external_binary_edge_count": sum(
                edge.classification == "external" for edge in binary_edges
            ),
        },
    }


def report_json_bytes(report: object) -> bytes:
    """Serialize an inventory report canonically, without host-specific metadata."""

    return (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")


def write_inventory_report(
    root: str | Path, output: str | Path
) -> tuple[dict[str, object], bytes]:
    """Build and write a report, returning both the object and exact bytes."""

    report = build_inventory_report(root)
    payload = report_json_bytes(report)
    output_path = Path(output)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(payload)
    except OSError as error:
        raise SourceError(f"{output_path}: unable to write inventory report: {error}") from error
    return report, payload


def _resolve_include(value: str, *, source: str) -> str | None:
    normalized = value.replace("\\", "/")
    normalized = _replace_mod_folder(normalized)
    if "%" in normalized:
        # Dynamic includes remain visible in their owning source node, but they
        # cannot be followed without executing the installer.
        return None
    return _repository_include_path(normalized, source=source)


def _resource_report_path(value: str) -> str:
    return f"{DEFAULT_RESOURCE_ROOT}/{value}"


def _replace_mod_folder(value: str) -> str:
    marker = "%MOD_FOLDER%"
    result = value
    while marker.casefold() in result.casefold():
        index = result.casefold().index(marker.casefold())
        result = result[:index] + "spell_rev" + result[index + len(marker) :]
    return result


def _repository_include_path(value: str, *, source: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not normalized or any(part in {"", ".", ".."} for part in path.parts):
        raise SourceError(f"{source}: unsafe INCLUDE path {value!r}")
    return path.as_posix()


def _include_occurrences(source: bytes) -> tuple[tuple[str, int], ...]:
    tokens = _weidu_tokens(source)
    line_starts = [0]
    line_starts.extend(index + 1 for index, byte in enumerate(source) if byte == 0x0A)
    includes: list[tuple[str, int]] = []
    index = 0
    while index < len(tokens):
        kind, value, offset = tokens[index]
        if kind != "identifier" or value.casefold() not in {
            "include",
            "reinclude",
        }:
            index += 1
            continue
        line = bisect_right(line_starts, offset)
        index += 1
        while index < len(tokens) and tokens[index][0] == "string":
            includes.append((tokens[index][1], line))
            index += 1
    return tuple(includes)


def _weidu_tokens(source: bytes) -> tuple[tuple[str, str, int], ...]:
    """Tokenize identifiers/strings while masking comments and inline files."""

    tokens: list[tuple[str, str, int]] = []
    index = 0
    line_start = True
    block_comment = False
    inline_file = False
    while index < len(source):
        if line_start:
            line_end = source.find(b"\n", index)
            if line_end < 0:
                line_end = len(source)
            stripped = source[index:line_end].lstrip(b" \t\r")
            if inline_file:
                if stripped.startswith(b">>>>>>>>"):
                    inline_file = False
                index = line_end + (line_end < len(source))
                line_start = True
                continue
            if not block_comment and stripped.startswith(b"<<<<<<<<"):
                inline_file = True
                index = line_end + (line_end < len(source))
                line_start = True
                continue
            line_start = False

        if block_comment:
            close = source.find(b"*/", index)
            if close < 0:
                break
            block_comment = False
            index = close + 2
            continue
        if source.startswith(b"//", index):
            newline = source.find(b"\n", index)
            if newline < 0:
                break
            index = newline + 1
            line_start = True
            continue
        if source.startswith(b"/*", index):
            block_comment = True
            index += 2
            continue
        byte = source[index]
        if byte in (ord("~"), ord('"')):
            token_offset = index
            close = source.find(bytes((byte,)), index + 1)
            if close < 0:
                break
            value = source[index + 1 : close].decode("utf-8", errors="replace")
            tokens.append(("string", value, token_offset))
            line_start = b"\n" in source[index:close]
            index = close + 1
            continue
        if (ord("A") <= byte <= ord("Z")) or (ord("a") <= byte <= ord("z")) or byte == ord("_"):
            end = index + 1
            while end < len(source):
                candidate = source[end]
                if (
                    ord("A") <= candidate <= ord("Z")
                    or ord("a") <= candidate <= ord("z")
                    or ord("0") <= candidate <= ord("9")
                    or candidate in (ord("_"), ord("#"))
                ):
                    end += 1
                else:
                    break
            tokens.append(
                ("identifier", source[index:end].decode("ascii"), index)
            )
            index = end
            continue
        if byte == ord("\n"):
            line_start = True
        index += 1
    return tuple(tokens)


__all__ = [
    "IncludeEdge",
    "ResourceOperand",
    "SourceError",
    "SourceNode",
    "build_inventory_report",
    "inventory",
    "inventory_tree",
    "inventory_tree_with_edges",
    "report_json_bytes",
    "write_inventory_report",
]
