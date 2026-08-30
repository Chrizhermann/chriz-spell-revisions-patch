from __future__ import annotations

import hashlib
import importlib
import json
import os
import stat
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from tools.sr_config.__main__ import main
from tools.sr_config.catalog import Catalog
from tools.sr_config.generate import (
    BEGIN_MARKER,
    END_MARKER,
    GenerationError,
    catalog_fingerprint,
    generate,
    render_config,
    render_html_catalog,
    render_html_document,
    render_markdown_catalog,
)
from tools.sr_config.text import TraError, load_english_tra, parse_tra


UPSTREAM_COMMIT = "af1dedb6d211f86ad7a321d4080e46c748e8abac"


def _catalog(
    *,
    display_name: str = "Magic | Missile <Revised>",
    span_end: str | None = "BUT_ONLY",
) -> Catalog:
    raw: dict[str, Any] = {
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
            },
            {
                "id": "arcane",
                "setting": "sr_arcane_default",
                "name": "Arcane spells",
                "default": -1,
                "parent": "global",
            },
            {
                "id": "arcane.level1",
                "setting": "sr_arcane_level_1_default",
                "name": "Arcane level 1",
                "default": -1,
                "parent": "arcane",
            },
        ],
        "changes": [
            {
                "id": "arcane.level1.magic_missile",
                "setting": "sr_wizard_magic_missile",
                "display_name": display_name,
                "default": -1,
                "group": "arcane.level1",
                "component": 0,
                "games": ["bg2ee", "eet"],
                "name_ref": "@1",
                "name_fallback": None,
                "description_ref": "@2",
                "member_refs": [],
                "source_spans": [
                    {
                        "path": "spell_rev/components/main_component.tpa",
                        "start": "COPY ~a~",
                        "end": span_end,
                        "sha256": "a" * 64,
                    }
                ],
                "resources": [],
                "atomic_group": "missile.family",
                "requires": [],
                "conflicts": [],
                "soft_requires": [],
                "processors": [],
                "documentation_only_reason": None,
            }
        ],
        "infrastructure": [],
    }
    return Catalog.from_dict(raw)


def _texts() -> dict[str, str]:
    return {
        "@1": "Magic | Missile <name>",
        "@2": "Deals <damage> & escapes | pipes. `code` [link](target) *bold*.",
    }


def _composite_catalog() -> Catalog:
    raw = json.loads(json.dumps(asdict(_catalog())))
    record = raw["changes"][0]
    record["display_name"] = "Shared | Deflection <bundle>"
    record["name_ref"] = None
    record["name_fallback"] = None
    record["description_ref"] = None
    record["member_refs"] = [
        {
            "source_spell": "SPWI101",
            "level": 1,
            "role": "active",
            "name_ref": "@3",
            "name_fallback": None,
            "description_ref": "@4",
        },
        {
            "source_spell": "SPWI205",
            "level": 2,
            "role": "game_compatibility_slot",
            "name_ref": None,
            "name_fallback": {
                "kind": "game_resource",
                "resource": "SPWI205",
            },
            "description_ref": "@5",
        },
    ]
    return Catalog.from_dict(raw)


def _composite_texts() -> dict[str, str]:
    return {
        "@3": "First | Name <one>",
        "@4": "First & description `one`.",
        "@5": "Second | description <two>.",
    }


def test_parse_tra_supports_multiline_tildes_and_quoted_actual_syntax() -> None:
    source = '@1 = ~Name~\n@2=~First line\nSecond line~\n@23000 = "Imprisonment ended."\n'

    assert parse_tra(source, source_name="sample.tra") == {
        "@1": "Name",
        "@2": "First line\nSecond line",
        "@23000": "Imprisonment ended.",
    }


def test_parse_tra_supports_sound_refs_and_trailing_comments() -> None:
    source = (
        "@1=~Spoken~ [voice]\n"
        "@2=~Block~ /* trailing block comment */\n"
        "@3=~Both~ [sound_01] /* block */ // line comment\n"
        "@4=~Multiline comment~ /* first\nsecond */\n"
        "@5=~Comment first~ /* ignored by WeiDU */ [after]\n"
        "@6=~Empty sound is accepted by WeiDU~ []\n"
    )

    assert parse_tra(source, source_name="suffixes.tra") == {
        "@1": "Spoken",
        "@2": "Block",
        "@3": "Both",
        "@4": "Multiline comment",
        "@5": "Comment first",
        "@6": "Empty sound is accepted by WeiDU",
    }


