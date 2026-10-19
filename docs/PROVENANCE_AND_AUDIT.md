# Clause-Level Provenance and Audit Invariants

This is TAARR's third differentiating capability. The result evidence is a structured trace, not merely a free-text citation.

## Required evidence properties
- Every resolved result identifies target obligation, selected version, clause ID, official source URL and reference date when available.
- Every condition evaluation records the predicate and TRUE/FALSE/UNKNOWN result.
- Missing required facts are listed explicitly.
- Active exemption/dependency edges include relation ID, linked clause ID and official source URL.
- Recursive dependency results remain nested in the result.
- Version validity uses start-inclusive/end-exclusive dates.
- Verification status is carried through to the UI; source-located is not gold-verified.
- Any future LLM explanation may cite only IDs already present in the evidence record. The outcome remains the deterministic engine's value.

## Suggested audit checks
1. Every gold evidence source URL is non-empty HTTPS on the relevant official regulator domain.
2. Every evidence version_id and clause_id resolves to the frozen catalog snapshot.
3. Every active temporal relation is valid on the query date.
4. Explanation agrees with the structured outcome and evidence.
5. Persist request, policy, dataset snapshot, output and timing for reproducibility, while minimizing personal/sensitive entity data.

## Limitation
An evidence trace improves inspectability but does not itself prove a legal conclusion. Legal source/version verification and expert adjudication remain required.
