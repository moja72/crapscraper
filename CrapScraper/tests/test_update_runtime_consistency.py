from __future__ import annotations

import io
import sqlite3
import zipfile
from pathlib import Path

from app.update_runtime_consistency import (
    _completed_overrides,
    _manual_attempt_ids,
    _patch_download_transport,
    _patch_repository_consistency,
)
from app.updates.repository import UpdateRepository
from app.updates.sources import HttpDownloadTransport


def zip_bytes() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("theme/style.css", "ok")
    return stream.getvalue()


class BinaryResponse:
    def __init__(self, body: bytes):
        self.status_code = 200
        self.headers = {"Content-Type": "application/octet-stream"}
        self.url = "https://downloads.example.test/aoki"
        self.content = body

    def iter_content(self, _size):
        yield self.content


class BinarySession:
    def __init__(self, body: bytes):
        self.response = BinaryResponse(body)

    def get(self, *_args, **_kwargs):
        return self.response


def approval(version="9.6.5"):
    return {
        "comparison_item_id": "edubin-95533",
        "woo_product_id": 95533,
        "site_name": "Edubin - Education WordPress Theme",
        "site_version": "9.6.4",
        "source_version": version,
        "source_name": "UltraPackV2",
        "source_product_url": "https://www.ultrapackv2.com/item/edubin/",
    }


def test_octet_stream_with_real_zip_is_accepted(tmp_path):
    _patch_download_transport()
    transport = HttpDownloadTransport(session=BinarySession(zip_bytes()))
    artifact = transport.download(
        url="https://downloads.example.test/aoki",
        target=tmp_path / "artifact.zip",
        source="UltraPackV2",
    )
    assert artifact.size > 0
    assert zipfile.is_zipfile(artifact.path)
    assert artifact.content_type == "application/octet-stream"


def test_stale_approval_cannot_regress_completed_current_version(tmp_path):
    _patch_repository_consistency()
    repository = UpdateRepository(tmp_path)
    repository.materialize([approval()])
    job = repository.list()["items"][0]
    with repository.connection() as db:
        db.execute(
            "UPDATE update_jobs SET public_state='success',stage='completed',"
            "current_version='9.6.4',source_version='9.6.5',attempts=1 WHERE job_id=?",
            (job["job_id"],),
        )

    repository.materialize([approval()])
    repaired = repository.get(job["job_id"])
    assert repaired["state"] == "success"
    assert repaired["current_version"] == "9.6.5"


def test_completed_overrides_use_confirmed_target(tmp_path):
    database = tmp_path / "consolidated_updates.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute(
            "CREATE TABLE update_jobs(woo_product_id INTEGER,current_version TEXT,"
            "source_version TEXT,public_state TEXT,stage TEXT)"
        )
        db.execute(
            "INSERT INTO update_jobs VALUES(95533,'9.6.4','9.6.5','success','completed')"
        )
    assert _completed_overrides(tmp_path / "catalog.csv") == {95533: "9.6.5"}


def test_manual_attempt_is_detected_from_mu_plugin_monitor_database(tmp_path):
    update_db = tmp_path / "consolidated_updates.sqlite3"
    update_db.touch()
    store_db = tmp_path / "consolidated_store.sqlite3"
    with sqlite3.connect(store_db) as db:
        db.execute(
            "CREATE TABLE store_monitor_requests(attempt_id TEXT,state TEXT)"
        )
        db.execute("INSERT INTO store_monitor_requests VALUES('attempt-manual','completed')")
        db.execute("INSERT INTO store_monitor_requests VALUES('attempt-panel','error')")
    assert _manual_attempt_ids(update_db) == {"attempt-manual"}
