"""Deterministic verifier for Markdown reports.

This is the concrete stand-in for the (later) quality estimator: instead of a
vague "quality = 94%" we check hard facts. A report passes when:

    - the file exists and is not empty
    - it contains at least a top-level heading
    - every required section heading is present
    - it links to sources (i.e. contains URLs)

All of this is plain string/file checks -- no model call, so verification is
free and reproducible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VerificationResult:
    passed: bool
    checks: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def add(self, ok: bool, label: str, detail: str = "") -> None:
        self.checks.append(label)
        if not ok:
            self.failures.append(detail or label)


_URL_RE = re.compile(r"https?://[^\s)>\"']+")


def verify_markdown_report(
    path: Path,
    required_sections: list[str] | None = None,
    require_sources: bool = True,
) -> VerificationResult:
    result = VerificationResult(passed=False)
    required_sections = required_sections or ["Comparison", "References"]

    # 1. File exists and is non-empty.
    if not path.exists():
        result.add(False, "file exists", f"missing file: {path}")
        result.passed = False
        return result
    content = path.read_text(encoding="utf-8")
    result.add(True, "file exists", str(path))
    if not content.strip():
        result.add(False, "file is not empty", "file is empty")
        result.passed = False
        return result
    result.add(True, "file is not empty")

    # 2. Has a heading (basic "is this markdown" signal).
    has_heading = bool(re.search(r"^#{1,6}\s+\S", content, re.MULTILINE))
    result.add(has_heading, "has a heading", "no markdown heading found")

    # 3. Required sections present (case-insensitive heading match).
    for section in required_sections:
        found = re.search(
            r"^#{1,6}\s+.*" + re.escape(section) + r".*$",
            content,
            re.MULTILINE | re.IGNORECASE,
        )
        result.add(bool(found), f"section '{section}' present",
                   f"missing section: {section}")

    # 4. Contains source links.
    urls = _URL_RE.findall(content)
    if require_sources:
        result.add(bool(urls), "contains source URLs",
                   "no URLs found in report")

    result.passed = len(result.failures) == 0
    return result
