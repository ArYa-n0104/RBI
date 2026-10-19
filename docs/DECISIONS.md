# TAARR Decisions and Open Questions

This log makes design assumptions visible so we do not silently change the proposal. Decisions affect benchmark gold labels and must be versioned before annotation scales.

## Adopted for the initial dataset implementation

1. **Benchmark unit:** one target-obligation decision per item (query + reference date + entity profile + target obligation). This gives the specified single `gold_outcome` a stable meaning. An item may also link supporting and related obligations.
2. **Four outcomes:** `Applicable`, `Not applicable`, `Indeterminate`, `Conflict` only.
3. **Temporal intervals:** represent validity as start-inclusive/end-exclusive. Keep publication date and effective date distinct. Null end date means "not recorded" until verified.
4. **Human-reviewed gold:** model-assisted extraction may propose records; it does not create verified gold labels. Two annotators label independently, disagreements are adjudicated against official sources.
5. **Provenance:** gold clause/version references must point to official RBI/SEBI URLs and preserve paragraph/sub-paragraph identifiers.
6. **No synthetic gold labels:** the initial benchmark is empty. Examples used in unit tests must be clearly marked as synthetic software fixtures, never merged into the regulatory gold dataset.

## Must resolve before labelling affected edge cases

### D-001: No version is in force on the reference date

- **Build Plan**, "Novelty 2: Algorithm", page 3, says after temporal filtering: if no versions, continue/drop it ("superseded/not-yet-effective -> drop, don't hallucinate it in").
- **Review Paper**, Algorithm 1 on page 13, says if the valid-version set is empty, emit `NOT_APPLICABLE` with reason "not in force on t".
- **Why this matters:** absence of an in-force version is not automatically equivalent to a substantive finding of Not applicable. If the candidate is excluded from the considered obligations, no labelled decision may be emitted; if it is emitted, the gold label becomes Not applicable. These alternatives change benchmark item definition, precision/recall, and the product's user-facing semantics.
- **Safe implementation stance:** do not author benchmark items for this edge case until the supervisor/project owner chooses one policy. Keep the engine behavior behind an explicitly named policy rather than silently conflating absence of a version with an entity-condition failure.
- **Question for owner:** should an obligation with no valid version be dropped from the result set (Build Plan) or returned as `Not applicable` (Review Paper)?

### D-002: Missing facts versus false predicates

The Review Paper states that missing attributes evaluate to UNKNOWN in Kleene three-valued logic, and the Build Plan says missing required facts should emit Indeterminate before evaluating condition truth. Preserve that rule: absent fact is not false. The annotation guideline must identify exactly which profile attributes are required by the obligation.

### D-003: Decision ordering when applicability is unknown and an exemption may apply

The Review Paper's Algorithm 1 and Build Plan's Algorithm 1 order some operations differently. The Review Paper evaluates temporal versions, then applicability, exemptions and dependencies with three-valued logic. The Build Plan emits Indeterminate when facts needed for applicability are missing before exemption resolution and describes a more streamlined branch order. We need tests specifying whether a known exemption can definitively make a provision Not applicable when unrelated entity attributes are missing, and whether dependency conflicts take precedence over unknown facts. Don't freeze gold labels for these overlap cases until this ordering is adopted.

### D-004: Equal-priority conflict and precedence evidence

Only mark Conflict when authoritative in-force sources genuinely disagree and no documented precedence rule resolves the disagreement. Never invent priority numbers. Source links and adjudicator rationale are required.

## Next decision gate

Before scaling annotations, approve D-001 and D-003 in the annotation protocol and create executable tests for the chosen semantics. The corpus/data structure can be developed now without pretending these policy questions are settled.