# Recovery queries

Concrete reformulations for when a search returns nothing citable. Change one variable at
a time so you learn which move worked; cap at three reformulations, then halt and report.

## Table of contents

- [Force the domain class](#force-the-domain-class)
- [Change the register](#change-the-register)
- [Go upstream to the artifact](#go-upstream-to-the-artifact)
- [Constrain the format](#constrain-the-format)
- [Leave the general search engine](#leave-the-general-search-engine)
- [Worked examples](#worked-examples)
- [Operator support caveat](#operator-support-caveat)

## Force the domain class

The highest-yield single move. Pin the result set to accountable publishers:

```
<query> site:.gov
<query> site:.edu
<query> (site:.gov OR site:.edu OR site:.int)
<query> site:reuters.com OR site:apnews.com
<query> site:nih.gov OR site:cdc.gov OR site:who.int
<query> site:arxiv.org OR site:doi.org OR site:ncbi.nlm.nih.gov
<query> site:docs.<project>.<tld>        # first-party technical docs
<query> site:github.com/<org>/<repo>     # issues, releases, source
```

Exclusion is weaker than inclusion but useful when one farm dominates:

```
<query> -site:<domain-that-keeps-appearing>
<query> -"best" -"top 10" -"ultimate guide"
```

## Change the register

Search the way the primary literature writes, not the way the question was asked. This
often replaces the entire result set in one step.

| Lay phrasing | Professional register |
| --- | --- |
| heart attack | myocardial infarction |
| the new privacy law | Regulation (EU) 2016/679, GDPR Art. 17 |
| the login bug | CVE-2025-XXXXX, the advisory id |
| how email encryption works | RFC 8551, S/MIME |
| unemployment went up | BLS CPS U-3 seasonally adjusted, <month> |
| the company got sued | <case name>, docket <number> |

## Go upstream to the artifact

If ten pages all summarize one thing, search for that thing directly:

```
"<exact title of the study>"
doi.org/<doi>
"<exact quoted sentence from the snippet>"     # finds the origin of a circulating claim
<agency> press release <date>
<project> changelog <version>
```

Harvest identifiers from search snippets without fetching the wrapper page.

## Constrain the format

```
<query> filetype:pdf          # reports, standards, agency publications
intitle:"<exact term>"        # precision when a word is overloaded
"<phrase in quotes>"          # exact match, no synonym expansion
<query> after:2024-01-01      # where supported; version-sensitive topics
```

## Leave the general search engine

When the open web is saturated, query the field's own index:

| Field | Index |
| --- | --- |
| Biomedical | PubMed, PMC, ClinicalTrials.gov, Cochrane Library |
| Physics/CS/math | arXiv, ACM DL, IEEE Xplore, DBLP |
| Social science/law | SSRN, JSTOR, HeinOnline, Google Scholar |
| US law | CourtListener, govinfo.gov, Federal Register, Congress.gov |
| EU law | EUR-Lex, curia.europa.eu |
| Companies | SEC EDGAR, Companies House, national registries |
| Economics/statistics | FRED, BLS, Eurostat, OECD.Stat, World Bank Open Data |
| Standards | IETF Datatracker, W3C TR index, ISO Online Browsing Platform |
| Software | the project's GitHub releases, its docs site, NVD/CVE, Libraries.io |
| Archives | Library of Congress, National Archives catalogs, Europeana |

## Worked examples

**Bad result set: a health question buried in supplement ads**

```
1. does magnesium help with sleep
2. magnesium supplementation insomnia randomized controlled trial site:nih.gov
3. "magnesium" "sleep quality" meta-analysis site:ncbi.nlm.nih.gov
```

**Bad result set: a framework question buried in tutorial mills**

```
1. how to configure retries in <library>
2. <library> retry configuration site:docs.<library>.dev
3. "retry" site:github.com/<org>/<library> path:/docs
```

**Bad result set: a news claim only on partisan sites**

```
1. <claim as the user phrased it>
2. <claim> site:apnews.com OR site:reuters.com
3. "<exact quoted phrase>" <official body name> transcript OR statement
```

If step 3 still yields nothing Tier 1/2 — halt and report, using the SOURCE HALT format
in SKILL.md. Do not fetch the partisan page to "check".

## Operator support caveat

Operator support varies by search backend: `site:`, quoted phrases, and `filetype:` are
broadly honored; `after:`, `intitle:`, and boolean `OR` are not universal. If an operator
appears to be ignored (the result set doesn't change at all), fall back to putting the
domain or the professional term in as a plain keyword, and rely on triage to reject what
comes back.
