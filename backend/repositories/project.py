import uuid

from sqlalchemy import event
from sqlalchemy.orm import Session

from backend.models.project import Project
from backend.schemas.project import ProjectCreate


def create_project(db: Session, schema: ProjectCreate) -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        name=schema.name,
        location=schema.location,
        description=schema.description,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def ensure_seed_project(
    db: Session,
    project_id: str,
    name: str,
    location: str | None = None,
    description: str | None = None,
) -> Project:
    """Create a project with a fixed id, or bring an existing one back to that state.

    Uses an explicit id rather than the generated UUID from `create_project` because
    seeded projects must be referable by a stable, readable slug: `INVENTORY_API_URL`
    is queried with `project_id`, so the value has to match the mock/internal API's
    data (see README §6.2.1) and stay identical across machines and restarts.
    """
    project = db.query(Project).filter(Project.id == project_id).first()

    if project is None:
        project = Project(id=project_id, name=name, location=location, description=description)
        db.add(project)
    else:
        project.name = name
        project.location = location
        project.description = description

    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session) -> list[Project]:
    return db.query(Project).order_by(Project.name).all()


def get_project(db: Session, project_id: str) -> Project | None:
    return db.query(Project).filter(Project.id == project_id).first()


_ALL_PROJECTS_KEY = "salesmate.all_projects"


def all_projects(db: Session) -> list[Project]:
    """Every project, loaded once per DB session instead of once per caller.

    One chat turn resolves scope, images, catalogue offers and tower context, and each
    of those scanned the whole table again — several full reads of every project's
    `details` JSON per question. A request owns its session, so the list lives exactly as
    long as the request; any flush, commit or rollback drops it (see `_forget_projects`),
    so a write is never answered from a stale copy. Sessions without a real `info` dict
    (test doubles) fall through to a plain query.
    """
    info = getattr(db, "info", None)
    if not isinstance(info, dict):
        return db.query(Project).all()
    cached = info.get(_ALL_PROJECTS_KEY)
    if cached is None:
        cached = info[_ALL_PROJECTS_KEY] = db.query(Project).all()
    return list(cached)


@event.listens_for(Session, "after_flush")
@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_rollback")
def _forget_projects(session: Session, *_args) -> None:
    session.info.pop(_ALL_PROJECTS_KEY, None)
