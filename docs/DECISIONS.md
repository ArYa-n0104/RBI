# TAARR Decisions and Open Questions

This log makes design assumptions visible so we do not silently change the proposal. Decisions affect benchmark gold labels and must be versioned before annotation scales.

## Adopted for the initial dataset implementation

1. **Benchmark unit:** one target-obligation decision per item (query + reference date + entity profile + target obligation). This gives the specified single `gold_outcome` a stable meaning. An item may also link supporting and related obligations.
2. **Four outcomes:** `Applicable`, `Not applicable`, `Indeterminate`, `Conflict` only.
3. **Temporal intervals:** represent validity as start-inclusive/end-exclusive. Keep publication date and effective date distinct. Null end date means "not recorded" until verified.
4. **Human-reviewed gold:** model-assisted extraction may propose records; it does not create verified gold labels. Two annotators label independently, disagreements are adjudicated against official sources.
5. **Provenance:** gold clause/version references must point to official RBI/SEBI URLs and preserve paragraph/sub-paragraph identifiers.
6. **No synthetic gold labels:** the initial benchmark is empty. Examples used in unit tests must be clearly marked as synthetic software fixtures, never merged into the regulatory gold dataset.
7. **No in-force version (D-001):** adopt `NoVersionPolicy.NOT_APPLICABLE`, following Review Paper Algorithm 1. If an obligation has no version in force on the reference date, emit `Not applicable` with the temporal-filter reason and evidence. Do not silently drop the target-obligation decision.

## Open decisions before labelling affected edge cases

### D-001: No version is in force on the reference date — DECIDED

- **Build Plan**, "Novelty 2: Algorithm", page 3, says after temporal filtering: if no versions, continue/drop it ("superseded/not-yet-effective -> drop, don't hallucinate it in").
- **Review Paper**, Algorithm 1 on page 13, says if the valid-version set is empty, emit `NOT_APPLICABLE` with reason "not in force on t".
- **Decision:** adopt the Review Paper behavior: use `NoVersionPolicy.NOT_APPLICABLE`. Emit `Not applicable` for the target obligation, with a clear reason that no recorded version is in force on the reference date and with temporal-filter evidence. This is an explicit decision to report the considered target obligation, not to claim that its substantive applicability condition was evaluated and found false.
- **Consequences:** keep the policy explicit and recorded in experiment reports; test the no-active-version case; do not drop these target-obligation decisions from the result set under the selected policy. Do not create gold labels for real regulatory records until the exact source/version timeline has been verified.
- **Status:** project owner selected Option B in the conversation; the policy choice is frozen unless explicitly reopened.

### D-002: Missing facts versus false predicates

The Review Paper states that missing attributes evaluate to UNKNOWN in Kleene three-valued logic, and the Build Plan says missing required facts should emit Indeterminate before evaluating condition truth. Preserve that rule: absent fact is not false. The annotation guideline must identify exactly which profile attributes are required by the obligation.

### D-003: Decision ordering when applicability is unknown and an exemption may apply

The Review Paper's Algorithm 1 and Build Plan's Algorithm 1 order some operations differently. The Review Paper evaluates temporal versions, then applicability, exemptions and dependencies with three-valued logic. The Build Plan emits Indeterminate when facts needed for applicability are missing before exemption resolution and describes a more streamlined branch order. We need tests specifying whether a known exemption can definitively make a provision Not applicable when unrelated entity attributes are missing, and whether dependency conflicts take precedence over unknown facts. Don't freeze gold labels for these overlap cases until this ordering is adopted.

### D-004: Equal-priority conflict and precedence evidence

Only mark Conflict when authoritative in-force sources genuinely disagree and no documented precedence rule resolves the disagreement. Never invent priority numbers. Source links and adjudicator rationale are required.

## Next decision gate

D-001 is decided as above. D-003 remains open: before labeling cases where applicability is unknown and exemptions/dependencies may settle the result, approve the ordering semantics and add executable tests. The corpus/data structure can continue to develop without pretending D-003 is settled.