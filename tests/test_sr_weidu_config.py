from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from tests.weidu_env import (
    MIN_WEIDU_VERSION,
    assert_installed,
    nogame_harness,
    parse_check,
    run_weidu,
    transcript,
    weidu_version,
)
from tools.sr_config.catalog import Catalog, load_catalog
from tools.sr_config.generate import (
    catalog_fingerprint,
    render_config,
    render_weidu_config_schema,
    render_weidu_selection,
)
from tools.sr_config.resolve import feature_symbols, resolve


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "spell_rev" / "catalog" / "changes.json"
SETTINGS = ROOT / "spell_rev" / "settings.ini"
SCHEMA = ROOT / "spell_rev" / "generated" / "config_schema.tpa"
SELECTION = ROOT / "spell_rev" / "generated" / "selection.tpa"
HARNESS = ROOT / "tests" / "weidu" / "sr_config_harness.tp2"
SETUP = ROOT / "spell_rev" / "setup-spell_rev.tp2"
UPSTREAM_COMMIT = "af1dedb6d211f86ad7a321d4080e46c748e8abac"


def _group(
    group_id: str,
    setting: str,
    parent: str | None,
    default: int = -1,
) -> dict[str, Any]:
    return {
        "id": group_id,
        "setting": setting,
        "name": group_id,
        "default": default,
        "parent": parent,
    }


def _change(change_id: str, setting: str, **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": change_id,
        "setting": setting,
        "display_name": change_id,
        "default": -1,
        "group": "arcane.level1",
        "component": 0,
        "games": ["all"],
        "name_ref": "@1",
        "name_fallback": None,
        "description_ref": "@2",
        "member_refs": [],
        "source_spans": [],
        "resources": [],
        "atomic_group": None,
        "requires": [],
        "conflicts": [],
        "soft_requires": [],
        "processors": [],
        "documentation_only_reason": "WeiDU config test fixture",
    }
    value.update(overrides)
    return value


def _catalog(*changes: dict[str, Any]) -> Catalog:
    return Catalog.from_dict(
        {
            "schema_version": 1,
            "upstream": {"tag": "v4.21", "commit": UPSTREAM_COMMIT},
            "migration": {
                "complete": False,
                "installer_source": "spell_rev/components/main_component.tpa",
            },
            "groups": [
                _group("global", "sr_default", None, 1),
                _group("arcane", "sr_arcane_default", "global"),
                _group(
                    "arcane.level1",
                    "sr_arcane_level_1_default",
                    "arcane",
                ),
            ],
            "changes": list(changes),
            "infrastructure": [],
            "component_zero_closure_roots": [],
            "dormant_resources": [],
            "deferred_source_scopes": [],
            "binary_edge_resolutions": [],
        }
    )


def _config(catalog: Catalog) -> str:
    return render_config(catalog, "install_tobex = 1\n", newline="\n")


def _set_assignment(source: str, setting: str, value: str | int) -> str:
    pattern = re.compile(rf"^{re.escape(setting)}\s*=.*$", re.MULTILINE)
    rendered, count = pattern.subn(f"{setting} = {value}", source)
    assert count == 1, setting
    return rendered


def _write_generated(root: Path, catalog: Catalog) -> tuple[Path, Path]:
    schema = root / "config_schema.tpa"
    selection = root / "selection.tpa"
    schema.write_text(render_weidu_config_schema(catalog), encoding="utf-8")
    selection.write_text(render_weidu_selection(catalog), encoding="utf-8")
    return schema, selection


def _run(
    tmp_path: Path,
    catalog: Catalog,
    config: str,
    *,
    component: int = 0,
    game: str = "bg2ee",
    run_name: str = "run",
):
    generated = tmp_path / "generated"
    generated.mkdir(exist_ok=True)
    schema, selection = _write_generated(generated, catalog)
    config_path = tmp_path / "settings.ini"
    config_path.write_text(config, encoding="utf-8", newline="")
    template = tmp_path / "sentinel-template.txt"
    symbols = feature_symbols(catalog)
    template.write_text(
        "install_tobex=%install_tobex%\n"
        "selection=%sr_selection_signature%\n"
        + "".join(f"{symbol}=%{symbol}%\n" for symbol in symbols.values()),
        encoding="ascii",
    )
    run_dir = tmp_path / run_name
    output = run_dir / f"component-{component}.sentinel"
    process = nogame_harness(
        HARNESS,
        component,
        run_dir,
        [
            schema.as_posix(),
            selection.as_posix(),
            config_path.as_posix(),
            game,
            template.as_posix(),
            output.as_posix(),
        ],
    )
    return process, output, config_path