def test_parse_tra_accepts_cr_only_assignment_separators() -> None:
    assert parse_tra("@1=~one~\r@2=~two~\r", source_name="cr-only.tra") == {
        "@1": "one",
        "@2": "two",
    }


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_parse_tra_line_comments_end_at_every_supported_newline(
    newline: str,
) -> None:
    source = (
        f"// leading comment{newline}"
        f"@1=~one~ // trailing comment{newline}"
        f"@2=~two~{newline}"
    )

    assert parse_tra(source, source_name="comments.tra") == {
        "@1": "one",
        "@2": "two",
    }


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_parse_tra_accepts_sound_reference_after_comments_and_blank_lines(
    newline: str,
) -> None:
    source = (
        f"@1=~one~{newline}"
        f"{newline}"
        f"// sound follows{newline}"
        f"/* still part of the entry */{newline}"
        f" [voice]{newline}"
        f"@2=~two~{newline}"
    )

    assert parse_tra(source, source_name="multiline-sound.tra") == {
        "@1": "one",
        "@2": "two",
    }


def test_parse_tra_cr_only_diagnostics_count_physical_lines() -> None:
    source = "// first line\r@1=~one~\rorphan content\r"

    with pytest.raises(TraError, match=r"cr-errors\.tra:3: unexpected content"):
        parse_tra(source, source_name="cr-errors.tra")


def test_tra_duplicate_identity_is_numeric() -> None:
    with pytest.raises(TraError, match="duplicate reference @1"):
        parse_tra("@01=~one~\n@1=~two~\n", source_name="duplicate.tra")


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("@1=~one~\n@1=~two~\n", "duplicate reference @1"),
        ("@x=~bad~\n", "malformed assignment"),
        ("@1 one\n", "malformed assignment"),
        ("@1=~unterminated\n", "unterminated '~' value for @1"),
        ('@1="unterminated\n', "unterminated '\"' value for @1"),
        ("@1=~value~ [unterminated\n", "unterminated sound reference"),
        ("@1=~value~ /* unterminated\n", "unterminated block comment"),
        ("@1=~value~ arbitrary\n", "unexpected content after @1"),
        ("@1=~value~ [voice] arbitrary\n", "unexpected content after @1"),
        ("orphan content\n", "unexpected content"),
    ],
)
def test_parse_tra_fails_closed(source: str, message: str) -> None:
    with pytest.raises(TraError, match=message):
        parse_tra(source, source_name="broken.tra")


def test_load_english_tra_rejects_duplicates_across_files(tmp_path: Path) -> None:
    language = tmp_path / "spell_rev" / "languages" / "english"
    language.mkdir(parents=True)
    (language / "arcane.tra").write_text("@1=~one~\n", encoding="utf-8")
    (language / "divine.tra").write_text("@1=~two~\n", encoding="utf-8")
    (language / "setup.tra").write_text("@2=~three~\n", encoding="utf-8")

    with pytest.raises(TraError, match="duplicate reference @1"):
        load_english_tra(tmp_path)


def test_current_english_tra_files_parse_and_references_must_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    texts = load_english_tra(root)

    assert texts["@401"] == "Grease"
    assert texts["@1"] == "Bless"
    assert texts["@9996"] == "Spell Revisions"
    assert len(texts) == 862
    assert texts["@337"] == ""
    with pytest.raises(TraError, match="missing TRA reference @2"):
        render_markdown_catalog(_catalog(), {"@1": "only the name"})


