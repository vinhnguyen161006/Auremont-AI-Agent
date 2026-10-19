# Customer question coverage

The customer questions that cannot be solved just by adding to the prompt. Every answer must come from the right source of truth; when that source lacks a needed field, the chatbot must say exactly what is missing and ask for more data or hand over to a consultant.

## Data source matrix

| Question group | Source of truth | Status |
|---|---|---|
| Location, developer, scale, unit types, areas, handover, ownership overview | `Project.details.project` | In the structured context |
| Price by unit type | `Project.details.pricing` | Supported as indicative catalogue prices |
| Amenities | `Project.details.amenities` | In the structured context |
| Payment, discount and loan policies | `Project.details.sales_policies` and approved documents | Answered where data exists; a policy with no effective date must be confirmed |
| Available units, unit codes, per-unit area and price | Inventory API | Real-time route in place; PDFs/catalogue must never confirm availability |
| Unit/tower floor plans | Gallery and image metadata | Images available when files are mapped to the right project, tower and unit type |
| Detailed legal terms, permits, guarantees, contracts | Approved legal documents in RAG | Answered only once the document is uploaded, classified and approved |
| Orientation, view, floor, corner unit, near lift/trash room, noise | Unit-level attributes in inventory | Schema/data not yet complete for every project |
| VAT, maintenance fee, management fee, parking, utilities | Fee tables/policies with effective dates | Normalised data not yet available |
| Amount per payment instalment | Unit price + payment schedule with percentages and dates | Needs a calculator and a structured payment schedule |
| Loan amount and monthly payment | Unit price, own capital, LTV, term, staged interest rates, repayment method | Needs a calculator; rates/terms must never be chosen by the model |
| Travel time, congestion, future infrastructure | Dated map/traffic data and official planning documents | Not available; must not be estimated from the location description |
| Rent, yield, liquidity, price growth | Dated transaction/rental data and comparables | Not available; only scenarios may be computed, never presented as forecasts |
| Holding a unit, deposits, viewings, meeting a consultant | CRM/booking/hold service | The lead is marked HOT; real actions need the corresponding service integration |

## Answering rules

1. Inventory beats the catalogue and static documents for a unit code or current status.
2. Catalogue prices must be labelled as an indicative range, not the final price of an available unit.
3. Policies, offers and interest rates without `effective_from`, `effective_to` or `as_of` must be re-confirmed.
4. Never infer orientation/view/floor/noise/legal status/travel time from a project name or an image.
5. Financial calculations only run with complete inputs and must show the formula, assumptions and effective date.
6. A multi-part question is answered part by part: give the parts with evidence, name exactly what is missing, then propose the next step.

## Data still needed

### Unit-level inventory

Add the fields `tower`, `floor`, `direction`, `view`, `is_corner`, `near_elevator`, `near_trash_room`, `noise_notes`, `gross_area_m2`, `net_area_m2`, `price_vnd`, `status`, `status_as_of`, `holdable_until` and the update source.

### Commercial policies

Normalise `deposit_amount`, the list of payment instalments (`percentage`, `due_date` or condition), VAT/maintenance fee, discounts, gifts, banks, LTV, interest-support period, post-promotion rate, early-repayment fee and `effective_from`/`effective_to`.

### Legal and handover

Every claim needs a `document_id`, document number, issue date, issuing authority, scope and approval status. Handover specifications need the brand/model or an exact description, ceiling height, glass type, fire safety, schedule and last-updated date.

### Operations and investment

Fee tables need effective dates. Investment data needs comparable transactions, leases or market sources, geographic scope, time period and sample size; results are shown as scenarios, never as a profit commitment.

## HOT lead scoring

Clear transaction intents are marked HOT immediately by rule: deposits/money transfers, asking for the latest stock list, viewing a real or show unit, checking whether a unit is still available, holding a unit, asking for a specific policy/schedule, computing instalments or a loan, preparing/signing deposit or contract paperwork, meeting staff and scheduling a visit. The signal persists across later turns so a "thank you" does not cool the lead down.

## Acceptance tests

Every question in the question set should be labelled with:

- `source`: `project_profile`, `inventory`, `document`, `calculator`, `crm` or `unsupported`;
- `freshness`: whether current data is required;
- `must_include`: required facts or warnings;
- `must_not_claim`: what the chatbot must not infer;
- `lead_tier`: `HOT` for the 12 transaction questions.

The tests must cover accented and unaccented questions, multi-part questions, near-synonymous phrasings and failures of a dependent source.