def _assert_success(
    process,
    output: Path,
    catalog: Catalog,
    selected: tuple[str, ...],
) -> None:
    assert_installed(process)
    text = output.read_text(encoding="ascii")
    selected_normalized = {value.casefold() for value in selected}
    expected_bits = "".join(
        "1" if record.id.casefold() in selected_normalized else "0"
        for record in catalog.changes
    )
    assert f"install_tobex=1\nselection={expected_bits}\n" in text
    for record, symbol in zip(catalog.changes, feature_symbols(catalog).values()):
        expected = 1 if record.id.casefold() in selected_normalized else 0
        assert f"{symbol}={expected}\n" in text


def _assert_failure(process, output: Path, *messages: str) -> str:
    text = transcript(process)
    assert process.returncode != 0, text
    assert "NOT INSTALLED DUE TO ERRORS" in text, text
    assert not output.exists(), text
    for message in messages:
        assert message in text, text
    return text


def test_generated_preflight_artifacts_exist_and_match_the_catalog() -> None:
    catalog = load_catalog(CATALOG_PATH)

    assert SCHEMA.read_text(encoding="utf-8") == render_weidu_config_schema(catalog)
    assert SELECTION.read_text(encoding="utf-8") == render_weidu_selection(catalog)
    assert HARNESS.is_file()


def test_weidu_is_recent_enough() -> None:
    assert weidu_version() >= MIN_WEIDU_VERSION


@pytest.mark.parametrize(
    ("kind", "path"),
    [("TPA", SCHEMA), ("TPA", SELECTION), ("TP2", HARNESS)],
    ids=lambda value: value.name if isinstance(value, Path) else value,
)
def test_generated_preflight_and_harness_parse(kind: str, path: Path) -> None:
    process = parse_check(kind, path)
    assert process.returncode == 0, transcript(process)


def test_untouched_production_config_resolves_to_all_applicable_changes(
    tmp_path: Path,
) -> None:
    catalog = load_catalog(CATALOG_PATH)
    process, output, _ = _run(tmp_path, catalog, SETTINGS.read_text(encoding="utf-8"))

    _assert_success(process, output, catalog, resolve(catalog, {}).selected_ids)


def test_global_all_off_disables_every_change(tmp_path: Path) -> None:
    catalog = load_catalog(CATALOG_PATH)
    config = _set_assignment(SETTINGS.read_text(encoding="utf-8"), "sr_default", 0)
    process, output, _ = _run(tmp_path, catalog, config)

    _assert_success(process, output, catalog, ())


@pytest.mark.parametrize("newline", ["\n", "\r\n", ""])
def test_literal_inheritance_syntax_accepts_lf_crlf_and_no_final_newline(
    tmp_path: Path, newline: str
) -> None:
    catalog = _catalog(_change("spell", "sr_spell"))
    config = _config(catalog)
    if newline == "\r\n":
        config = config.replace("\n", "\r\n")
    elif newline == "":
        config = config.rstrip("\n")

    process, output, _ = _run(tmp_path, catalog, config)

    _assert_success(process, output, catalog, ("spell",))


