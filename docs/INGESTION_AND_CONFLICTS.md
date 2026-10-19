# Ingestion and conflict checks

## From file to RAG

The upload endpoint works in this order:

1. Create the `documents` row in `pending`, then move it to `processing`.
2. Check the magic bytes, then parse the PDF/DOCX into sections with page numbers; strip NUL bytes, drop empty sections and scan for prompt injection.
3. Send the filename and the full parsed text to Gemini with a structured-output schema. The LLM picks the primary category and returns all available metadata (`subcategory`, scope, unit types, summary, version, dates, legal metadata, confidence, reason, `requires_admin_review`). There is no keyword/regex classifier and no local fallback.
4. Pydantic validates enums, date types, confidence in 0-1, lists and date ordering. An API error, an empty response or a schema mismatch marks ingestion `failed` before any vector is created. A valid response is currently auto-approved by ingestion; `requires_admin_review` is stored as a signal but does not yet block publication.
5. Store the suggested metadata in MySQL and the original file in MinIO.
6. Chunk by category: legal, table (`price_list`, `inventory_snapshot`, `payment_schedule`) or general.
7. Embed in batches and upsert into Qdrant with `is_current=false`.
8. Hold a MySQL advisory lock per `project_id + category`, end the old read snapshot, then scan for conflicts/duplicates against `completed` documents in the same scope.
9. Commit the MySQL decision while Qdrant is still quarantined. Only a clean, legally active document is published with `is_current=true`. If the publish loses its ACK, MySQL keeps the committed decision and the drift is fixed by retrying the sync (for example a re-index), instead of marking the document `failed` and creating a fail-open state.

RAG fetches points that satisfy `is_current=true`, visibility and the project filter together. `review_status` is not part of the retrieval filter yet.

## Editing metadata after ingestion, and visibility

- The metadata page lists `completed` documents so an Admin can correct the LLM's metadata after ingestion; it is not an approval queue.
- PATCH keeps every field that is not sent.
- Changing `category` returns `409` because it needs quarantine, a conflict rescan and a controlled re-index. Changing `subdivision_names`, `building_codes` or `unit_types` also returns `409` because it needs a conflict rescan. The UI locks these fields instead of allowing an unsafe payload-only correction.
- A metadata update runs in two phases: phase 1 writes the metadata to Qdrant with `is_current=false` while holding the row lock, then commits MySQL; phase 2 locks and re-reads the latest row and only then publishes the real `is_current`. A phase 2 failure leaves the document safely quarantined.
- Legal status `not_yet_effective`, `expired`, `repealed` or `replaced` always keeps `is_current=false`.
- Visibility can only change once ingestion is `completed`. `internal → public` quarantines first, commits MySQL, then publishes from the freshly re-read row. `public → internal` writes the more restrictive level to Qdrant before the MySQL commit.

## When two documents are compared

Two documents are only compared when:

- they have the same category;
- they belong to the same project, or neither has a project;
- their metadata does not prove they cover separate scopes.

Scope is judged hierarchically:

- subdivisions or buildings present on both sides but with no overlap are evidence of separate scopes;
- the same subdivision/building must still be compared even when the unit-type lists differ, because the difference may be a version that adds or removes unit types;
- only when no location overlaps can unit types that are present but disjoint separate the scopes;
- empty metadata means "unknown", not evidence of a different scope.

After the scope step:

- `price_list`: compare prices by normalised code (`BE1-1201` and `BE1.1201` are the same code), understanding tables with VND in the header, compound amounts such as `3 tỷ 500 triệu` and the form `3.500 triệu`; footnotes/conditions such as "đã gồm VAT" versus "chưa gồm VAT" are compared too;
- other categories: compare the same clause anchor when a percentage, amount, date, duration or value position changes;
- the text comparator catches affirmative/negative changes such as "được" versus "không được";
- for categories other than `price_list`, the same title after removing the extension, separators and version/edition/month/batch/quarter markers is a fallback conflict if the meaningful content still differs;
- legal documents with the same document number are treated as the same identity even if the uploaded titles differ;
- different titles need a shared fact, polarity or legal-identity anchor;
- without a project, an extra title/legal identity, metadata overlap, shared price code or shared fact anchor is required;
- a different version/period does not rule out a conflict, because retrieval does not yet filter by effective date.

Exactly identical or meaningfully normalised identical content is a duplicate, not a conflict. The new upload is `blocked`, `rejected`, `is_current=false`, and the duplicate's ID is stored in the classification reason so it does not take up top-k slots or citations. A missing source for a sibling makes the scan fail closed; the new document is not activated.

## Resolving a conflict

- Lock the related conflicts, inactive relations and documents in a fixed order.
- The winner must be `completed`, must not carry a legal status that is not yet or no longer in force, and must not be the target of an approved `REPLACES`, `SUPERSEDES` or `REPEALS` relation.
- Phase 1 quarantines both the loser and the winner in Qdrant, then commits the MySQL decision. A timeout therefore cannot publish an Admin decision that was never committed.
- Phase 2 locks and re-reads the winner, and only enables it if no OPEN conflict remains and no other relation retired it between the two phases.
- Remaining OPEN edges whose endpoints are both `blocked` are closed automatically.
- If the commit outcome is unknown, there is no compensation that re-enables old data; both sides stay quarantined for a safe retry.

## Replace / repeal relations

When `REPLACES`, `SUPERSEDES` or `REPEALS` is approved:

- source and target are locked in ID order;
- the source must be `completed`, `approved`, `is_current=true` and legally active;
- the target must also be a `completed`, `approved`, current document, so an upload still `processing` cannot be retired;
- the target is switched off in Qdrant before the MySQL commit; the target becomes `blocked`, `is_current=false`;
- `REPEALS` sets the target's legal status to `repealed`; the target of `REPLACES/SUPERSEDES` becomes `replaced`;
- if the commit loses its ACK, the target stays quarantined instead of being revived by compensation.
