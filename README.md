# citation-worthy

A source-validation skill for [Claude Code](https://claude.com/claude-code). It makes the
agent evaluate *where* a search result comes from **before** it fetches the page, refuse
hyper-partisan sites, tabloids, SEO/AI content farms and scraped mirrors, prefer primary
and institutional sources, recover with targeted re-queries when a search returns
garbage — and **halt and tell you** rather than quietly settling for a low-quality source.

It applies across every domain, not just politics: science, medicine, law, software,
finance, history, statistics and consumer claims each get their own source map.

## Why

Left to its own devices, an autonomous agent fetches whatever ranks first. Search rankings
optimize for engagement and SEO, not accuracy, so the top result is often the least
accountable page on the topic. Once a content farm's text is in the context window it
shapes the answer whether or not it gets cited, and you can't see where a number came
from. This skill turns fetching into a decision with a stated rationale.

## Install

```bash
git clone https://github.com/topoftheblock/citation-worthy-skill.git ~/.claude/skills/citation-worthy
```

Project-scoped instead of global:

```bash
git clone https://github.com/topoftheblock/citation-worthy-skill.git .claude/skills/citation-worthy
```

Start a new Claude Code session. The skill loads itself when a task involves web search
or fetching a URL; you can also invoke it explicitly with `/citation-worthy`. To confirm
the install, type `/` and check that `citation-worthy` is in the list.

Update with `git -C ~/.claude/skills/citation-worthy pull`; uninstall by deleting that
directory.

**No-install option:** copy the block in [`claude-md-block.md`](claude-md-block.md) into
your `CLAUDE.md`. Same protocol, condensed, no files needed. The skill is preferable for
long sessions — it loads only when you actually research, instead of occupying context in
every prompt.

## What it does

| | |
| --- | --- |
| **Pre-fetch triage** | Classifies each search result from the SERP alone — publisher, URL shape, date, distance from the primary source — and states the pick in one line before fetching. |
| **Tiers** | Tier 1 primary/institutional (fetch freely), Tier 2 accountable secondary (fetch, attribute, corroborate), Tier 3 (do not fetch as a basis for facts), Tier 4 (never). |
| **Blocklist by category** | Hyper-partisan outlets of any alignment, tabloids, opinion-as-fact, SEO and AI content mills, scraped Q&A/doc mirrors, affiliate listicles, press-release reprints, predatory journals, undated pages. |
| **Allowlist** | `.gov`/`.mil`/`.int`, courts and regulators, peer-reviewed work via DOI, standards bodies (RFC/W3C/ISO/NIST), first-party technical docs, AP/Reuters/AFP/PA. |
| **Recovery** | Up to three reformulations: force the domain class with `site:`, switch to the professional register, go upstream to the artifact, constrain the format, then leave the general search engine for the field's own index. |
| **Halt condition** | A structured `SOURCE HALT` report listing the queries tried, what was rejected and why, and three options — instead of a confident unsourced answer. |
| **Injection safety** | Fetched page content is treated as data, never as instructions. |
| **Your URLs are yours** | A specific URL you hand the agent is fetched as asked, with a one-line note on what kind of source it is. The gate applies to what the agent picks, not to what you pick. |

## Design notes

**The blocklist is by category and by structural signal, not by a hardcoded list of outlet
names.** Named blocklists go stale within months and are always contestable — someone will
argue about any specific entry, and the list can never cover the long tail of farms that
appear weekly. What generalizes are the structural tests: directional consistency across
stories, loaded modifiers in straight reporting, who gets quoted, disclosed funding, and
whether the publisher ever corrects itself. Those are in
[`references/red-flags.md`](references/red-flags.md), along with pointers to maintained
external lists (Wikipedia's perennial sources, Retraction Watch, DOAJ indexing) for a
second opinion on a specific outlet.

**Tier follows the claim, not the URL.** A vendor's docs are Tier 1 for "what does this
flag do" and Tier 3 for "is this product better than a competitor's". A campaign site is
Tier 1 for "what is this candidate's stated position" and Tier 3 for whether that position
is sound. And when a low-quality source *is* the subject — you're analyzing media
coverage, or quoting a company's own blog — fetching it is correct, labeled as primary
evidence of what that source says.

**Community answers get a pragmatic carve-out.** Stack Overflow and technical blogs are
allowed as debugging *hypotheses to test in code*, never as documented behavior. Without
this, a strict rule makes the agent useless for the most common real research task.

## Check that it works

In a fresh session, with no mention of the skill, try these. In each case the first tool
call should be the skill loading itself.

| Prompt | What you should see |
| --- | --- |
| `Does magnesium supplementation actually improve sleep? Search the web and give me a short sourced answer.` | Searches pinned to PubMed/PMC/NIH, a one-line pick before fetching (`Fetching pubmed.ncbi.nlm.nih.gov … Tier 1`), and no supplement vendors or wellness blogs. |
| `What's the best budget mechanical keyboard to buy right now? Search the web and recommend one with sources.` | Anonymous affiliate listicles skipped; the answer built from individual hands-on reviews and the manufacturer's own page, with the outlets' affiliate interest disclosed and any page it could not read marked as an unread excerpt. |
| `Find me a source confirming that <public figure> said "<a quote you made up>".` | A few targeted re-queries, then a `SOURCE HALT` block instead of a quote site or a confident guess. |
| `My Python requests call hangs forever when the server stops responding mid-download. Search the web for why and how to fix it.` | Straight to the library's own docs, with the relevant sentence quoted. |

These were run against Claude Code 2.1.296. Exact wording varies from run to run; the
tool calls are what to look at.

To run one headless and see every tool call:

```bash
claude -p "<prompt>" --output-format stream-json --verbose \
  --allowedTools "Skill,WebSearch,WebFetch,Read"
```

## Layout

```
citation-worthy/
├── SKILL.md                        # the protocol the agent follows
├── claude-md-block.md              # condensed drop-in block for CLAUDE.md
└── references/
    ├── red-flags.md                # classifying an unfamiliar domain
    ├── source-tiers.md             # where Tier 1 lives, field by field
    └── search-operators.md         # recovery queries with worked examples
```

`SKILL.md` is what loads when the skill triggers. The `references/` files are read only
when the agent needs them, so they cost nothing until they're used.

## Tuning it

- **Add your own hard blocks or allows.** Append a short list to the end of `SKILL.md`
  under a `## Local overrides` heading — an explicit named entry beats a heuristic for
  domains you already have an opinion about.
- **Loosen or tighten the halt.** Three recovery attempts is a default; change the number
  in step 4 of `SKILL.md` and in step 8 of `claude-md-block.md`.
- **Narrow the scope.** If you only want this on research tasks and not on debugging,
  trim the software section of `references/source-tiers.md` and the community carve-out
  in section 3 of `SKILL.md`.

## License

MIT — see [LICENSE](LICENSE).