@pytest.mark.parametrize(
    ("values", "enabled"),
    [
        ({"sr_default": 1}, True),
        ({"sr_default": 0, "sr_arcane_default": 1}, True),
        (
            {
                "sr_default": 1,
                "sr_arcane_default": 0,
                "sr_arcane_level_1_default": 1,
            },
            True,
        ),
        (
            {
                "sr_default": 1,
                "sr_arcane_default": 1,
                "sr_arcane_level_1_default": 0,
            },
            False,
        ),
        (
            {
                "sr_default": 0,
                "sr_arcane_default": 0,
                "sr_arcane_level_1_default": 0,
                "sr_spell": 1,
            },
            True,
        ),
    ],
)
def test_weidu_uses_leaf_level_tradition_global_precedence(
    tmp_path: Path, values: dict[str, int], enabled: bool
) -> None:
    catalog = _catalog(_change("spell", "sr_spell"))
    config = _config(catalog)
    for key, value in values.items():
        config = _set_assignment(config, key, value)

    process, output, _ = _run(tmp_path, catalog, config)

    _assert_success(process, output, catalog, ("spell",) if enabled else ())


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    [
        ("install_tobex", "0", "install_tobex: expected exactly 1"),
        ("sr_spell", "2", "sr_spell: expected -1, 0, or 1"),
        ("sr_spell", "yes", "sr_spell: expected -1, 0, or 1"),
        ("sr_default", "-1", "sr_default: expected 0 or 1"),
    ],
)
def test_invalid_values_fail_before_the_mutation_sentinel(
    tmp_path: Path, setting: str, value: str, message: str
) -> None:
    catalog = _catalog(_change("spell", "sr_spell"))
    config = _set_assignment(_config(catalog), setting, value)

    process, output, _ = _run(tmp_path, catalog, config)

    _assert_failure(process, output, message)


@pytest.mark.parametrize(
    ("mutation", "messages"),
    [
        (
            lambda source: re.sub(
                r"^sr_spell\s*=.*(?:\n|$)", "", source, flags=re.MULTILINE
            ),
            ("missing setting sr_spell",),
        ),
        (
            lambda source: source + "sr_unknown = 1\n",
            ("unrecognized or malformed non-comment line",),
        ),
        (
            lambda source: source + "sr_spell = 0\n",
            ("duplicate setting sr_spell",),
        ),
        (
            lambda source: _set_assignment(source, "sr_config_schema", 999),
            ("stale or malformed sr_config_schema",),
        ),
        (
            lambda source: re.sub(
                r"^SPRINT sr_catalog_fingerprint .*$",
                "SPRINT sr_catalog_fingerprint ~" + "0" * 64 + "~",
                source,
                flags=re.MULTILINE,
            ),
            ("stale or malformed sr_catalog_fingerprint",),
        ),
    ],
)
def test_raw_schema_failures_are_rejected_before_assignments_are_used(
    tmp_path: Path, mutation, messages: tuple[str, ...]
) -> None:
    catalog = _catalog(_change("spell", "sr_spell"))

    process, output, _ = _run(tmp_path, catalog, mutation(_config(catalog)))

    _assert_failure(process, output, *messages)


def test_executable_config_content_is_never_executed(tmp_path: Path) -> None:
    catalog = _catalog(_change("spell", "sr_spell"))
    injected_source = tmp_path / "injected-source.txt"
    injected_source.write_text("unsafe", encoding="ascii")
    injected_output = tmp_path / "CONFIG-WAS-EXECUTED.txt"
    config = _config(catalog) + (
        f"COPY ~{injected_source.as_posix()}~ ~{injected_output.as_posix()}~\n"
    )

    process, output, config_path = _run(tmp_path, catalog, config)

    _assert_failure(process, output, "unrecognized or malformed non-comment line")
    assert not injected_output.exists()
    assert config_path.read_text(encoding="utf-8") == config


def test_multiple_raw_errors_are_aggregated_before_failure(tmp_path: Path) -> None:
    catalog = _catalog(_change("spell", "sr_spell"))
    config = _config(catalog)
    config = _set_assignment(config, "sr_config_schema", 999)
    config = config + "sr_spell = 0\nsr_unknown = 1\n"

    process, output, _ = _run(tmp_path, catalog, config)

    _assert_failure(
        process,
        output,
        "stale or malformed sr_config_schema",
        "duplicate setting sr_spell",
        "unrecognized or malformed non-comment line",
    )


