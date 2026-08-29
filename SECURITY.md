# Security Policy

Shufflebase connects to databases you point it at and moves data between
them. It is meant to be run by a trusted operator (an engineer refreshing a
staging environment, a CI job) against infrastructure they already control —
not exposed as a public-facing service.

## Supported versions

Only the latest release and `master` receive security fixes. This is a young
project with no long-term-support branches yet.

## What's in scope

Report a vulnerability if you find:

- A way for a crafted database schema, column name, or row value to cause
  SQL to execute outside the parameterized queries this tool builds (a SQL
  injection path through table/column names reflected from the source
  database, for example).
- A masking or referential-integrity bug that causes `shufflebase run` to
  report success (`result.ok`) while the target database actually contains
  unmasked sensitive values or broken foreign keys. This is the tool's core
  promise, and a silent failure here is the most serious class of bug it can
  have.
- A way for the web dashboard (`shufflebase serve`) to read or write a
  database URL, credential, or file path other than the one an operator
  explicitly supplied in that request.
- A dependency with a known CVE that this project pulls in at a vulnerable
  version.

## What's out of scope

- The web dashboard and CLI trust the database credentials you give them —
  connecting to a database is the tool's job, not a vulnerability. Running
  `shufflebase serve` on a network where untrusted users can reach it and
  supply their own connection strings is a deployment mistake, not a bug in
  this project; the README says so explicitly.
- Denial-of-service via an intentionally enormous source database (v1 loads
  each table into memory during a run — see the README's Limitations
  section). This is a known, documented scaling limit, not a security issue.

## Reporting a vulnerability

Please report security issues privately via
[GitHub Security Advisories](https://github.com/Laaaaksh/shufflebase/security/advisories/new)
rather than a public issue. Include the version, a reproduction if you have
one, and the impact as you understand it. We'll acknowledge reports within a
few days.
