"""Cloud Storage helper — upload/download report files to the reports bucket.

Auth: uses Application Default Credentials. In Cloud Run, the job's service
account authenticates automatically (no key needed). Locally, it uses whatever
`gcloud auth application-default login` set up.

The bucket name comes from the REPORTS_BUCKET env var, falling back to the
known bucket. This keeps it configurable without hardcoding.
"""

import os
import logging
from google.cloud import storage

log = logging.getLogger(__name__)

BUCKET_NAME = os.getenv("REPORTS_BUCKET", "range-music-label-reports")


def _bucket():
    client = storage.Client()
    return client.bucket(BUCKET_NAME)


def upload_report(local_path, blob_name: str):
    """Upload a local file to the bucket under blob_name."""
    blob = _bucket().blob(blob_name)
    blob.upload_from_filename(str(local_path))
    log.info("Uploaded %s to gs://%s/%s", local_path, BUCKET_NAME, blob_name)


def download_report(blob_name: str, local_path):
    """Download blob_name from the bucket to local_path. Returns True on success,
    False if the blob doesn't exist."""
    from google.api_core import exceptions
    blob = _bucket().blob(blob_name)
    try:
        blob.download_to_filename(str(local_path))
        log.info("Downloaded gs://%s/%s to %s", BUCKET_NAME, blob_name, local_path)
        return True
    except exceptions.NotFound:
        log.warning("Report not found in bucket: gs://%s/%s", BUCKET_NAME, blob_name)
        return False