def test_hard_dependency_closes_when_inherited_but_rejects_explicit_veto(
    tmp_path: Path,
) -> None:
    catalog = _catalog(
        _change("a", "sr_a", requires=["b"]),
        _change("b", "sr_b"),
    )
    config = _set_assignment(_config(catalog), "sr_default", 0)
    config = _set_assignment(config, "sr_a", 1)
    process, output, _ = _run(tmp_path, catalog, config, run_name="closure")
    _assert_success(process, output, catalog, ("a", "b"))

    veto = _set_assignment(config, "sr_b", 0)
    process, output, _ = _run(tmp_path, catalog, veto, run_name="veto")
    _assert_failure(
        process,
        output,
        "sr_a requires sr_b, but sr_b is explicitly disabled",
    )


def test_atomic_family_closes_and_rejects_an_explicit_veto(tmp_path: Path) -> None:
    catalog = _catalog(
        _change("a", "sr_a", atomic_group="paired"),
        _change("b", "sr_b", atomic_group="PAIRED"),
    )
    config = _set_assignment(_config(catalog), "sr_default", 0)
    config = _set_assignment(config, "sr_a", 1)
    process, output, _ = _run(tmp_path, catalog, config, run_name="closure")
    _assert_success(process, output, catalog, ("a", "b"))

    veto = _set_assignment(config, "sr_b", 0)
    process, output, _ = _run(tmp_path, catalog, veto, run_name="veto")
    _assert_failure(
        process,
        output,
        "atomic family 'paired' requires sr_b, but sr_b is explicitly disabled",
    )


def test_conflicts_are_rejected_after_dependency_closure(tmp_path: Path) -> None:
    catalog = _catalog(
        _change("a", "sr_a", requires=["b"]),
        _change("b", "sr_b", conflicts=["c"]),
        _change("c", "sr_c"),
    )
    config = _set_assignment(_config(catalog), "sr_default", 0)
    config = _set_assignment(config, "sr_a", 1)
    config = _set_assignment(config, "sr_c", 1)

    process, output, _ = _run(tmp_path, catalog, config)

    _assert_failure(process, output, "sr_b conflicts with sr_c")


def test_soft_edges_are_informational_and_never_force_selection(
    tmp_path: Path,
) -> None:
    catalog = _catalog(
        _change("a", "sr_a", soft_requires=["b"]),
        _change("b", "sr_b"),
    )
    config = _set_assignment(_config(catalog), "sr_default", 0)
    config = _set_assignment(config, "sr_a", 1)

    process, output, _ = _run(tmp_path, catalog, config)

    _assert_success(process, output, catalog, ("a",))


def test_explicitly_enabled_unavailable_change_is_rejected(tmp_path: Path) -> None:
    catalog = _catalog(_change("ee_only", "sr_ee_only", games=["bg2ee"]))
    config = _set_assignment(_config(catalog), "sr_ee_only", 1)

    process, output, _ = _run(tmp_path, catalog, config, game="soa")

    _assert_failure(
        process,
        output,
        "sr_ee_only is explicitly enabled but unavailable on game 'soa'",
    )


def test_generated_flags_are_collision_free_and_published_to_the_caller() -> None:
    catalog = _catalog(
        _change("arcane.level1.a-b", "sr_a"),
        _change("arcane_level1_a_b", "sr_b"),
    )
    rendered = render_weidu_selection(catalog)

    assert feature_symbols(catalog) == {
        "arcane.level1.a-b": "sr_feature_000001",
        "arcane_level1_a_b": "sr_feature_000002",
    }
    function, publisher = rendered.split(
        "DEFINE_ACTION_MACRO sr_config_preflight_component_zero", 1
    )
    function_returns = function.split("  RET\n", 1)[1].split("BEGIN", 1)[0]
    publisher_returns = publisher.split("    RET\n", 1)[1].split("  END", 1)[0]
    for symbol in ("sr_feature_000001", "sr_feature_000002"):
        assert f"    {symbol}\n" in function_returns
        assert f"      {symbol}\n" in publisher_returns


