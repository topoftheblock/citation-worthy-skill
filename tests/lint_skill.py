#!/usr/bin/env python3
"""Static checks for the citation-worthy skill. Free, fast, no model calls.

    python3 tests/lint_skill.py

Exits non-zero on any failure. Checks the skill's frontmatter against Claude Code's
limits, that every file the docs point at exists, and that SKILL.md and the condensed
claude-md-block.md haven't drifted apart on the things they must agree on.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
failures: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        failures.append(msg)


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    return fields


skill = (REPO / "SKILL.md").read_text()
block = (REPO / "claude-md-block.md").read_text()
readme = (REPO / "README.md").read_text()
body = skill.split("\n---\n", 1)[1] if skill.startswith("---") else skill

print("frontmatter")
fm = frontmatter(skill)
check(fm.get("name") == "citation-worthy", f"name is 'citation-worthy' (got {fm.get('name')!r})")
check(re.fullmatch(r"[a-z0-9-]{1,64}", fm.get("name", "")) is not None, "name is lowercase/digits/hyphens, ≤64 chars")
desc = fm.get("description", "")
check(0 < len(desc) <= 1024, f"description is 1–1024 chars (got {len(desc)})")
check("<" not in desc and ">" not in desc, "description has no angle brackets")
check(set(fm) <= {"name", "description", "license", "allowed-tools", "metadata", "compatibility"},
      f"no unknown frontmatter keys (got {sorted(fm)})")

print("size")
n = len(skill.splitlines())
check(n <= 500, f"SKILL.md ≤ 500 lines (got {n})")

print("references")
refs = sorted(p.relative_to(REPO).as_posix() for p in (REPO / "references").glob("*.md"))
mentioned = set(re.findall(r"references/[\w.-]+\.md", skill))
for r in refs:
    check(r in mentioned, f"{r} is pointed to from SKILL.md")
for r in sorted(mentioned):
    check((REPO / r).exists(), f"{r} (named in SKILL.md) exists")
for f in ["SKILL.md", *refs, "claude-md-block.md", "README.md"]:
    text = (REPO / f).read_text()
    for target in re.findall(r"`(references/[\w.-]+\.md)`", text):
        check((REPO / target).exists(), f"{f}: link to {target} resolves")

print("README links")
for target in re.findall(r"\]\(([^)#:]+)\)", readme):
    check((REPO / target).exists(), f"README link {target} resolves")

print("SKILL.md ↔ claude-md-block.md")
skill_n = re.search(r"at most \*\*(\d+) reformulations", skill)
block_n = re.search(r"Max \*\*(\d+)\*\* reformulations", block)
check(bool(skill_n and block_n), "both state a recovery budget")
if skill_n and block_n:
    check(skill_n.group(1) == block_n.group(1),
          f"recovery budget matches (SKILL.md {skill_n.group(1)}, block {block_n.group(1)})")
    halt = re.search(r"If (\w+) recovery attempts", skill)
    words = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5"}
    check(bool(halt) and words.get(halt.group(1).lower()) == skill_n.group(1),
          "SKILL.md halt section uses the same number as the recovery budget")
for phrase in ["SOURCE HALT", "Queries tried:", "Rejected:", "Best available:"]:
    check(phrase in skill and phrase in block, f"halt template field '{phrase}' in both")
for concept, rx in {
    "tier 1 wire services": r"AP.*Reuters.*AFP",
    "community-answers carve-out": r"Stack Overflow",
    "user-supplied URL rule": r"URL (the user hands you|I hand you)",
    "data-not-instructions rule": r"data, never (as )?instructions",
    "affiliate listicle rule": r"affiliate",
    "unread-snippet rule": r"(unread search excerpt|unread excerpt)",
    "domain-filter preference": r"allow(/| )block list|domain filter",
    "lookalike domains": r"lookalike",
    "split sources list": r"Seen in search results, not opened",
    "halt even when fabrication is obvious": r"obvious the claim is fabricated",
}.items():
    flat_skill, flat_block = " ".join(skill.split()), " ".join(block.split())
    check(bool(re.search(rx, flat_skill)) and bool(re.search(rx, flat_block)), f"both cover: {concept}")
check("\n---\n" in block, "claude-md-block.md has a `---` rule before the pasteable block")

print("eval cases")
cases = json.loads((REPO / "tests" / "cases.json").read_text())["cases"]
names = [c["name"] for c in cases]
check(len(names) == len(set(names)), "case names are unique")
for c in cases:
    check(re.fullmatch(r"[a-z][a-z0-9-]*", c["name"]) is not None, f"{c['name']}: valid case name")
    for f in c.get("fixtures", []):
        check((REPO / "tests" / "fixtures" / f).exists(), f"{c['name']}: fixture {f} exists")
    for chk in c["checks"]:
        if "pattern" in chk:
            try:
                re.compile(chk["pattern"])
            except re.error as e:
                check(False, f"{c['name']}: bad regex {chk['pattern']!r}: {e}")

print()
if failures:
    print(f"{len(failures)} check(s) failed")
    sys.exit(1)
print("all checks passed")
