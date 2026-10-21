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

### D-003: Decision ordering when applicability is unknown and an exemption may apply — DECIDED

The Review Paper's Algorithm 1 and Build Plan's Algorithm 1 order some operations differently. The Review Paper evaluates temporal versions, then applicability, exemptions and dependencies with three-valued logic. The Build Plan emits Indeterminate when facts needed for applicability are missing before exemption resolution and describes a more streamlined branch order.

- **Decision:** adopt `UnknownPrecedencePolicy.DEFINITIVE_RULES_FIRST` (the Review Paper's ordering): when applicability is `UNKNOWN`, do not abstain immediately. Evaluate exemptions and dependencies first. A definite (non-`UNKNOWN`) exemption or dependency result can settle the outcome (`Not applicable` or `Conflict`) even while applicability itself remains unknown — a system that can abstain is weaker than one that resolves on dispositive evidence it already has. Only when no definite rule settles the case does unresolved applicability fall through to `Indeterminate`.
- **Consequences:** `resolve_obligation` in `src/taarr/reasoning.py` already implements this branch order, and `.env.example` already sets `TAARR_UNKNOWN_PRECEDENCE_POLICY=DEFINITIVE_RULES_FIRST`. This entry only catches the documentation up to that implemented and configured behavior. `INDETERMINATE_FIRST` remains available in `UnknownPrecedencePolicy` as a documented diagnostic baseline (ablation), never the production policy.
- **Status:** frozen. Gold labels may now be created for overlap cases where applicability is unknown and an exemption/dependency is definite, provided the annotation packet records which rule was dispositive.

### D-004: Equal-priority conflict and precedence evidence

Only mark Conflict when authoritative in-force sources genuinely disagree and no documented precedence rule resolves the disagreement. Never invent priority numbers. Source links and adjudicator rationale are required.

### D-005: Project owner opted out of the annotator role — DECIDED

On 2026-10-21, after the catalog had grown to 60 obligations (all source-located, none gold-verified), the project owner explicitly asked the assistant to perform full verification alone and said: "please do the verification on your own, i am not able to do such a large data verification, exclude me from this role." This changes what verification tiers are actually reachable without a new human annotator.

- **What stays true regardless:** `gold_verified` still requires two annotators who worked independently (per `ANNOTATION_PROTOCOL.md`) plus adjudication. One person checking something twice is not independent dual-annotation, however carefully it is done. The assistant will not mark anything `gold_verified`, `dual_annotated`, or `adjudicated` under this decision, and will not reuse "annotator_1"/"annotator_2" fields to simulate independence that does not exist.
- **What "single_pass_reviewed" means from this point on:** `DATASET_SPEC.md`'s original definition of this tier included project-owner review and approval. With the owner opted out, that is no longer what happens. From 2026-10-21 onward, an obligation or benchmark item reaching `single_pass_reviewed` (or the matching catalog `verification_status`) means: the clause was fetched from the official source at least twice, independently, in separate tool calls, by the assistant, and the two fetches agreed (or a disagreement was found and corrected -- see the 2026-10-21 regulation-2(1)(zb)/(zc) correction for a real example). It does **not** mean a human reviewed or approved it. This is a real weakening of the tier's original meaning, done openly rather than left implicit.
- **Why this is still worth doing:** a second independent fetch catches real mistakes a first pass alone would not -- it already found and fixed one mis-citation (see above). That is strictly better than a single uncorroborated pass. It is still not equivalent to a human legal reviewer, and the paper's threats-to-validity section must say so plainly: **no human has reviewed the substantive legal correctness of the 2026-10-21 bulk-added obligations.**
- **Consequences:** `docs/DATASET_SPEC.md`'s `single_pass_reviewed` section and `src/taarr/dataset.py`'s inline comment are updated to describe this owner-opted-out meaning. If the owner later wants to resume the annotator_1 role, or a different second human reviewer is found, that reopens the path toward genuine `gold_verified` labels; nothing here forecloses it.
- **Important: the `annotation_status`/`verification_status` string alone does not say which kind of check happened.** The 5 draft items marked `single_pass_reviewed` before 2026-10-21 (`TAARR-DRAFT-0001`..`0005`) genuinely went through the original meaning: the owner checked source text via screenshots and approved the outcome logic -- that is recorded in their own `annotations.source_verification_human_check` / `annotations.outcome_logic_review` fields, which remain true and unchanged. Everything promoted to `single_pass_reviewed` **on or after 2026-10-21** instead carries `annotations.single_pass_review = {"checked_by": "assistant_solo_refetch", "owner_reviewed": false, ...}`, marking the weaker, owner-opted-out meaning. Anyone reading this dataset must check the `annotations` payload, not just the status string, to know which of the two actually happened for a given item.
- **Status:** frozen. Reopen only if the owner wants to resume a review role, or a second human becomes available.

## Next decision gate

D-001 and D-003 are decided as above. D-002 and D-004 are preserved as drafting/labelling guidance, not open-ended choices: D-002 is implemented as `MissingFactsPolicy.KLEENE` (see `.env.example`), and D-004 governs how annotators and `_resolve_exception_effects` justify a `Conflict` label — both remain the live policy unless explicitly reopened here. The next gate is dataset scale, not algorithm ambiguity: grow the catalog past the single RBI-KYC-P38E pilot obligation and produce the first `gold_verified` benchmark items.