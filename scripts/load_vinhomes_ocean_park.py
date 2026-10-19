"""Load Vinhomes Ocean Park sample data: JSON -> MySQL (projects table).

The gallery comes from the image manifest, like the other catalogue loaders, so the first
boot and every later `_sync_catalogue_galleries` pass agree on the same photos.

Run manually, once, whenever the demo data needs a refresh:
    python scripts/load_vinhomes_ocean_park.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.mysql_client import SessionLocal  # noqa: E402
from backend.models.project import Project  # noqa: E402
from scripts._gallery import gallery_by_slug  # noqa: E402

JSON_PATH = REPO_ROOT / "seed-data" / "vinhomes_ocean_park.json"


def load_project() -> None:
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    project = payload["project"]
    gallery_urls = gallery_by_slug().get(project["id"], [])
    payload["images"]["gallery"] = gallery_urls
    location = f"{project['location']['district']}, {project['location']['city']}"

    db = SessionLocal()
    try:
        row = db.get(Project, project["id"])
        if row is None:
            row = Project(id=project["id"])
            db.add(row)
        row.name = project["name"]
        row.location = location
        row.description = project["description"]
        row.details = payload
        db.commit()
        print(f"[mysql] upsert project '{project['id']}' OK ({len(gallery_urls)} gallery images)")
    finally:
        db.close()


def main() -> None:
    load_project()


if __name__ == "__main__":
    main()
