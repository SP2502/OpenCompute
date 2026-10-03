"""Tests for the deterministic Markdown verifier."""

from pathlib import Path

from opencompute.verification.markdown import verify_markdown_report

GOOD = """# Report

## Comparison
a vs b.

## References
- [Open-Meteo](https://open-meteo.com)
"""


def test_verify_passes_good_report(tmp_path):
    f = tmp_path / "r.md"
    f.write_text(GOOD)
    r = verify_markdown_report(f)
    assert r.passed
    assert not r.failures


def test_verify_fails_missing_file(tmp_path):
    r = verify_markdown_report(tmp_path / "nope.md")
    assert not r.passed
    assert any("file" in x for x in r.failures)


def test_verify_fails_empty_file(tmp_path):
    f = tmp_path / "empty.md"
    f.write_text("")
    r = verify_markdown_report(f)
    assert not r.passed


def test_verify_fails_missing_section(tmp_path):
    f = tmp_path / "r.md"
    f.write_text("# Report\n\n## Something\n\ntext https://x.com\n")
    r = verify_markdown_report(f, required_sections=["References"])
    assert not r.passed
    assert any("References" in x for x in r.failures)


def test_verify_fails_no_urls(tmp_path):
    f = tmp_path / "r.md"
    f.write_text("# Report\n\n## References\n- a source with no link\n")
    r = verify_markdown_report(f)
    assert not r.passed
    assert any("URL" in x for x in r.failures)