def test_fingerprint_is_canonical_semantic_json_not_source_formatting() -> None:
    raw = json.loads(
        json.dumps(
            {
                "schema_version": 1,
                "upstream": {"tag": "v4.21", "commit": UPSTREAM_COMMIT},
                "migration": {"complete": False, "installer_source": "x.tpa"},
                "groups": [
                    {
                        "id": "global",
                        "setting": "sr_default",
                        "name": "All",
                        "default": 1,
                        "parent": None,
                    }
                ],
                "changes": [],
                "infrastructure": [],
            }
        )
    )
    catalog = Catalog.from_dict(raw)
    canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    assert catalog_fingerprint(catalog) == hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def test_fingerprint_includes_member_order_refs_and_fallback_with_schema_one() -> None:
    baseline = _composite_catalog()
    raw = json.loads(json.dumps(asdict(baseline)))

    reordered = json.loads(json.dumps(raw))
    reordered["changes"][0]["member_refs"].reverse()
    changed_ref = json.loads(json.dumps(raw))
    changed_ref["changes"][0]["member_refs"][0]["description_ref"] = "@99"
    changed_fallback = json.loads(json.dumps(raw))
    changed_fallback["changes"][0]["member_refs"][1]["name_fallback"][
        "resource"
    ] = "SPWI206"
    compact = json.loads(json.dumps(raw, separators=(",", ":")))
    pretty = json.loads(json.dumps(raw, indent=4, ensure_ascii=False))

    fingerprints = {
        catalog_fingerprint(baseline),
        catalog_fingerprint(Catalog.from_dict(reordered)),
        catalog_fingerprint(Catalog.from_dict(changed_ref)),
        catalog_fingerprint(Catalog.from_dict(changed_fallback)),
    }
    assert baseline.schema_version == 1
    assert len(fingerprints) == 4
    assert catalog_fingerprint(Catalog.from_dict(compact)) == catalog_fingerprint(
        Catalog.from_dict(pretty)
    )


def test_config_preserves_tobex_prefix_and_emits_exact_metadata_and_defaults() -> None:
    existing = (
        "// Main Component   \r\n"
        "install_tobex = 1 // retain this comment\r\n\r\n"
    )
    catalog = _catalog()
    fingerprint = catalog_fingerprint(catalog)

    rendered = render_config(catalog, existing, newline="\r\n")

    assert rendered.startswith(existing)
    assignments = [
        line for line in rendered.splitlines() if line and not line.startswith("//")
    ]
    assert assignments[0] == "install_tobex = 1 // retain this comment"
    assert assignments[1] == "sr_config_schema = 1"
    assert assignments[2] == f"SPRINT sr_catalog_fingerprint ~{fingerprint}~"
    assert "sr_default = 1" in assignments
    assert "sr_arcane_default = -1" in assignments
    assert "sr_arcane_level_1_default = -1" in assignments
    assert "sr_wizard_magic_missile = -1" in assignments
    assert rendered.count("\r\n") == rendered.count("\n")


@pytest.mark.parametrize(
    "assignment",
    [
        "install_tobex = 1 garbage",
        "install_tobex = 1 sr_default = 0",
        "install_tobex = 1 /* not a line comment */",
        "install_tobex = 10",
    ],
)
def test_config_rejects_trailing_tokens_on_tobex_assignment(
    assignment: str,
) -> None:
    with pytest.raises(GenerationError, match="first non-comment settings assignment"):
        render_config(_catalog(), f"// Main\n{assignment}\n", newline="\n")


def test_docs_resolve_tra_and_escape_markdown_and_html() -> None:
    catalog = _catalog()

    markdown = render_markdown_catalog(catalog, _texts())
    html_region = render_html_catalog(catalog, _texts(), newline="\r\n")

    assert "Magic \\| Missile &lt;name&gt;" in markdown
    assert "Deals &lt;damage&gt; &amp; escapes \\| pipes." in markdown
    assert r"\`code\` \[link\]\(target\) \*bold\*" in markdown
    assert "`sr_wizard_magic_missile`" in markdown
    assert "`sr_feature_000001`" in markdown
    assert "v4.21 (`af1dedb6d211f86ad7a321d4080e46c748e8abac`)" in markdown
    assert "Magic | Missile &lt;name&gt;" in html_region
    assert "Deals &lt;damage&gt; &amp; escapes | pipes." in html_region
    assert html_region.count('id="spell_changes"') == 1


def test_singleton_fallback_renders_game_name_note_before_description() -> None:
    raw = json.loads(json.dumps(asdict(_catalog(display_name="Righteous Fury"))))
    record = raw["changes"][0]
    record["name_ref"] = None
    record["name_fallback"] = {
        "kind": "game_resource",
        "resource": "SPPR311",
    }
    catalog = Catalog.from_dict(raw)
    texts = {"@2": "Resolved <description>."}

    markdown = render_markdown_catalog(catalog, texts)
    html_region = render_html_catalog(catalog, texts, newline="\n")

    rendered_description = (
        "Name retained from installed game resource SPPR311. "
        "Resolved &lt;description&gt;."
    )
    assert "| Righteous Fury | `sr_wizard_magic_missile` |" in markdown
    assert "Game\\-provided name \\(SPPR311\\)" not in markdown
    assert rendered_description in markdown
    assert markdown.index("Name retained") < markdown.index("Resolved &lt;description&gt;")
    assert "<tr><td>Righteous Fury</td><td>sr_wizard_magic_missile</td>" in html_region
    assert "Game-provided name (SPPR311)" not in html_region
    assert rendered_description in html_region


