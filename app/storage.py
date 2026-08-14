"""Supabase Storage — persistent public URLs for uploaded property media.

Replaces the old local-disk `data/media/` approach, which was lost every
time the free-tier host restarted. Uses the service-role key (bypasses Row
Level Security) since only our own trusted backend uploads here — never
exposed to a browser — so the bucket needs no manual policy configuration
beyond creating it as Public in the Supabase dashboard.
"""
import logging
import time
import uuid

from supabase import Client, create_client

from app import config

log = logging.getLogger(__name__)

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        config.require("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
    return _client


def upload_media(account_slug: str, filename: str, content: bytes, content_type: str) -> str:
    """Upload one property photo/video, namespaced by account. Returns its public URL."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    path = f"{account_slug}/{int(time.time())}_{uuid.uuid4().hex[:8]}.{ext}"
    client = _get_client()
    client.storage.from_(config.STORAGE_BUCKET).upload(
        path, content, {"content-type": content_type}
    )
    log.info("Uploaded media %s (%d bytes)", path, len(content))
    return client.storage.from_(config.STORAGE_BUCKET).get_public_url(path)
