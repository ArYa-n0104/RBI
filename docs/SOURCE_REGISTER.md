# Official Source Register

This register begins the feasibility pilot described in the TAARR Build Plan and Review Paper. Links below were located on official RBI/SEBI properties during project bootstrap. They are **candidate acquisition sources**, not yet a complete, clause-by-clause verified amendment history. Before producing gold labels, capture each source locally, record its exact publication/effective dates, and confirm whether a later consolidation or amendment exists.

## Pilot instruments

| Source ID | Regulator | Instrument/source | Official source | Current status |
|---|---|---|---|---|
| RBI-KYC-CONSOLIDATED | RBI | Master Direction - Know Your Customer (KYC) Direction, 2016. An RBI results page lists an updated copy as of 14 Aug 2025. | https://old.rbi.org.in/commonman/English/Scripts/MasterDirection.aspx | Candidate consolidated text located; verify it remains the latest consolidated version and reconcile amendment documents before annotation. |
| RBI-KYC-AMEND-2025-06-12 | RBI | Reserve Bank of India (Know Your Customer (KYC)) (Amendment) Directions, 2025, circular RBI/2025-26/51 dated 12 Jun 2025. The official page states immediate effect and includes modifications to paragraph 38. | https://www.rbi.org.in/scripts/NotificationUser.aspx/searchnew/searchnew/NotificationUser.aspx?Id=12866 | Official amendment candidate located; clause-level mapping and effective intervals not yet verified in this repository. |
| RBI-KYC-AMEND-2024-11-06 | RBI | Amendment to the KYC Master Direction, RBI/2024-2025/87, dated 6 Nov 2024. | https://systemhealth.rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx_Id%3D12746.html | Official RBI-hosted index copy located; confirm canonical link and relate exact clauses to the consolidated text. |
| SEBI-LODR-CONSOLIDATED | SEBI | Securities and Exchange Board of India (Listing Obligations and Disclosure Requirements) Regulations, 2015; official SEBI page marked last amended 14 Jul 2026. | https://www.sebi.gov.in/legal/regulations/jul-2026/securities-and-exchange-board-of-india-listing-obligations-and-disclosure-requirements-regulations-2015-last-amended-on-july-14-2026-_102974.html | Current consolidated candidate located; download linked regulation and reconstruct individual clause amendment chronology. |
| SEBI-LODR-ORIGINAL-2015 | SEBI | Original 2015 LODR Regulations page with a list of subsequent amendment notifications. | https://www.sebi.gov.in/legal/regulations/sep-2015/sebi-listing-obligations-and-disclosure-requirements-regulations-2015_31425.html | Historical starting point located; enumerate and verify relevant amendment instruments for each clause chosen in the pilot. |

## Acquisition checklist (one record per source)

Track at least:
- source_id, regulator, instrument title and document type;
- official URL, retrieval timestamp, local relative file path, MIME type, and SHA-256 hash;
- publication/notification date separately from commencement/effective date;
- source's own "updated as on" date when applicable;
- amendment instrument IDs and exactly which clauses are inserted, substituted, omitted, or repealed;
- extraction status, text-quality issues, human reviewer, and review status.

Avoid using third-party summaries as the controlling source for gold labels. If an official page is inaccessible, record that failure and locate an alternative official source rather than silently substituting a blog or search snippet.

## Immediate data pilot

1. Capture the latest official RBI KYC consolidation and the official amendment notifications relevant to it.
2. Capture the latest official SEBI LODR consolidated text and amendment notifications for the selected clauses.
3. Choose a small number of clauses where the relevant original and amended text and effective dates can be established.
4. Build a clause/version table from official wording; do not infer commencement date from publication date when the instrument states otherwise.
5. Decide feasibility based on traceable amendment lineages and varied entity applicability, not simply on the number of PDFs found.

## Source discovery references

The initial discovery found the RBI KYC consolidation index and the 12 June 2025 amendment on RBI domains, and the July 2026 LODR consolidation on the SEBI domain. These links should be re-opened during acquisition because regulatory pages and consolidations may change. This register records the state of source discovery, not a claim that the dataset is complete.