def test_composite_docs_render_one_neutral_main_row_and_ordered_member_details() -> None:
    catalog = _composite_catalog()
    texts = _composite_texts()

    markdown = render_markdown_catalog(catalog, texts)
    html_region = render_html_catalog(catalog, texts, newline="\r\n")

    neutral = "One atomic option controls 2 member spells listed below."
    assert neutral in markdown
    assert neutral in html_region
    assert "Shared \\| Deflection &lt;bundle&gt;" in markdown
    assert "Atomic bundle member descriptions" in markdown
    assert "controlled together" in markdown
    assert "not separate options" in markdown
    assert markdown.index("`SPWI101`") < markdown.index("`SPWI205`")
    assert "1 / active" in markdown
    assert r"2 / game\_compatibility\_slot" in markdown
    assert "First \\| Name &lt;one&gt;" in markdown
    assert "First &amp; description \\`one\\`." in markdown
    assert r"Game\-provided name \(SPWI205\)" in markdown
    assert "Second \\| description &lt;two&gt;." in markdown

    assert "Atomic bundle member descriptions" in html_region
    assert "controlled together" in html_region
    assert "not separate options" in html_region
    assert html_region.index("SPWI101") < html_region.index("SPWI205")
    assert "First | Name &lt;one&gt;" in html_region
    assert "First &amp; description `one`." in html_region
    assert "Game-provided name (SPWI205)" in html_region
    assert "Second | description &lt;two&gt;." in html_region


def test_composite_keeps_exactly_one_setting_flag_and_main_row_per_change() -> None:
    catalog = _composite_catalog()
    markdown = render_markdown_catalog(catalog, _composite_texts())
    html_region = render_html_catalog(catalog, _composite_texts(), newline="\n")
    config = render_config(catalog, "install_tobex = 1\n", newline="\n")

    assert config.splitlines().count("sr_wizard_magic_missile = -1") == 1
    assert config.count("internal flag sr_feature_000001") == 1
    main_markdown = markdown.split("## Atomic bundle member descriptions", 1)[0]
    assert main_markdown.count("`sr_wizard_magic_missile`") == 1
    assert main_markdown.count("`sr_feature_000001`") == 1
    main_html = html_region.split("<h4>Atomic bundle member descriptions</h4>", 1)[0]
    assert main_html.count("sr_wizard_magic_missile") == 1
    assert main_html.count("sr_feature_000001") == 1
    main_body = main_html.split("  <tbody>", 1)[1].split("  </tbody>", 1)[0]
    assert main_body.count("    <tr>") == 1


def test_eof_source_span_has_unambiguous_generated_provenance() -> None:
    eof_catalog = _catalog(span_end=None)

    markdown = render_markdown_catalog(eof_catalog, _texts())

    assert "COPY ~a~ .. EOF" in markdown
    assert ".. None" not in markdown
    assert catalog_fingerprint(eof_catalog) != catalog_fingerprint(_catalog())


def test_html_non_latin_text_is_encoded_safely_for_iso_8859_1() -> None:
    catalog = _catalog(display_name="Magic — 雪")
    texts = {"@1": "Magic — 雪", "@2": "Description U0001f642"}

    region = render_html_catalog(catalog, texts, newline="\r\n")

    assert "&#" in region
    region.encode("iso-8859-1")


def test_legacy_html_is_bootstrapped_once_and_preserves_outside_bytes() -> None:
    legacy = (
        b"prefix\r\n<div class=\"section\">\r\n  <p>\r\n"
        b"    <a id=\"spell_changes\"></a><strong>Overview of Divine Spell Changes</strong>\r\n"
        b"  </p>\r\n  <p>Overview of Arcane Spell Changes</p>\r\n"
        b"</div>\r\n\r\n<h2>Contact Information</h2>\r\nsuffix\r\n"
    )
    region = '<p><a id="spell_changes"></a>new</p>\r\n'

    rendered = render_html_document(legacy, region)

    assert rendered.startswith(b"prefix\r\n<div class=\"section\">\r\n")
    assert rendered.endswith(
        b"</div>\r\n\r\n<h2>Contact Information</h2>\r\nsuffix\r\n"
    )
    assert rendered.count(BEGIN_MARKER.encode("ascii")) == 1
    assert rendered.count(END_MARKER.encode("ascii")) == 1
    assert rendered.count(b'id="spell_changes"') == 1


