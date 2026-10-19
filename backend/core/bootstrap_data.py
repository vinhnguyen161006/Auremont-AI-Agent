"""Load demo data (images -> MinIO, catalogue -> MySQL) as soon as the backend starts.

Three scripts used to have to be run by hand after `docker compose up`; anyone who
skipped that step got an empty catalogue page and every image broken, with nothing
pointing at the cause. The goal of this module: clone the repo, `docker compose up`, done.

Project images are NOT in git (~58 MB). They live on S3/R2 and are downloaded into
MinIO here, following the list in seed-data/project_images_manifest.json.

There are two sources:

* `PROJECT_IMAGES_BASE_URL` — a public folder (R2 public URL, public S3, CDN); each
  manifest path is appended to the base. Read anonymously: no credentials, so no API
  key has to be handed to the whole team just to see images.
* `PROJECT_IMAGES_ARCHIVE_URL` — a single .tar.gz file; one request instead of ~180.

Three required properties:

* **Idempotent** — images already in MinIO are skipped, and the catalogue load is only
  skipped when the catalogue already has data. Images are still reconciled on every
  start so an old MinIO is never stuck forever when the manifest gains new files.
* **Never blocks startup** — a broken source, MinIO not being ready or a missing
  environment variable only degrades the demo data; none of them is a reason for the
  whole API to go down.
* **Never reaches the Internet unless configured** — with neither variable set the step
  is skipped quietly with one log line, without guessing a URL.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, cast
from urllib.parse import urljoin

from backend.core.config import get_settings
from backend.core.mysql_client import SessionLocal
from backend.models.project import Project

logger = logging.getLogger(__name__)

_DOWNLOAD_WORKERS = 8
_DOWNLOAD_TIMEOUT_SECONDS = 30
_ARCHIVE_TIMEOUT_SECONDS = 300


def _catalogue_is_loaded() -> bool:
    """True only when every catalogue record shipped in seed-data is loaded.

    One populated project is not a complete catalogue. Treating it as complete leaves a
    partially seeded deployment stuck forever because every later restart skips all
    loaders. Expected IDs are discovered from data files, not duplicated in code.
    """
    db = SessionLocal()
    try:
        loaded_ids = {row.id for row in db.query(Project).all() if row.details}
        expected_ids = _expected_catalogue_ids()
        return bool(expected_ids) and expected_ids <= loaded_ids
    finally:
        db.close()


def _expected_catalogue_ids() -> set[str]:
    root = Path(__file__).resolve().parents[2] / "seed-data"
    paths = [root / "vinhomes_ocean_park.json"]
    paths.extend((root / "apartments").glob("*.json"))
    paths.extend((root / "villas-shops").glob("*.json"))

    ids: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            project_id = ((payload.get("project") or {}).get("id") or "").strip()
            if project_id:
                ids.add(project_id)
        except (OSError, ValueError, TypeError):
            logger.warning("Could not read catalogue seed file %s.", path, exc_info=True)
    return ids


def _read_manifest() -> list[str]:
    path = Path(__file__).resolve().parents[2] / "seed-data" / "project_images_manifest.json"
    if not path.exists():
        logger.warning("No image manifest at %s; skipping the image download step.", path)
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("images", [])


def _download_archive_to_minio(archive_url: str) -> int:
    """Download one .tar.gz holding every image and load it into MinIO. Returns the number of new images."""
    import tarfile
    import tempfile

    import httpx
    from minio.error import S3Error

    from backend.core.minio_client import ensure_public_read_bucket, get_minio_client

    settings = get_settings()
    bucket = settings.minio_bucket_project_images
    ensure_public_read_bucket(bucket)
    client = get_minio_client()

    existing = {o.object_name for o in client.list_objects(bucket, recursive=True)}
    wanted = set(_read_manifest())
    if wanted and wanted <= existing:
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        archive_path = f"{tmp}/images.tar.gz"
        with httpx.stream("GET", archive_url, timeout=_ARCHIVE_TIMEOUT_SECONDS, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(archive_path, "wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                    fh.write(chunk)

        loaded = 0
        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                name = member.name.lstrip("./")
                if name.startswith("/") or ".." in name.split("/"):
                    logger.warning("Skipping unexpected path in the archive: %r", member.name)
                    continue
                if name in existing:
                    continue
                member_stream = tar.extractfile(member)
                if member_stream is None:
                    continue
                try:
                    client.put_object(bucket, name, cast(BinaryIO, member_stream), length=member.size)
                    loaded += 1
                except S3Error:
                    logger.warning("Uploading image '%s' to MinIO failed.", name, exc_info=True)
    return loaded


def _download_images_to_minio(base_url: str) -> int:
    """Tai anh tu CDN vao MinIO. Tra ve so anh da tai moi."""
    import httpx
    from minio.error import S3Error

    from backend.core.minio_client import ensure_public_read_bucket, get_minio_client

    settings = get_settings()
    bucket = settings.minio_bucket_project_images
    ensure_public_read_bucket(bucket)
    client = get_minio_client()

    images = _read_manifest()
    if not images:
        return 0

    def fetch_one(object_name: str) -> bool:
        try:
            try:
                client.stat_object(bucket, object_name)
                return False
            except S3Error:
                pass

            url = urljoin(base_url.rstrip("/") + "/", object_name)
            resp = httpx.get(url, timeout=_DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True)
            resp.raise_for_status()
            client.put_object(
                bucket,
                object_name,
                BytesIO(resp.content),
                length=len(resp.content),
                content_type=resp.headers.get("content-type", "image/jpeg"),
            )
            return True
        except Exception:
            logger.warning("Downloading image '%s' failed.", object_name, exc_info=True)
            return False

    with ThreadPoolExecutor(max_workers=_DOWNLOAD_WORKERS) as pool:
        return sum(pool.map(fetch_one, images))


def _sync_project_images() -> None:
    """Reconcile the manifest and upload only the images MinIO is missing.

    Images and the catalogue have different lifecycles: a complete MySQL does not mean the
    MinIO bucket is complete (a new volume, a new manifest, or an interrupted earlier R2
    download). So this function must run before the catalogue check on every bootstrap.
    """
    settings = get_settings()
    archive_url = settings.project_images_archive_url
    base_url = settings.project_images_base_url

    if archive_url:
        try:
            count = _download_archive_to_minio(archive_url)
            logger.info("Loaded project images from the archive: %d new images.", count)
        except Exception:
            logger.error(
                "Loading project images from the archive failed; the catalogue pages will be missing images.",
                exc_info=True,
            )
    elif base_url:
        try:
            count = _download_images_to_minio(base_url)
            logger.info("Uploaded project images to MinIO: %d new images.", count)
        except Exception:
            logger.error(
                "Downloading project images failed; the catalogue pages will be missing images.", exc_info=True
            )
    else:
        logger.warning(
            "Neither PROJECT_IMAGES_BASE_URL nor PROJECT_IMAGES_ARCHIVE_URL is set; skipping the "
            "image download step, so the catalogue will show no images."
        )


def _sync_catalogue_galleries() -> int:
    """Refresh gallery metadata without overwriting the rest of a seeded catalogue."""
    from scripts._gallery import gallery_by_slug

    galleries = gallery_by_slug()
    db = SessionLocal()
    updated = 0
    try:
        for project in db.query(Project).all():
            gallery = galleries.get(project.id)
            if gallery is None:
                continue

            details = dict(project.details or {})
            images = dict(details.get("images") or {})
            if images.get("gallery") == gallery:
                continue

            images["gallery"] = gallery
            details["images"] = images
            project.details = details
            updated += 1

        if updated:
            db.commit()
        return updated
    finally:
        db.close()


def load_demo_data() -> None:
    settings = get_settings()
    if not settings.auto_load_demo_data:
        return

    _sync_project_images()

    try:
        refreshed = _sync_catalogue_galleries()
        if refreshed:
            logger.info("Updated galleries from the manifest for %d projects.", refreshed)
    except Exception:
        logger.warning("Could not sync catalogue galleries from the manifest.", exc_info=True)

    try:
        if _catalogue_is_loaded():
            logger.info("Catalogue already has data; skipping the catalogue load.")
            return
    except Exception:
        logger.warning("Could not check whether the catalogue is loaded.", exc_info=True)

    from scripts.load_apartment_projects import main as load_apartments
    from scripts.load_villa_shop_projects import main as load_villas_and_shops
    from scripts.load_vinhomes_ocean_park import main as load_ocean_park

    for label, loader in (
        ("vinhomes-ocean-park", load_ocean_park),
        ("villas-shops", load_villas_and_shops),
        ("apartments", load_apartments),
    ):
        try:
            loader()
            logger.info("Loaded catalogue '%s'.", label)
        except Exception:
            logger.error(
                "Loading catalogue '%s' failed; the catalogue pages will be missing data.", label, exc_info=True
            )
