from __future__ import annotations

from app.update_retry_live_objective import _refresh_retry_objective


class Repository:
    def __init__(self):
        self.refreshed = None

    def get(self, job_id):
        return {
            "job_id": job_id,
            "state": "error",
            "woo_product_id": 42,
            "source_kind": "ultrapackv2",
            "source_version": "1.0",
        }

    def refresh_objective(self, job_id, *, current_version, source_version):
        self.refreshed = (job_id, current_version, source_version)
        return {"job_id": job_id, "current_version": current_version, "source_version": source_version}


class Woo:
    def get_product_fresh(self, product_id):
        assert product_id == 42
        return {"id": 42, "meta_data": [{"key": "pt_versao", "value": "1.0"}]}


class Source:
    def validate_access(self, job):
        return {"version": "1.2"}


class Sources:
    def get(self, kind):
        assert kind == "ultrapackv2"
        return Source()


class Executor:
    woo = Woo()
    sources = Sources()


class Service:
    def __init__(self):
        self.repository = Repository()
        self.executor = Executor()


def test_retry_refreshes_stale_approved_version_from_same_live_source():
    service = Service()
    result = _refresh_retry_objective(service, "job-1")
    assert result["current_version"] == "1.0"
    assert result["source_version"] == "1.2"
    assert service.repository.refreshed == ("job-1", "1.0", "1.2")
