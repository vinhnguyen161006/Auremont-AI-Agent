"""Which catalogue project a document belongs to.

Two consumers share one alias key (`canonical_scope_name`):

* the Admin document-coverage dashboard, which decides per project/category whether a
  document is ready, pending review, unavailable or missing;
* the document classifier, whose proposed project metadata is resolved here. The LLM may
  choose only from the live project catalogue, so an invented id never reaches the
  document foreign key, and an exact subdivision name maps to its catalogue row without
  fuzzy guessing.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypedDict

from sqlalchemy.orm import Session

from backend.core.enums import DocumentReviewStatus, DocumentStatus
from backend.models.document import Document
from backend.models.project import Project

CoverageState = Literal["ready", "pending_review", "unavailable", "missing"]

COVERAGE_CATEGORIES = (
    "subdivision_info",
    "sales_policy",
    "price_list",
    "floor_plan",
    "legal_document",
    "payment_schedule",
)


def canonical_scope_name(value: str) -> str:
    """Create an accent/case/punctuation-insensitive exact-match key."""

    decomposed = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9]+", without_marks))


def project_scope_aliases(project: Project) -> set[str]:
    """Derive exact aliases from a catalogue row's structured identity.

    Parent and sub-zone fields are deliberately excluded: they identify a group,
    not the row itself, and would leak one subdivision's documents into another.
    """

    raw_aliases: list[str] = [project.id, project.name]
    if " - " in project.name:
        raw_aliases.append(project.name.split(" - ", 1)[0].strip())

    return {canonical_scope_name(value) for value in raw_aliases if value.strip()}


def document_matches_project_scope(
    document: Document,
    project: Project,
    project_aliases: set[str] | None = None,
) -> bool:
    """Match an explicit project id or an exact canonical subdivision alias."""

    if document.project_id == project.id:
        return True
    if not isinstance(document.subdivision_names, list):
        return False

    aliases = project_aliases if project_aliases is not None else project_scope_aliases(project)
    document_scopes = {
        canonical_scope_name(value) for value in document.subdivision_names if isinstance(value, str) and value.strip()
    }
    return bool(document_scopes & aliases)


def document_coverage_state(
    documents: Iterable[Document],
    *,
    retrieval_project_id: str | None = None,
) -> CoverageState:
    """Summarise one project/category without reviving stale review records.

    A current, approved, completed document always wins because AI can use it. A
    current pending review remains actionable. Otherwise only the newest record
    controls the action state. This prevents an older superseded PENDING row from
    keeping the cell amber after a later upload failed, was blocked, or rejected.

    New quarantined LLM classifications carry ``classification_version`` and may
    legitimately be non-current while awaiting approval. Legacy non-current rows
    without that provenance are not presented as actionable reviews.

    ``document_matches_project_scope`` deliberately includes exact subdivision
    metadata so the Admin can find and repair legacy rows whose ``project_id`` is
    missing or wrong. Qdrant project-scoped retrieval, however, filters only its
    ``project_id`` payload. When ``retrieval_project_id`` is supplied, only a row
    carrying that exact id can make the cell ``ready``. A metadata-only LLM result
    may still be ``pending_review`` so the Admin sees the work queue; an already
    approved null/mismatched id is ``unavailable`` rather than falsely green.
    """

    related_rows = list(documents)
    if not related_rows:
        return "missing"

    retrieval_rows = (
        related_rows
        if retrieval_project_id is None
        else [row for row in related_rows if row.project_id == retrieval_project_id]
    )

    if any(
        row.is_current and row.status == DocumentStatus.COMPLETED and row.review_status == DocumentReviewStatus.APPROVED
        for row in retrieval_rows
    ):
        return "ready"

    if any(
        row.is_current and row.status == DocumentStatus.COMPLETED and row.review_status == DocumentReviewStatus.PENDING
        for row in retrieval_rows
    ):
        return "pending_review"

    latest = max(related_rows, key=lambda row: (row.created_at or datetime.min, row.id or -1))
    scope_is_actionable = bool(
        retrieval_project_id is None
        or latest.project_id == retrieval_project_id
        or latest.classification_version is not None
    )
    is_actionable_review = (
        latest.status == DocumentStatus.COMPLETED
        and latest.review_status == DocumentReviewStatus.PENDING
        and (latest.is_current or latest.classification_version is not None)
        and scope_is_actionable
    )
    if is_actionable_review:
        return "pending_review"

    return "unavailable"


class ProjectCatalogEntry(TypedDict):
    id: str
    name: str
    location: str | None


@dataclass(frozen=True)
class ProjectResolution:
    project_id: str | None
    requires_admin_review: bool = False
    note: str | None = None


def classification_project_catalog(db: Session) -> list[ProjectCatalogEntry]:
    """Return the complete DB catalogue, including rows hidden from the public page."""

    return [
        {"id": row.id, "name": row.name, "location": row.location}
        for row in db.query(Project).order_by(Project.name).all()
    ]


def resolve_classified_project(
    *,
    selected_project_id: str | None,
    suggested_project_id: str | None,
    subdivision_names: list[str] | None,
    catalog: list[ProjectCatalogEntry],
) -> ProjectResolution:
    """Resolve one safe project id while preserving an Admin's explicit upload choice.

    The LLM-proposed id must exist in ``catalog``.  When no project was selected during
    upload, a single exact subdivision-to-project match may fill the project id.  Conflicts
    are quarantined for Admin review instead of silently choosing one side.
    """

    catalog_ids = {entry["id"] for entry in catalog}
    suggested_is_valid = suggested_project_id in catalog_ids if suggested_project_id else False
    invalid_suggestion = bool(suggested_project_id and not suggested_is_valid)
    subdivision_matches = _matching_project_ids(subdivision_names or [], catalog)

    if selected_project_id:
        conflicts = set(subdivision_matches)
        if suggested_is_valid:
            conflicts.add(str(suggested_project_id))
        conflicts.discard(selected_project_id)
        if invalid_suggestion or conflicts:
            details = sorted(conflicts) or [str(suggested_project_id)]
            return ProjectResolution(
                project_id=selected_project_id,
                requires_admin_review=True,
                note=(
                    "Project do Admin chọn được giữ nguyên nhưng metadata LLM gợi ý phạm vi khác: "
                    + ", ".join(details)
                    + "."
                ),
            )
        return ProjectResolution(project_id=selected_project_id)

    if len(subdivision_matches) == 1:
        subdivision_project_id = next(iter(subdivision_matches))
        if suggested_is_valid and suggested_project_id != subdivision_project_id:
            return ProjectResolution(
                project_id=None,
                requires_admin_review=True,
                note=(
                    "Project LLM gợi ý mâu thuẫn với phân khu đã trích xuất: "
                    f"{suggested_project_id} / {subdivision_project_id}."
                ),
            )
        return ProjectResolution(project_id=subdivision_project_id)

    if len(subdivision_matches) > 1:
        if suggested_is_valid and suggested_project_id in subdivision_matches:
            return ProjectResolution(
                project_id=str(suggested_project_id),
                requires_admin_review=True,
                note="Tài liệu nhắc nhiều project/phân khu; cần Admin xác nhận phạm vi chính.",
            )
        return ProjectResolution(
            project_id=None,
            requires_admin_review=True,
            note="Tài liệu khớp nhiều project/phân khu; không tự gán một project duy nhất.",
        )

    if invalid_suggestion:
        return ProjectResolution(
            project_id=None,
            requires_admin_review=True,
            note=f"LLM trả project_id không tồn tại trong catalogue: {suggested_project_id}.",
        )

    return ProjectResolution(project_id=str(suggested_project_id) if suggested_is_valid else None)


def _matching_project_ids(
    subdivision_names: list[str],
    catalog: list[ProjectCatalogEntry],
) -> set[str]:
    aliases_by_id = {entry["id"]: _project_aliases(entry) for entry in catalog}
    matches: set[str] = set()
    for subdivision_name in subdivision_names:
        key = canonical_scope_name(subdivision_name)
        if not key:
            continue
        matches.update(project_id for project_id, aliases in aliases_by_id.items() if key in aliases)
    return matches


def _project_aliases(entry: ProjectCatalogEntry) -> set[str]:
    name = entry["name"]
    aliases = {canonical_scope_name(entry["id"]), canonical_scope_name(name)}
    if " - " in name:
        aliases.add(canonical_scope_name(name.split(" - ", 1)[0]))
    return {alias for alias in aliases if alias}
