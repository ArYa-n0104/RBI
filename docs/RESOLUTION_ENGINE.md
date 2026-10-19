# Deterministic Resolution Engine

The engine is the executable core of TAARR's proposed contribution. It keeps the final decision separate from retrieval and natural-language explanation and emits evidence records that the UI can display as a provenance trail.

Implementation:
- `src/taarr/models.py` — typed obligation/version, exception, dependency, outcome, and policy records.
- `src/taarr/reasoning.py` — deterministic predicates, temporal filtering, version selection, exemption resolution, recursive dependencies, and evidence production.
- `tests/test_reasoning.py` — unit tests for the formal behaviour.

## Decision pipeline

1. Select versions whose interval satisfies `effective_from <= reference_date < effective_to`. A null end date is treated as open-ended in memory only because the record is already loaded; ingestion must separately track whether the end date was source-verified.
2. If one active version exists, use it. If overlapping active versions have different text, select a winner only when source-grounded precedence gives one unique winner; otherwise emit Conflict. Identical wording can be de-duplicated deterministically.
3. Evaluate applicability conditions against the entity profile using three-valued logic: TRUE, FALSE, UNKNOWN. Missing or null facts are UNKNOWN, never silently coerced to false.
4. Resolve active exceptions. Only source-grounded priorities are considered. Opposing effects without a documented, unique priority yield Conflict.
5. Resolve active prerequisite dependencies recursively. A dependency cycle yields Conflict rather than recursing indefinitely.
6. Return one of Applicable, Not applicable, Indeterminate, or Conflict with a reason and evidence chain.
7. Explanation generation is not implemented in this module; later it will consume the evidence and must not change the outcome.

## Predicate syntax

Atomic condition:

```json
{
  "attribute": "entity.layer",
  "operator": "equals",
  "value": "upper"
}
```

Supported operators: `equals`/`eq`, `not_equals`/`ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, and `contains`. A missing attribute returns UNKNOWN. A value of the wrong type is also treated as UNKNOWN and recorded as a missing/corrective fact, rather than guessed.

Compound conditions:

```json
{
  "all_of": [
    {"attribute": "is_rbi_regulated_entity", "operator": "equals", "value": true},
    {"attribute": "entity.layer", "operator": "in", "value": ["middle", "upper"]}
  ]
}
```

Supported compound nodes: `all_of`, `any_of`, and `not`. Kleene AND uses FALSE if any child is FALSE; otherwise UNKNOWN if any child is UNKNOWN; otherwise TRUE. Kleene OR uses TRUE if any child is TRUE; otherwise UNKNOWN if any child is UNKNOWN; otherwise FALSE.

## Explicit policy choices — not yet frozen

The Build Plan and Review Paper differ on the following points. The engine makes these explicit constructor arguments so test runs cannot silently make the decision:

- `NoVersionPolicy.DROP`: return no outcome if no version is in force (Build Plan).
- `NoVersionPolicy.NOT_APPLICABLE`: emit Not applicable if no version is in force (Review Paper Algorithm 1).
- `MissingFactsPolicy.STRICT_MISSING`: any missing applicability attribute results in Indeterminate before evaluating other conditions (Build Plan).
- `MissingFactsPolicy.KLEENE`: evaluate the full Boolean condition with Kleene three-valued logic (Review Paper).
- `UnknownPrecedencePolicy.INDETERMINATE_FIRST`: once applicability is UNKNOWN, abstain before checking exceptions/dependencies.
- `UnknownPrecedencePolicy.DEFINITIVE_RULES_FIRST`: allow a definitive, verified exemption or conflict to settle the result before returning Indeterminate for unresolved facts.

No shared default policy is set in the library. A benchmark run must serialize and report the policy selection. See GitHub issue [#1](https://github.com/ArYa-n0104/RBI/issues/1) before assigning final gold labels to edge cases.

## Minimal use

```python
from datetime import date

from taarr.models import (
    ClauseVersion,
    MissingFactsPolicy,
    NoVersionPolicy,
    Obligation,
    ResolverPolicy,
    UnknownPrecedencePolicy,
)
from taarr.reasoning import resolve_obligation

record = Obligation(
    obligation_id="RBI-KYC-P38E-DUE-NOTICES",
    versions=(
        ClauseVersion(
            obligation_id="RBI-KYC-P38E-DUE-NOTICES",
            version_id="RBI-KYC-P38E-v1",
            clause_id="paragraph-38(e)",
            official_url="https://www.rbi.org.in/scripts/NotificationUser.aspx/searchnew/searchnew/NotificationUser.aspx?Id=12866",
            clause_text="The RE shall intimate its customers, in advance, to update their KYC.",
            effective_from=date(2025, 6, 12),
            effective_to=None,
            applicability_condition={
                "attribute": "is_rbi_regulated_entity",
                "operator": "equals",
                "value": True,
            },
        ),
    ),
)
configuration = ResolverPolicy(
    no_version=NoVersionPolicy.DROP,
    missing_facts=MissingFactsPolicy.KLEENE,
    unknown_precedence=UnknownPrecedencePolicy.DEFINITIVE_RULES_FIRST,
)
result = resolve_obligation(
    "RBI-KYC-P38E-DUE-NOTICES",
    {record.obligation_id: record},
    date(2025, 7, 1),
    {"is_rbi_regulated_entity": True},
    configuration,
)
print(result.to_dict() if result is not None else None)
```

The values above show how to use the API, not a frozen TAARR global policy. Replace the choices only after the ambiguity is resolved and reflected in the benchmark annotation guide.

## Verification

```bash
python -m pytest tests/test_reasoning.py
ruff check src tests
```

Tests validate software logic with fixtures; they do not substitute for legal adjudication of source records.
