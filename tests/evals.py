#!/usr/bin/env python3
"""Behavioral eval pipeline for the citation-worthy skill.

Runs each case in tests/cases.json through headless Claude Code (`claude -p`) in an
isolated temp project, records the stream-json trace, and grades it: deterministic
checks over the tool calls (what was searched, what was fetched, whether the skill
loaded first) plus an LLM judge for the checks that need reading the answer.

    python3 tests/evals.py run                         # run + grade + report, new iteration
    python3 tests/evals.py run --cases fabricated-quote --runs 3
    python3 tests/evals.py run --configs with_skill,old_skill --baseline-ref HEAD
    python3 tests/evals.py grade  tests/results/iteration-1   # regrade without rerunning
    python3 tests/evals.py report tests/results/iteration-1

Configurations:
    with_skill     the skill as it is in the working tree
    without_skill  no skill at all (baseline)
    old_skill      the skill at --baseline-ref (a git ref), to compare an edit against
    claude_md      no skill; the condensed block from claude-md-block.md as CLAUDE.md

Every run uses --setting-sources project and --strict-mcp-config, so your own user
skills, CLAUDE.md and MCP servers stay out of it. These are real, billed model runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"
CASES_FILE = TESTS / "cases.json"
FIXTURES = TESTS / "fixtures"
RESULTS = TESTS / "results"

SKILL_NAME = "citation-worthy"
# What gets installed into a run's .claude/skills/citation-worthy/ — the skill itself,
# never tests/ (the run must not be able to read its own graders).
SKILL_FILES = ["SKILL.md", "references"]
TOOLS = "Skill,WebSearch,WebFetch,Read,Grep,Glob"
ALL_CONFIGS = ["with_skill", "without_skill", "old_skill", "claude_md"]
SKILL_CONFIGS = {"with_skill", "old_skill"}


# --------------------------------------------------------------------------- setup


def load_cases(names: list[str] | None) -> tuple[list[dict], list[dict]]:
    data = json.loads(CASES_FILE.read_text())
    cases = data["cases"]
    if names:
        unknown = set(names) - {c["name"] for c in cases}
        if unknown:
            sys.exit(f"unknown case(s): {', '.join(sorted(unknown))}")
        cases = [c for c in cases if c["name"] in names]
    return cases, data.get("global_checks", [])


def export_skill(ref: str | None, dest: Path) -> None:
    """Copy the skill files from the working tree (ref=None) or a git ref into dest."""
    dest.mkdir(parents=True, exist_ok=True)
    if ref is None:
        for name in SKILL_FILES:
            src = REPO / name
            if src.is_dir():
                shutil.copytree(src, dest / name)
            elif src.exists():
                shutil.copy2(src, dest / name)
        return
    archive = subprocess.run(
        ["git", "-C", str(REPO), "archive", ref, *SKILL_FILES],
        capture_output=True, check=True,
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)


def claude_md_block() -> str:
    """The pasteable part of claude-md-block.md: everything after the first `---` rule."""
    text = (REPO / "claude-md-block.md").read_text()
    return text.split("\n---\n", 1)[1].strip() + "\n"


def make_workdir(config: str, case: dict, baseline_ref: str | None) -> Path:
    work = Path(tempfile.mkdtemp(prefix="cw-eval-"))
    skills = work / ".claude" / "skills" / SKILL_NAME
    if config == "with_skill":
        export_skill(None, skills)
    elif config == "old_skill":
        export_skill(baseline_ref, skills)
    elif config == "claude_md":
        (work / "CLAUDE.md").write_text(claude_md_block())
    for name in case.get("fixtures", []):
        shutil.copy2(FIXTURES / name, work / name)
    return work


# --------------------------------------------------------------------------- running


def run_one(case: dict, config: str, run_dir: Path, args) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "outputs").mkdir(exist_ok=True)
    work = make_workdir(config, case, args.baseline_ref)
    cmd = [
        args.claude, "-p", case["prompt"],
        "--setting-sources", "project",
        "--strict-mcp-config",
        "--tools", TOOLS,
        "--allowedTools", TOOLS,
        "--output-format", "stream-json", "--verbose",
        "--max-turns", str(args.max_turns),
        "--max-budget-usd", str(args.max_budget_usd),
    ]
    if args.model:
        cmd += ["--model", args.model]
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=args.timeout)
        stdout, stderr, status = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr, status = f"timeout after {args.timeout}s", -1
    finally:
        shutil.rmtree(work, ignore_errors=True)
    elapsed = time.time() - started

    (run_dir / "transcript.jsonl").write_text(stdout)
    if stderr.strip():
        (run_dir / "stderr.txt").write_text(stderr)
    trace = parse_trace(stdout)
    (run_dir / "outputs" / "answer.md").write_text(trace["answer"] or "(no final answer)\n")
    (run_dir / "outputs" / "trace.md").write_text(render_trace(trace, limit=400))
    result = trace["result"]
    usage = result.get("usage") or {}
    tokens = sum(usage.get(k, 0) or 0 for k in (
        "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    timing = {
        "total_tokens": tokens,
        "duration_ms": result.get("duration_ms") or int(elapsed * 1000),
        "total_duration_seconds": round(elapsed, 1),
        "cost_usd": result.get("total_cost_usd"),
        "num_turns": result.get("num_turns"),
        "model": trace["model"],
        "exit_status": status,
    }
    (run_dir / "timing.json").write_text(json.dumps(timing, indent=2))
    return timing


# --------------------------------------------------------------------------- trace parsing


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def parse_trace(stdout: str) -> dict:
    """Flatten a stream-json transcript into ordered steps."""
    steps: list[dict] = []
    by_id: dict[str, dict] = {}
    result: dict = {}
    model = None
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = ev.get("type")
        if kind == "system" and ev.get("subtype") == "init":
            model = ev.get("model")
        elif kind == "assistant":
            for b in ev["message"].get("content", []):
                if b.get("type") == "text" and b["text"].strip():
                    steps.append({"kind": "text", "text": b["text"]})
                elif b.get("type") == "tool_use":
                    step = {"kind": "tool", "name": b["name"], "input": b.get("input", {}),
                            "result": None, "is_error": False}
                    by_id[b["id"]] = step
                    steps.append(step)
        elif kind == "user":
            content = ev.get("message", {}).get("content")
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        step = by_id.get(b.get("tool_use_id"))
                        if step is not None:
                            step["result"] = _result_text(b.get("content"))
                            step["is_error"] = bool(b.get("is_error"))
        elif kind == "result":
            result = ev
    answer = result.get("result")
    if not answer:
        texts = [s["text"] for s in steps if s["kind"] == "text"]
        answer = texts[-1] if texts else ""
    return {"steps": steps, "result": result, "model": model, "answer": answer}


def tools(trace: dict, name: str | None = None) -> list[dict]:
    return [s for s in trace["steps"] if s["kind"] == "tool" and (name is None or s["name"] == name)]


def fetched_urls(trace: dict) -> list[str]:
    return [s["input"].get("url", "") for s in tools(trace, "WebFetch")]


def render_trace(trace: dict, limit: int) -> str:
    out = []
    for s in trace["steps"]:
        if s["kind"] == "text":
            out.append(f"**assistant:** {s['text'].strip()}\n")
            continue
        inp = s["input"]
        if s["name"] == "WebSearch":
            extra = {k: v for k, v in inp.items() if k not in ("query", "mode")}
            head = f"WebSearch `{inp.get('query')}`" + (f" {json.dumps(extra)}" if extra else "")
        elif s["name"] == "WebFetch":
            head = f"WebFetch {inp.get('url')}\n  prompt: {inp.get('prompt', '')}"
        else:
            head = f"{s['name']} {json.dumps(inp)}"
        res = (s["result"] or "").strip().replace("\n", " ")
        if len(res) > limit:
            res = res[:limit] + " …"
        err = " (ERROR)" if s["is_error"] else ""
        out.append(f"- **{head}**\n  → {err}{res}\n")
    out.append("\n---\n**final answer:**\n\n" + (trace["answer"] or "(none)"))
    return "\n".join(out)


# --------------------------------------------------------------------------- checks


def describe(check: dict) -> str:
    t, label = check["type"], check.get("label", check.get("pattern", ""))
    return check.get("text") or {
        "skill_loaded_first": f"The {SKILL_NAME} skill is loaded before the first web search or fetch",
        "skill_not_loaded": f"The {SKILL_NAME} skill is not loaded",
        "pick_line_before_fetch": "A one-line tiered pick ('Fetching … (Tier N …)') is stated before the first fetch",
        "fetched": f"At least one fetch is from: {label}",
        "no_fetch": f"No fetch is from: {label}",
        "answer_matches": f"The final answer contains: {label}",
        "answer_not_matches": f"The final answer does not contain: {label}",
        "max_searches": f"At most {check.get('n')} web searches ({label})" if "label" in check
                        else f"At most {check.get('n')} web searches",
        "max_fetches": f"At most {check.get('n')} fetches",
        "no_web": "No web search or fetch is made",
        "no_refusal_to_fetch": "The URL the user supplied is fetched rather than refused",
        "cited_urls_read": "Every URL cited in the answer was actually fetched, or is marked as unread / failed",
    }[t]


URL_RX = re.compile(r"https?://[^\s)\]>\"'`]+")
# A line that says the page behind its URL was not read passes the cited_urls_read check.
UNREAD_RX = re.compile(
    r"unread|not read|not opened|n['’]t (open|read|load|fetch|access|reach|get)|did not (open|read|load)|"
    r"could not (open|read|load|fetch|access|reach|get)|unable to|search (result|excerpt|snippet)|"
    r"excerpt|snippet|blocked|failed|forbidden|40[13]|paywall|not fetched|not verified|unverified", re.I)


def _norm(url: str) -> str:
    u = urlparse(url.rstrip(".,;:*_"))
    host, path = u.netloc.lower().removeprefix("www."), u.path.rstrip("/")
    if host == "ncbi.nlm.nih.gov" and path.startswith("/pmc/"):  # old and new PMC URLs, same page
        host, path = "pmc.ncbi.nlm.nih.gov", path[4:]
    host = {"docs.python-requests.org": "requests.readthedocs.io"}.get(host, host)  # redirect alias
    return f"{host}{path}"


def _fetch_failed(step: dict) -> bool:
    res = step["result"] or ""
    return step["is_error"] or bool(re.search(r"HTTP (4|5)\d\d|unable to fetch|Forbidden", res[:300], re.I))


def check_cited_urls_read(trace: dict, prompt: str) -> tuple[bool, str]:
    """Every URL in the final answer was fetched successfully, or its line marks it as unread/failed.

    A label line ending in ':' (e.g. 'Search results I did not open:') covers the list under it.
    URLs the user typed into the prompt, and URLs inside code, are exempt. A run that made no
    web calls passes: its URLs are examples, not citations of research it did."""
    if not tools(trace, "WebSearch") and not tools(trace, "WebFetch"):
        return True, "no web calls (n/a)"
    answer = re.sub(r"```.*?```", "", trace["answer"] or "", flags=re.S)
    answer = re.sub(r"`[^`\n]*`", "", answer)
    read = {_norm(s["input"].get("url", "")) for s in tools(trace, "WebFetch") if not _fetch_failed(s)}
    given = {_norm(u) for u in URL_RX.findall(prompt)}
    bad, label = [], ""
    for line in answer.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        urls = URL_RX.findall(line)
        if not urls and (stripped.endswith(":") or stripped.endswith(":**") or stripped.startswith("#")):
            label = stripped
            continue
        for u in urls:
            n = _norm(u)
            if n in read or n in given or UNREAD_RX.search(line) or UNREAD_RX.search(label):
                continue
            bad.append(u)
    total = len(URL_RX.findall(answer))
    return not bad, (f"{len(bad)} of {total} cited URLs never read and not marked: {bad[:5]}" if bad
                     else f"all {total} cited URLs read or marked")


def check_deterministic(check: dict, trace: dict, prompt: str = "") -> tuple[bool, str]:
    t = check["type"]
    urls = fetched_urls(trace)
    if t == "skill_loaded_first":
        for s in tools(trace):
            if s["name"] == "Skill" and SKILL_NAME in json.dumps(s["input"]):
                return True, "Skill loaded before any web tool"
            if s["name"] in ("WebSearch", "WebFetch"):
                return False, f"first web call ({s['name']}) came before the skill loaded"
        return False, "skill never loaded"
    if t == "skill_not_loaded":
        hit = [s for s in tools(trace, "Skill") if SKILL_NAME in json.dumps(s["input"])]
        return not hit, "skill loaded" if hit else "skill not loaded"
    if t == "pick_line_before_fetch":
        seen_pick = False
        for s in trace["steps"]:
            if s["kind"] == "text" and re.search(r"\btier\s*[1-4]\b", s["text"], re.I):
                seen_pick = True
            if s["kind"] == "tool" and s["name"] == "WebFetch":
                return seen_pick, ("pick line present before first fetch" if seen_pick
                                   else "first fetch had no 'Tier N' line before it")
        return True, "no fetches made (vacuously true)"
    if t in ("fetched", "no_fetch", "no_refusal_to_fetch"):
        rx = re.compile(check["pattern"], re.I) if "pattern" in check else None
        if t == "no_refusal_to_fetch":
            ok = bool(urls)
            return ok, f"fetched: {urls}" if ok else "no fetch at all"
        hits = [u for u in urls if rx.search(u)]
        if t == "fetched":
            return bool(hits), f"matched: {hits}" if hits else f"none of {len(urls)} fetches matched; fetched: {urls}"
        return not hits, f"violations: {hits}" if hits else f"clean ({len(urls)} fetches)"
    if t in ("answer_matches", "answer_not_matches"):
        m = re.search(check["pattern"], trace["answer"] or "", re.I)
        ok = bool(m) if t == "answer_matches" else not m
        return ok, f"found '{m.group(0)}'" if m else "not found"
    if t == "max_searches":
        n = len(tools(trace, "WebSearch"))
        return n <= check["n"], f"{n} searches"
    if t == "max_fetches":
        n = len(urls)
        return n <= check["n"], f"{n} fetches"
    if t == "no_web":
        n = len(tools(trace, "WebSearch")) + len(urls)
        return n == 0, f"{n} web calls"
    if t == "cited_urls_read":
        return check_cited_urls_read(trace, prompt)
    raise ValueError(f"unknown check type {t}")


JUDGE_PROMPT = """You are grading one run of an AI research agent. Below is the user's prompt, the agent's \
condensed tool trace (searches, fetched URLs with truncated results, interim text) and its final answer.

