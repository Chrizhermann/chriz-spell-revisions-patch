from __future__ import annotations

import hashlib
from pathlib import Path

from tools.sr_config.catalog import Catalog
from tools.sr_config.coverage import audit_catalog_coverage


UPSTREAM_COMMIT = "af1dedb6d211f86ad7a321d4080e46c748e8abac"


def _span(path: str, source: bytes) -> dict[str, object]:
    return {
        "path": path,
        "start": "// component-zero postlude",
        "end": None,
        "sha256": hashlib.sha256(source).hexdigest(),
    }


def _write_language_files(root: Path) -> None:
    language = root / "spell_rev/languages/english"
    language.mkdir(parents=True)
    for filename in ("arcane.tra", "divine.tra", "setup.tra"):
        (language / filename).write_text("", encoding="utf-8")


def test_closure_root_rejects_wrong_case_path_before_span_resolution(
    tmp_path: Path,
) -> None:
    component = tmp_path / "spell_rev/components/main_component.tpa"
    component.parent.mkdir(parents=True)
    component.write_bytes(b"")
    source = b"// component-zero postlude\nPRINT ~inside~\n"
    (tmp_path / "spell_rev/setup-spell_rev.tp2").write_bytes(source)
    _write_language_files(tmp_path)
    declared_span = _span("spell_rev/Setup-Spell_Rev.tp2", source)
    catalog = Catalog.from_dict(
        {
            "schema_version": 1,
            "upstream": {"tag": "v4.21", "commit": UPSTREAM_COMMIT},
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
            "infrastructure": [
                {
                    "id": "postlude",
                    "activation": "consumer_selected",
                    "infrastructure_requires": [],
                    "source_spans": [declared_span],
                    "resources": [],
                    "consumers": [],
                }
            ],
            "component_zero_closure_roots": [
                {"owner": "postlude", "source_span": declared_span}
            ],
            "dormant_resources": [],
            "deferred_source_scopes": [],
            "binary_edge_resolutions": [],
        }
    )

    result = audit_catalog_coverage(tmp_path, catalog)

    exact_issue = next(
        issue for issue in result.issues if issue.code == "invalid_closure_root"
    )
    assert exact_issue.location == "component_zero_closure_roots[0].source_span"
    assert "does not exactly match an existing file" in exact_issue.message