@pytest.mark.parametrize(
    "document",
    [
        b"no marker and no legacy overview",
        (BEGIN_MARKER + "\nonly begin").encode("ascii"),
        (END_MARKER + "\n" + BEGIN_MARKER).encode("ascii"),
        (BEGIN_MARKER + BEGIN_MARKER + END_MARKER).encode("ascii"),
        (BEGIN_MARKER + END_MARKER + END_MARKER).encode("ascii"),
    ],
)
def test_html_marker_errors_fail_closed(document: bytes) -> None:
    with pytest.raises(GenerationError):
        render_html_document(document, '<a id="spell_changes"></a>')


def _seed_repo(root: Path, *, newline: str = "\n") -> None:
    language = root / "spell_rev" / "languages" / "english"
    language.mkdir(parents=True)
    for filename, content in (
        ("arcane.tra", "@1=~Magic Missile~\n@2=~Description~\n"),
        ("divine.tra", "@3=~Bless~\n"),
        ("setup.tra", "@4=~Setup~\n"),
    ):
        (language / filename).write_text(content, encoding="utf-8", newline="")
    catalog_path = root / "spell_rev" / "catalog" / "changes.json"
    catalog_path.parent.mkdir(parents=True)
    raw = json.loads(json.dumps(_catalog(), default=lambda value: value.__dict__))
    # Dataclass serialization above retains tuples and nested records but produces
    # exactly the strict schema shape after a JSON round trip.
    catalog_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    settings = root / "spell_rev" / "settings.ini"
    settings.write_bytes(
        ("// Main Component" + newline + "install_tobex = 1 // keep" + newline).encode()
    )
    html_path = root / "spell_rev" / "readme-spell_rev.html"
    html_path.write_bytes(
        (
            "prefix"
            + newline
            + '<div class="section">'
            + newline
            + "  <p>"
            + newline
            + '    <a id="spell_changes"></a><strong>Overview of Divine Spell Changes</strong>'
            + newline
            + "  </p>"
            + newline
            + "  <p>Overview of Arcane Spell Changes</p>"
            + newline
            + "</div>"
            + newline
            + newline
            + "<h2>Contact Information</h2>"
            + newline
            + "suffix"
            + newline
        ).encode("iso-8859-1")
    )


def test_generate_is_idempotent_and_check_writes_nothing(tmp_path: Path) -> None:
    _seed_repo(tmp_path, newline="\r\n")

    first = generate(tmp_path)
    after_first = {path: path.read_bytes() for path in first.paths}
    second = generate(tmp_path)
    check = generate(tmp_path, check=True)

    assert first.changed
    assert not second.changed
    assert not check.changed
    assert {path: path.read_bytes() for path in first.paths} == after_first
    assert (tmp_path / "spell_rev" / "settings.ini").read_bytes().count(b"\r\n") > 0
    assert (tmp_path / "spell_rev" / "readme-spell_rev.html").read_bytes().count(
        b"\r\n"
    ) > 0
    assert (tmp_path / "docs" / "spell-revisions-change-catalog.md").exists()