Judge each numbered statement strictly against the trace and the final answer. A statement passes only if \
the evidence clearly supports it; when in doubt, fail it. Quote short evidence.

Reply with JSON only, no prose and no code fence, in exactly this shape:
{{"results": [{{"id": 1, "passed": true, "evidence": "..."}}]}}

## User prompt
{prompt}

## Trace
{trace}

## Statements
{statements}
"""


def run_judge(case: dict, trace: dict, checks: list[dict], args, run_dir: Path) -> list[tuple[bool, str]]:
    """Ask the judge model; verdicts are cached per (judge model, prompt) so a regrade is stable."""
    statements = "\n".join(f"{i + 1}. {c['text']}" for i, c in enumerate(checks))
    prompt = JUDGE_PROMPT.format(prompt=case["prompt"], trace=render_trace(trace, limit=700),
                                 statements=statements)
    cache_file = run_dir / "judge_cache.json"
    key = hashlib.sha256(f"{args.judge_model}\n{prompt}".encode()).hexdigest()
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    if key in cache:
        return [tuple(v) for v in cache[key]]
    verdicts = _ask_judge(prompt, len(checks), args)
    if not any(ev.startswith("[judge error]") for _, ev in verdicts):
        cache[key] = verdicts
        cache_file.write_text(json.dumps(cache, indent=2))
    return verdicts


def _ask_judge(prompt: str, n: int, args) -> list[tuple[bool, str]]:
    work = Path(tempfile.mkdtemp(prefix="cw-judge-"))
    try:
        proc = subprocess.run(
            [args.claude, "-p", "--model", args.judge_model, "--tools", "",
             "--setting-sources", "project", "--strict-mcp-config", "--output-format", "json"],
            input=prompt, cwd=work, capture_output=True, text=True, timeout=300,
        )
        text = json.loads(proc.stdout).get("result", "")
        parsed = json.loads(text[text.index("{"): text.rindex("}") + 1])
        by_id = {r["id"]: r for r in parsed["results"]}
        return [(bool(by_id[i + 1]["passed"]), "[judge] " + by_id[i + 1].get("evidence", ""))
                for i in range(n)]
    except Exception as e:  # a judge failure is a failed grade, never a pass
        return [(False, f"[judge error] {e}") for _ in range(n)]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def grade_run(case: dict, global_checks: list[dict], config: str, run_dir: Path, args) -> dict:
    trace = parse_trace((run_dir / "transcript.jsonl").read_text())
    checks = list(case["checks"]) + ([] if case.get("skip_global") else global_checks)
    checks = [c for c in checks if config in SKILL_CONFIGS or not c.get("skill_only")]
    det = [c for c in checks if c["type"] != "judge"]
    llm = [c for c in checks if c["type"] == "judge"]
    expectations = []
    for c in det:
        ok, ev = check_deterministic(c, trace, case["prompt"])
        expectations.append({"text": describe(c), "passed": ok, "evidence": ev,
                             "skill_only": bool(c.get("skill_only"))})
    if llm:
        if not trace["answer"]:
            verdicts = [(False, "no final answer")] * len(llm)
        elif args.no_judge:
            verdicts = None
        else:
            verdicts = run_judge(case, trace, llm, args, run_dir)
        if verdicts:
            for c, (ok, ev) in zip(llm, verdicts):
                expectations.append({"text": c["text"], "passed": ok, "evidence": ev,
                                     "skill_only": bool(c.get("skill_only"))})
    passed = sum(e["passed"] for e in expectations)
    counts: dict[str, int] = {}
    for s in tools(trace):
        counts[s["name"]] = counts.get(s["name"], 0) + 1
    grading = {
        "expectations": expectations,
        "summary": {"passed": passed, "failed": len(expectations) - passed, "total": len(expectations),
                    "pass_rate": round(passed / len(expectations), 3) if expectations else 0.0},
        "execution_metrics": {
            "tool_calls": counts,
            "total_tool_calls": sum(counts.values()),
            "fetched_domains": sorted({urlparse(u).netloc for u in fetched_urls(trace)}),
            "queries": [s["input"].get("query") for s in tools(trace, "WebSearch")],
        },
    }
    (run_dir / "grading.json").write_text(json.dumps(grading, indent=2))
    return grading


# --------------------------------------------------------------------------- layout


def run_dirs(iteration: Path) -> list[tuple[str, str, Path]]:
    """(case, config, run_dir) for every run with a transcript under an iteration."""
    found = []
    for t in sorted(iteration.glob("*/*/**/transcript.jsonl")):
        rel = t.parent.relative_to(iteration).parts
        found.append((rel[0], rel[1], t.parent))
    return found


def next_iteration() -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    nums = [int(m.group(1)) for p in RESULTS.iterdir() if (m := re.fullmatch(r"iteration-(\d+)", p.name))]
    return RESULTS / f"iteration-{max(nums, default=0) + 1}"


def write_metadata(iteration: Path, cases: list[dict], global_checks: list[dict]) -> None:
    for case in cases:
        d = iteration / case["name"]
        d.mkdir(parents=True, exist_ok=True)
        checks = list(case["checks"]) + ([] if case.get("skip_global") else global_checks)
        (d / "eval_metadata.json").write_text(json.dumps({
            "eval_name": case["name"],
            "prompt": case["prompt"],
            "expected_outcome": case.get("expected_outcome", ""),
            "assertions": [describe(c) for c in checks],
        }, indent=2))


# --------------------------------------------------------------------------- report


def report(iteration: Path) -> str:
    rows: dict[str, dict[str, list[dict]]] = {}
    configs: list[str] = []
    for case, config, rd in run_dirs(iteration):
        g = rd / "grading.json"
        if not g.exists():
            continue
        timing = json.loads((rd / "timing.json").read_text()) if (rd / "timing.json").exists() else {}
        rows.setdefault(case, {}).setdefault(config, []).append(
            {"grading": json.loads(g.read_text()), "timing": timing})
        if config not in configs:
            configs.append(config)
    configs.sort(key=lambda c: ALL_CONFIGS.index(c) if c in ALL_CONFIGS else 99)

    def rate(runs):
        p = sum(r["grading"]["summary"]["passed"] for r in runs)
        t = sum(r["grading"]["summary"]["total"] for r in runs)
        return p, t

    # Checks every configuration is graded on (skill_only ones excluded), for a like-for-like row.
    shared = {c: [0, 0] for c in configs}
    for case in rows:
        for c in configs:
            for r in rows[case].get(c, []):
                for e in r["grading"]["expectations"]:
                    if not e.get("skill_only"):
                        shared[c][0] += e["passed"]
                        shared[c][1] += 1

    lines = [f"# citation-worthy eval — {iteration.name}", "",
             "Cells are passed/total checks, summed over runs. `total` includes skill-only checks "
             "(skill loaded first, tier pick line, SOURCE HALT format); `shared checks only` is the "
             "like-for-like comparison across configurations.", ""]
    lines.append("| case | " + " | ".join(configs) + " |")
    lines.append("|---|" + "---|" * len(configs))
    totals = {c: [0, 0, 0.0, 0.0, 0] for c in configs}  # passed, total, cost, seconds, runs
    for case in sorted(rows):
        cells = []
        for c in configs:
            runs = rows[case].get(c, [])
            if not runs:
                cells.append("—")
                continue
            p, t = rate(runs)
            totals[c][0] += p
            totals[c][1] += t
            for r in runs:
                totals[c][2] += r["timing"].get("cost_usd") or 0
                totals[c][3] += r["timing"].get("total_duration_seconds") or 0
                totals[c][4] += 1
            cells.append(f"{p}/{t}")
        lines.append(f"| {case} | " + " | ".join(cells) + " |")
    lines.append("| **total** | " + " | ".join(
        f"**{totals[c][0]}/{totals[c][1]} ({totals[c][0] / max(totals[c][1], 1):.0%})**" for c in configs) + " |")
    lines.append("| **shared checks only** | " + " | ".join(
        f"**{shared[c][0]}/{shared[c][1]} ({shared[c][0] / max(shared[c][1], 1):.0%})**" for c in configs) + " |")
    lines.append("| cost / run | " + " | ".join(
        f"${totals[c][2] / max(totals[c][4], 1):.2f}" for c in configs) + " |")
    lines.append("| time / run | " + " | ".join(
        f"{totals[c][3] / max(totals[c][4], 1):.0f}s" for c in configs) + " |")
    lines += ["", "## Failures", ""]
    for case in sorted(rows):
        for c in configs:
            for i, r in enumerate(rows[case].get(c, [])):
                for e in r["grading"]["expectations"]:
                    if not e["passed"]:
                        tag = f"{case} / {c}" + (f" / run-{i + 1}" if len(rows[case][c]) > 1 else "")
                        lines.append(f"- **{tag}** — {e['text']}  \n  _{e['evidence'][:300]}_")
    md = "\n".join(lines) + "\n"
    (iteration / "report.md").write_text(md)
    return md


# --------------------------------------------------------------------------- CLI


def cmd_run(args) -> None:
    cases, global_checks = load_cases(args.cases)
    configs = args.configs.split(",")
    bad = set(configs) - set(ALL_CONFIGS)
    if bad:
        sys.exit(f"unknown config(s): {', '.join(bad)}")
    if "old_skill" in configs and not args.baseline_ref:
        sys.exit("old_skill needs --baseline-ref <git ref>")
    if not shutil.which(args.claude):
        sys.exit(f"`{args.claude}` not found on PATH")
    iteration = Path(args.out) if args.out else next_iteration()
    write_metadata(iteration, cases, global_checks)

    jobs = []
    for case in cases:
        for config in configs:
            for k in range(args.runs):
                rd = iteration / case["name"] / config
                if args.runs > 1:
                    rd = rd / f"run-{k + 1}"
                jobs.append((case, config, rd))
    print(f"{len(jobs)} runs → {iteration.relative_to(REPO) if iteration.is_relative_to(REPO) else iteration}",
          flush=True)

    cost = 0.0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run_one, case, config, rd, args): (case, config, rd) for case, config, rd in jobs}
        for f in as_completed(futures):
            case, config, rd = futures[f]
            try:
                timing = f.result()
                g = grade_run(case, global_checks, config, rd, args)
                cost += timing.get("cost_usd") or 0
                s = g["summary"]
                print(f"  {case['name']:34} {config:13} {s['passed']}/{s['total']}  "
                      f"{timing['total_duration_seconds']:>5.0f}s  ${timing.get('cost_usd') or 0:.2f}", flush=True)
            except Exception as e:
                print(f"  {case['name']:34} {config:13} FAILED: {e}", flush=True)
    print(f"\ntotal agent cost ${cost:.2f} (judge calls not included)\n")
    print(report(iteration))


def cmd_grade(args) -> None:
    iteration = Path(args.iteration)
    cases, global_checks = load_cases(None)
    by_name = {c["name"]: c for c in cases}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(lambda x: grade_run(by_name[x[0]], global_checks, x[1], x[2], args),
                      [x for x in run_dirs(iteration) if x[0] in by_name]))
    write_metadata(iteration, [c for c in cases if (iteration / c["name"]).exists()], global_checks)
    print(report(iteration))


def main() -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--claude", default=os.environ.get("CLAUDE_BIN", "claude"), help="claude CLI binary")
    common.add_argument("--judge-model", default="sonnet", help="model for LLM-judged checks (default: sonnet)")
    common.add_argument("--no-judge", action="store_true", help="skip LLM-judged checks")
    common.add_argument("--jobs", type=int, default=4, help="parallel runs (default 4)")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", parents=[common], help="run cases, then grade and report")
    r.add_argument("--cases", type=lambda s: s.split(","), help="comma-separated case names (default: all)")
    r.add_argument("--configs", default="with_skill,without_skill",
                   help=f"comma-separated, from {ALL_CONFIGS} (default: with_skill,without_skill)")
    r.add_argument("--baseline-ref", help="git ref for the old_skill config, e.g. HEAD or HEAD~1")
    r.add_argument("--runs", type=int, default=1, help="runs per case and config (default 1)")
    r.add_argument("--model", help="model for the agent under test (default: your CLI default)")
    r.add_argument("--max-turns", type=int, default=30)
    r.add_argument("--max-budget-usd", type=float, default=1.50, help="per-run spend cap")
    r.add_argument("--timeout", type=int, default=900, help="per-run timeout in seconds")
    r.add_argument("--out", help="iteration directory (default: tests/results/iteration-<next>)")
    r.set_defaults(func=cmd_run)

    g = sub.add_parser("grade", parents=[common], help="regrade an existing iteration")
    g.add_argument("iteration")
    g.set_defaults(func=cmd_grade)

    p = sub.add_parser("report", parents=[common], help="rewrite report.md for an iteration")
    p.add_argument("iteration")
    p.set_defaults(func=lambda a: print(report(Path(a.iteration))))

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
