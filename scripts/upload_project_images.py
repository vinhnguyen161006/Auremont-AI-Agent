"""Upload every subdivision image from project-images-source/ to MinIO.

The source of the floor-plan/perspective/layout images used by the catalogue pages
(Zurich, Beverly, London, Paris, Sapphire, Senique Hanoi, Ocean View, Zenpark,
Pavilion, Palma...) — these images are NOT in the `projects` table (JSON details), so
they do not go through load_vinhomes_ocean_park.py; frontend code points straight at
MinIO URLs of the form `http://<endpoint>/project-images/<slug>/<filename>`.

These images used to exist only in a MinIO Docker volume on one machine (they cannot be
pushed to git), so teammates who cloned the repo saw broken images (404). This script
fixes that: run it once after `docker compose up -d minio` to reload the data from the
folder committed in the repo.

Run:
    python scripts/upload_project_images.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.config import get_settings  # noqa: E402
from backend.core.minio_client import ensure_public_read_bucket, get_minio_client, public_object_url  # noqa: E402

SOURCE_DIR = REPO_ROOT / "project-images-source"


def main() -> None:
    settings = get_settings()
    ensure_public_read_bucket(settings.minio_bucket_project_images)
    client = get_minio_client()

    if not SOURCE_DIR.exists():
        print(f"[error] Folder {SOURCE_DIR} not found; there are no source images to upload.")
        return

    uploaded = 0
    for path in sorted(SOURCE_DIR.rglob("*")):
        if not path.is_file():
            continue
        object_name = path.relative_to(SOURCE_DIR).as_posix()
        client.fput_object(settings.minio_bucket_project_images, object_name, str(path))
        print(f"[minio] uploaded {object_name}")
        uploaded += 1

    if uploaded == 0:
        print("[error] No image files found in project-images-source/.")
        return

    print(f"\nDone: uploaded {uploaded} images to bucket '{settings.minio_bucket_project_images}'.")
    print(f"Spot check: {public_object_url(settings.minio_bucket_project_images, 'the-zurich')}...")


if __name__ == "__main__":
    main()
