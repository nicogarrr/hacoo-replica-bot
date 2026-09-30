# Hacoo fixes: apply in order 01, 02, 03

Base: 7a4fd4c5cb9f6cdcbb172002082c14fce0e30d4a.

01: H1 H5 H7 H8 H9 + RapidFuzz 3.14.1 (41 tests).
02: H2 H3 H6 H11 H12 + controlled SQLite handler error (61 tests).
03: H4 H10 H13 + offline marketplace identities (93 tests).

Run: pip install -r requirements.txt; python -m pytest -q.
pytest is needed only for tests, not runtime. All network integration tests use
fake sessions. No Telegram calls, production DB, paid API, or deployment tested.

The original suite has 35 tests. 34 remain unchanged. One assertion documented
that ID search did not exist; it is now a positive regression test for ID search.
58 new parameterized test cases cover fixes, giving 93 passing tests in total.

No flag switched ON, no synthetic Hacoo URLs, no affiliate URLs manufactured.
Only mapping entries explicitly supplied by the operator are used. A supported
host is not proof of affiliate ownership: verify mappings in the dashboard.

Allowlist: HTTPS hacoo.app and hacoo.pl including subdomains, onlyaff.app,
c.onlyaff.app. Check actual production host samples before deployment. Unknown
hosts (including legacy x.sh fixtures) are never fetched or rendered by handlers.
The search unit tests retain synthetic x.sh URLs to test ranking independently.

RapidFuzz fallback is bounded to the newest 500 alive index rows. Word threshold
85, numeric tokens must match literally. This is a typo fallback, not a semantic
model. It can miss older matches outside the bounded candidate window. Existing
progressive relaxation remains: related models may be returned, with exact=False
if the requested model is absent. No typo is described as an exact match.

Retry state migration adds resolve_attempts and resolve_retry_at in place. Backoff
starts at 60 seconds and caps at one day. Selection is frozen at pass start, so
transient failures never loop within one run. Existing terminal failures remain
terminal: this patch does not requeue historical failures automatically. To retry
those, first inspect/select genuinely transient rows in production. Do not blindly
requeue dead or unsupported URLs.

Liveness checks every eligible live link at most once per pass and rotates oldest
checked_at first. HTTP failures still do not prove death, as before. No stock/size
availability claims are added.

## cn-links-style normalization

Own small Python implementation, no npm/package dependency and no copied source.
Reference concept: https://github.com/cachho/cn-links (public page says TS/MIT).
Its source/API/npm retrieval returned 404 during this work. That does not prove
abandonment. No claim is made that this is the entire cn-links pattern set.

The resolver exports resolve_identity(session, url) with a typed result. For
marketplace links it is offline: marketplace + product_id + canonical_url, with
kind=marketplace. It supports numeric Taobao/Tmall id, Weidian itemID, 1688 offer
paths, CSSBuy item[-platform]-ID.html, and CNFans product platform/shop_type + id,
plus bounded nested url decoding for those two agents. Unknown/non-numeric IDs,
ambiguous duplicate parameters and hostile hosts fail closed.

Concrete external examples inspected:
https://github.com/cachho/cn-links (Weidian itemId example)
https://apify.com/teodor_banea/taobao-agent-link-converter-cnfans-hoobuy-oopbuy-superbuy/api
(CNFans platform=TAOBAO/ALI_1688, CSSBuy item-1688-ID.html, 1688 canonical URL)
https://qualit.ly/linkconverter/cnfans
(CNFans shop_type=weidian and numeric itemID)
CSSBuy default/Weidian route variants are parser fixtures, not verified live
merchant stock or availability. Only URLs/format examples were read, no paid
service used, no account connected.

Marketplace IDs are separate namespaces. They are NOT Hacoo IDs, never saved
in links.product_id, never served under "Abrir en Hacoo" and never converted to
Hacoo/affiliate links. The existing Hacoo crawl/output allowlist is unchanged by
this normalizer. To ingest/display marketplace products requires a separate UI,
DB namespace and explicit scope change, not silently widening H6.

No marketplace shortlinks are followed; they return unknown without requests.
No QC/price/stock lookup or marketplace search added. Runtime cost is local only.
