# Classifying an unfamiliar domain

Most of the web is not on anyone's list. These are the signals that let you tier a domain
you've never seen, using the search snippet first and the page itself only if you've
already decided it's fetchable.

## Table of contents

- [Judge from the SERP first](#judge-from-the-serp-first)
- [Disqualifying signals](#disqualifying-signals)
- [Qualifying signals](#qualifying-signals)
- [Lookalike and impersonation domains](#lookalike-and-impersonation-domains)
- [Detecting partisanship without a list of outlets](#detecting-partisanship-without-a-list-of-outlets)
- [Detecting SEO and AI content farms](#detecting-seo-and-ai-content-farms)
- [Detecting scraped mirrors](#detecting-scraped-mirrors)
- [Predatory and low-quality journals](#predatory-and-low-quality-journals)
- [Maintained external lists](#maintained-external-lists)

## Judge from the SERP first

A search result gives you the domain, the URL path, the title, a snippet, and often a
date. That is enough to reject most junk without spending a fetch. Ask:

1. Is this the entity that produced the fact, or someone retelling it?
2. Would this publisher print a correction if it were wrong, and would anyone notice?
3. Does the URL look like a document, or like a landing page built to rank?

## Disqualifying signals

Any one of these is enough to skip the result:

- No author name anywhere, or an author who is a generic persona ("Staff Writer",
  "Editorial Team", a stock-photo byline with no other work).
- No publication date, or a "last updated" date that changes without the content
  changing.
- Title patterns built for search: `Top 10 …`, `… : Everything You Need To Know`,
  `Is X Worth It In 2026?`, `X vs Y: The Ultimate Guide`.
- URL patterns: `/amp/`, deep keyword-stuffed slugs, `?utm_`-heavy canonical links,
  category paths like `/trending/`, `/viral/`, `/deals/`.
- The snippet attributes the claim to someone else ("a study found", "reports say",
  "according to sources") without naming a retrievable source.
- The domain sells the thing it is evaluating, or earns affiliate revenue on it.
- The page is a translation or re-post of another page that ranks lower.
- Interstitials and monetization dominate: the snippet is mostly boilerplate,
  the site is a subdomain farm, or the domain hosts unrelated topics at scale
  (crypto, weight loss, immigration law, and GPU benchmarks on one site).

## Qualifying signals

- A named author with verifiable credentials or a masthead you can check.
- A visible corrections/retractions policy, and evidence it is used.
- Stable identifiers: DOI, RFC number, CVE id, docket number, spec section, ISBN.
- References to primary sources that you could independently retrieve.
- An "about", ownership, and funding disclosure that names real people or institutions.
- Editorial separation between news and opinion, clearly labeled.
- The page is the thing itself (the statute, the spec, the dataset, the filing) rather
  than a description of it.

## Lookalike and impersonation domains

Check the registrable domain character by character against the institution you expect:

- `nature.com` vs `nature-journal.example`, `who.int` vs `who-news.example`
- Hyphenated or suffixed variants of a real brand (`-news`, `-official`, `-daily`)
- A `.org`/`.co`/`.info` twin of a well-known `.gov`/`.edu`/`.com`
- Homoglyphs and extra characters (`rn` for `m`, doubled letters)

When in doubt, navigate to the institution's real domain and find the document there
instead of trusting the search result's link.

## Detecting partisanship without a list of outlets

Named blocklists go stale and are always contestable. These structural tests generalize:

- **Directional consistency**: does every story resolve in favor of one side, including
  stories where the evidence is genuinely mixed?
- **Adjectives in the news copy**: loaded modifiers in straight reporting ("radical",
  "disastrous", "so-called") rather than confined to labeled opinion.
- **Who is quoted**: only allied sources, with opponents paraphrased rather than quoted.
- **Funding and ownership**: an advocacy group, party, campaign, PAC, or single-donor
  foundation behind the masthead — often disclosed only in a footer or on the about page.
- **Corrections**: an outlet that never corrects is not more accurate; it is less
  accountable.
- **Framing in the headline vs the body**: the headline asserts what the body only
  suggests.

This test applies to every domain, not just politics: nutrition, climate, vaccines,
cryptocurrency, AI policy, and programming-language flame wars all have advocacy outlets
dressed as reporting.

## Detecting SEO and AI content farms

- Publishing volume that no named staff could produce; dozens of posts a day across
  unrelated topics.
- Text that restates the question, hedges, and never gets specific — no numbers, no
  version strings, no citations.
- Boilerplate section headers matching the query verbatim ("What is X?", "Why is X
  important?", "Conclusion").
- Code samples that don't run, mixed API versions, invented flags — a common tell in
  AI-generated technical posts.
- Identical phrasing appearing across several results in the same SERP: they are all
  spinning one upstream article.

## Detecting scraped mirrors

Q&A scrapers, doc mirrors, and README reposters rank by copying accountable content.
If the snippet reads like Stack Overflow, MDN, a man page, or a project README, search
for a distinctive phrase from it in quotes and fetch the original instead. The mirror is
usually stale, often truncated, and sometimes silently edited.

## Predatory and low-quality journals

Signals that a "journal" is pay-to-publish rather than peer-reviewed:

- Solicitation language on the site ("rapid publication in 72 hours", "call for papers"
  across unrelated fields).
- An editorial board of names with no listed affiliation, or affiliations that deny it.
- No indexing in PubMed, Scopus, Web of Science, or DOAJ.
- A title that closely mimics an established journal.
- Article-processing charges advertised more prominently than editorial standards.

Prefer the version of record with a DOI, or the author's institutional repository copy.

## Maintained external lists

You do not have to maintain a blocklist yourself. When you need a second opinion on a
specific outlet, these are useful (each with its own editorial stance, so read them as
input, not verdict):

- Wikipedia's perennial sources list — a long-running, sourced consensus on which
  publications are considered generally reliable, situational, or deprecated.
- Retraction Watch — retractions and journals with integrity problems.
- DOAJ, PubMed, Scopus indexing status — whether a journal is indexed at all.
- The project's own docs site, linked from its repository — the canonical answer to
  "which of these five doc mirrors is real".
