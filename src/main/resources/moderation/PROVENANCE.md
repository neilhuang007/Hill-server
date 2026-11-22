# Imported English moderation vocabulary

## Upstream

- Project: **cuss**, by Titus Wormer and contributors, `words/cuss`.
- Version: **2.2.0**.
- Git commit: **6bab3fef250481e34ba55bc400fac5c6d25f1429**.
- Repository: <https://github.com/words/cuss>.
- Source: <https://github.com/words/cuss/blob/6bab3fef250481e34ba55bc400fac5c6d25f1429/index.js>.
- License: **MIT**, copyright (c) 2016 Titus Wormer
  <tituswormer@gmail.com>. The full required notice is preserved alongside this
  file in `cuss-LICENSE.txt` and included in the plugin JAR.
- Upstream license:
  <https://github.com/words/cuss/blob/6bab3fef250481e34ba55bc400fac5c6d25f1429/license>.
- Upstream explanation, data attribution and caveats:
  <https://github.com/words/cuss/blob/6bab3fef250481e34ba55bc400fac5c6d25f1429/readme.md>.

`cuss-en.js` is the upstream English `index.js`, copied without vocabulary or
rating changes. It is parsed as data by Java; JavaScript is never executed and
Node.js is not a runtime dependency. No network access is used at runtime.

The pinned file contains **1,795 entries**: 1,255 rated 2, 285 rated 1 and 255
rated 0. These are measured from this exact source, rather than the approximate
counts in the upstream README. Ratings describe certainty of profane use, not
severity. Upstream credits Luis von Ahn's Research Group at Carnegie Mellon,
Wikipedia's list of ethnic slurs, and later contributors as English data sources.

The upstream author explicitly warns against treating this research vocabulary
as a reliable profanity filter. Hill uses it only as a bounded local lexical
check, not a semantic classifier, an endorsement of its labels, or a guarantee of
school safety. It can reject legitimate discussion and miss harmful language.
See `docs/operations/chat-safety.md` in the source repository for actual coverage
and operational limits.

## School policy supplement

`school-additions.txt` contains **88 entries selected verbatim from the same
pinned upstream vocabulary**, all rated 1. This promotes common swearing and
explicit sexual/genital terminology into the default school check without
blocking every ambiguous rating-1 word. It is a policy selection from an
established vocabulary, not a replacement tiny handwritten wordlist. Its exact
contents are visible in the adjacent file; the same MIT attribution applies.
The default therefore activates 1,343 upstream entries before operator additions.

## Integrity

SHA-256 values for UTF-8 files with LF line endings:

| File | SHA-256 |
| --- | --- |
| `cuss-en.js` | `1d18ada207c6551513c767492b9441619ceea0dfe0895552410040ee0c937223` |
| `cuss-LICENSE.txt` | `ca4662cb5d1b738fbe5350c0d5485ba11773b4b7208974082ae6e129a52d631d` |
| `school-additions.txt` | `10ddddadf5d4ec32cc9749ffbbc5ba936bdc4ec0dc6a423a4fa07a53acf38acf` |

The loader verifies both vocabulary hashes, structure and entry counts. It
normalizes CRLF to LF before hashing so Windows Git text conversion does not
break the pin. Missing, unreadable or changed vocabulary fails closed while
moderation is enabled. Upstream updates require deliberate review, new pinned
hashes/counts and updated attribution; the plugin never downloads list updates.