def test_only_component_zero_invokes_preflight_and_it_precedes_tobex_mutation() -> None:
    source = SETUP.read_text(encoding="utf-8")
    always, after_always = source.split("END", 1)
    component_zero, remainder = after_always.split("/*------Deva", 1)

    assert "INCLUDE ~spell_rev/generated/config_schema.tpa~" in always
    assert "INCLUDE ~spell_rev/generated/selection.tpa~" in always
    assert "PATCH_INCLUDE ~spell_rev/settings.ini~" not in always
    assert source.count("LAM sr_config_preflight_component_zero") == 1
    assert component_zero.index("LAM sr_config_preflight_component_zero") < (
        component_zero.index("// ToBEx")
    )
    assert "LAM sr_config_preflight_component_zero" not in remainder


def test_component_zero_maps_the_game_without_an_unresolved_placeholder() -> None:
    source = SETUP.read_text(encoding="utf-8")
    component_zero = source.split("DESIGNATED 0", 1)[1].split("// ToBEx", 1)[0]
    games = (
        "eet",
        "bgt",
        "tutu_totsc",
        "tutu",
        "bg2ee",
        "bgee",
        "iwdee",
        "tob",
        "soa",
    )

    assert "%SOURCE_GAME%" not in component_zero
    positions = [component_zero.index(f"GAME_IS ~{game}~") for game in games]
    assert positions == sorted(positions)
    assert positions[-1] < component_zero.index("LAM sr_config_preflight_component_zero")


@pytest.mark.parametrize("component", [10, 20, 30, 55, 65, 70])
def test_invalid_config_does_not_block_independent_components(
    tmp_path: Path, component: int
) -> None:
    catalog = _catalog(_change("spell", "sr_spell"))
    config = _config(catalog) + "FAIL ~must not execute~\n"

    process, output, _ = _run(
        tmp_path,
        catalog,
        config,
        component=component,
        run_name=f"component-{component}",
    )

    assert_installed(process)
    assert output.read_text(encoding="ascii").startswith(
        "install_tobex=%install_tobex%\n"
    )


def test_component_60_uses_installed_component_zero_not_the_current_config(
    tmp_path: Path,
) -> None:
    catalog = _catalog(_change("spell", "sr_spell"))
    valid = _config(catalog)
    process, output, config_path = _run(
        tmp_path, catalog, valid, component=0, run_name="component-60"
    )
    _assert_success(process, output, catalog, ("spell",))
    config_path.write_text(valid + "FAIL ~must not execute~\n", encoding="utf-8")

    process, output, _ = _run(
        tmp_path,
        catalog,
        config_path.read_text(encoding="utf-8"),
        component=60,
        run_name="component-60",
    )

    assert_installed(process)
    assert output.read_text(encoding="ascii").startswith(
        "install_tobex=%install_tobex%\n"
    )


def test_invalid_current_config_does_not_block_component_zero_uninstall(
    tmp_path: Path,
) -> None:
    catalog = _catalog(_change("spell", "sr_spell"))
    valid = _config(catalog)
    process, output, config_path = _run(
        tmp_path, catalog, valid, component=0, run_name="uninstall"
    )
    _assert_success(process, output, catalog, ("spell",))
    config_path.write_text(valid + "FAIL ~must not execute~\n", encoding="utf-8")
    args = [
        str(HARNESS),
        "--nogame",
        "--force-uninstall-list",
        "0",
    ]
    for value in (
        tmp_path / "generated" / "config_schema.tpa",
        tmp_path / "generated" / "selection.tpa",
        config_path,
        Path("bg2ee"),
        tmp_path / "sentinel-template.txt",
        output,
    ):
        args.extend(("--args", value.as_posix()))
    args.extend(("--no-exit-pause", "--quick-log"))

    process = run_weidu(args, cwd=tmp_path / "uninstall")

    text = transcript(process)
    assert process.returncode == 0, text
    assert "SUCCESSFULLY REMOVED" in text, text
    assert not output.exists()


def test_synthetic_catalog_fingerprint_is_embedded_exactly() -> None:
    catalog = _catalog(_change("spell", "sr_spell"))
    fingerprint = catalog_fingerprint(catalog)
    schema = render_weidu_config_schema(catalog)

    assert fingerprint in schema
    assert "PATCH_INCLUDE" not in schema
    assert asdict(catalog)["schema_version"] == 1