def test_check_reports_stable_diff_without_writing(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    generate(tmp_path)
    target = tmp_path / "spell_rev" / "settings.ini"
    target.write_text(target.read_text(encoding="utf-8") + "stale = 1\n", encoding="utf-8")
    before = target.read_bytes()

    first = generate(tmp_path, check=True)
    second = generate(tmp_path, check=True)

    assert first.changed and second.changed
    assert first.diff == second.diff
    assert "--- spell_rev/settings.ini (current)" in first.diff
    assert "+++ spell_rev/settings.ini (generated)" in first.diff
    assert target.read_bytes() == before


def test_generation_validates_every_output_before_writing(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    settings = tmp_path / "spell_rev" / "settings.ini"
    before = settings.read_bytes()
    html_path = tmp_path / "spell_rev" / "readme-spell_rev.html"
    html_path.write_bytes(b"broken markerless generated document")

    with pytest.raises(GenerationError):
        generate(tmp_path)

    assert settings.read_bytes() == before
    assert not (tmp_path / "docs" / "spell-revisions-change-catalog.md").exists()


def test_generate_cli_exposes_write_and_check_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["generate"]) == 0
    assert "generated:" in capsys.readouterr().out
    target = tmp_path / "spell_rev" / "settings.ini"
    target.write_text(target.read_text(encoding="utf-8") + "stale = 1\n", encoding="utf-8")
    before = target.read_bytes()

    assert main(["generate", "--check"]) == 1
    output = capsys.readouterr()
    assert "--- spell_rev/settings.ini (current)" in output.out
    assert "generated files are stale" in output.err
    assert target.read_bytes() == before


def test_generation_rolls_back_every_target_if_publication_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_repo(tmp_path)
    settings = tmp_path / "spell_rev" / "settings.ini"
    html_path = tmp_path / "spell_rev" / "readme-spell_rev.html"
    before_settings = settings.read_bytes()
    before_html = html_path.read_bytes()
    module = importlib.import_module("tools.sr_config.generate")
    real_replace = module.os.replace
    publication_calls = 0
    failed = False

    def fail_second_publication(source: object, target: object) -> None:
        nonlocal publication_calls, failed
        if str(source).endswith(".tmp") and not str(source).endswith(".rollback.tmp"):
            publication_calls += 1
            if publication_calls == 2 and not failed:
                failed = True
                raise OSError("simulated publication failure")
        real_replace(source, target)

    monkeypatch.setattr(module.os, "replace", fail_second_publication)

    with pytest.raises(GenerationError, match="transaction failed"):
        generate(tmp_path)

    assert settings.read_bytes() == before_settings
    assert html_path.read_bytes() == before_html
    assert not (tmp_path / "docs" / "spell-revisions-change-catalog.md").exists()


def test_failed_rollback_preserves_backup_and_reports_exact_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_repo(tmp_path)
    settings = tmp_path / "spell_rev" / "settings.ini"
    before_settings = settings.read_bytes()
    module = importlib.import_module("tools.sr_config.generate")
    real_replace = module.os.replace
    publication_calls = 0

    def fail_publication_and_rollback(source: object, target: object) -> None:
        nonlocal publication_calls
        source_text = str(source)
        if source_text.endswith(".rollback.tmp"):
            raise OSError("simulated rollback failure")
        if source_text.endswith(".tmp"):
            publication_calls += 1
            if publication_calls == 2:
                raise OSError("simulated publication failure")
        real_replace(source, target)

    monkeypatch.setattr(module.os, "replace", fail_publication_and_rollback)

    with pytest.raises(GenerationError) as caught:
        generate(tmp_path)

    backups = list(tmp_path.rglob("*.rollback.tmp"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == before_settings
    assert str(settings) in str(caught.value)
    assert str(backups[0]) in str(caught.value)
    assert "simulated publication failure" in str(caught.value)
    assert "simulated rollback failure" in str(caught.value)


def test_cleanup_failure_does_not_mask_primary_transaction_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_repo(tmp_path)
    module = importlib.import_module("tools.sr_config.generate")
    real_replace = module.os.replace
    real_unlink = type(tmp_path).unlink
    publication_calls = 0
    cleanup_failed = False

    def fail_second_publication(source: object, target: object) -> None:
        nonlocal publication_calls
        source_text = str(source)
        if source_text.endswith(".tmp") and not source_text.endswith(".rollback.tmp"):
            publication_calls += 1
            if publication_calls == 2:
                raise OSError("primary publication failure")
        real_replace(source, target)

    def fail_one_cleanup(
        path: Path, missing_ok: bool = False
    ) -> None:
        nonlocal cleanup_failed
        if not cleanup_failed and str(path).endswith(".tmp"):
            cleanup_failed = True
            raise OSError("secondary cleanup failure")
        real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(module.os, "replace", fail_second_publication)
    monkeypatch.setattr(type(tmp_path), "unlink", fail_one_cleanup)

    with pytest.raises(GenerationError) as caught:
        generate(tmp_path)

    assert "primary publication failure" in str(caught.value)
    assert "secondary cleanup failure" in str(caught.value)
    assert "cleanup errors" in str(caught.value)


def test_staging_cleanup_failure_is_reported_with_primary_error_and_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_repo(tmp_path)
    module = importlib.import_module("tools.sr_config.generate")
    real_unlink = type(tmp_path).unlink
    cleanup_failed = False

    def fail_staging_write(_descriptor: int) -> None:
        raise OSError("primary staging write failure")

    def fail_staging_cleanup(
        path: Path, missing_ok: bool = False
    ) -> None:
        nonlocal cleanup_failed
        if not cleanup_failed and str(path).endswith(".tmp"):
            cleanup_failed = True
            raise OSError("secondary staging cleanup failure")
        real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(module.os, "fsync", fail_staging_write)
    monkeypatch.setattr(type(tmp_path), "unlink", fail_staging_cleanup)

    with pytest.raises(GenerationError) as caught:
        generate(tmp_path)

    leaked = list(tmp_path.rglob("*.tmp"))
    assert len(leaked) == 1
    assert "primary staging write failure" in str(caught.value)
    assert "secondary staging cleanup failure" in str(caught.value)
    assert str(leaked[0]) in str(caught.value)
    assert "cleanup errors" in str(caught.value)


def test_generation_cleans_staging_files_if_backup_staging_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_repo(tmp_path)
    settings = tmp_path / "spell_rev" / "settings.ini"
    before = settings.read_bytes()
    module = importlib.import_module("tools.sr_config.generate")
    real_stage = module._stage_bytes
    calls = 0

    def fail_first_backup(
        path: Path,
        payload: bytes,
        *,
        suffix: str,
        mode: int | None = None,
    ) -> Path:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated staging failure")
        return real_stage(path, payload, suffix=suffix, mode=mode)

    monkeypatch.setattr(module, "_stage_bytes", fail_first_backup)

    with pytest.raises(GenerationError, match="transaction failed"):
        generate(tmp_path)

    assert settings.read_bytes() == before
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("target_name", ["settings", "html", "markdown"])
def test_generation_rejects_cr_only_target_newlines(
    tmp_path: Path, target_name: str
) -> None:
    _seed_repo(tmp_path)
    if target_name == "markdown":
        generate(tmp_path)
        target = tmp_path / "docs" / "spell-revisions-change-catalog.md"
    elif target_name == "html":
        target = tmp_path / "spell_rev" / "readme-spell_rev.html"
    else:
        target = tmp_path / "spell_rev" / "settings.ini"
    target.write_bytes(
        target.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r")
    )

    with pytest.raises(GenerationError, match="lone CR newline"):
        generate(tmp_path, check=True)


@pytest.mark.parametrize("target_name", ["settings", "html", "markdown"])
def test_generation_rejects_crlf_mixed_with_lone_cr(
    tmp_path: Path, target_name: str
) -> None:
    _seed_repo(tmp_path, newline="\r\n")
    if target_name == "markdown":
        generate(tmp_path)
        target = tmp_path / "docs" / "spell-revisions-change-catalog.md"
    elif target_name == "html":
        target = tmp_path / "spell_rev" / "readme-spell_rev.html"
    else:
        target = tmp_path / "spell_rev" / "settings.ini"
    target.write_bytes(target.read_bytes() + b"\r")

    with pytest.raises(GenerationError, match="mixed newline conventions"):
        generate(tmp_path, check=True)


def test_markdown_read_error_is_wrapped_for_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_repo(tmp_path)
    markdown_path = tmp_path / "docs" / "spell-revisions-change-catalog.md"
    markdown_path.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    assert main(["generate", "--check"]) == 1
    output = capsys.readouterr()
    assert "generation failed:" in output.err
    assert "unable to read Markdown" in output.err
    assert "Traceback" not in output.err


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission modes")
def test_generation_preserves_existing_modes_and_uses_umask_for_new_files(
    tmp_path: Path,
) -> None:
    _seed_repo(tmp_path)
    settings = tmp_path / "spell_rev" / "settings.ini"
    html_path = tmp_path / "spell_rev" / "readme-spell_rev.html"
    markdown_path = tmp_path / "docs" / "spell-revisions-change-catalog.md"
    settings.chmod(0o640)
    html_path.chmod(0o604)
    current_umask = os.umask(0)
    os.umask(current_umask)

    generate(tmp_path)

    assert stat.S_IMODE(settings.stat().st_mode) == 0o640
    assert stat.S_IMODE(html_path.stat().st_mode) == 0o604
    assert stat.S_IMODE(markdown_path.stat().st_mode) == 0o666 & ~current_umask
