from app.updates.executor import UpdateExecutor
from app.updates.repository import UpdateRepository
from app.updates.service import UpdateService
from tests.update_fakes import approval


def materialize_named(repo, identifier, name, woo):
    item = approval(identifier, woo=woo)
    item["site_name"] = name
    repo.materialize([item])
    return repo._job_id(identifier)


def test_update_sorting_happens_before_pagination(tmp_path):
    repo = UpdateRepository(tmp_path)
    alfa = materialize_named(repo, "alpha", "Alfa", 101)
    zulu = materialize_named(repo, "zulu", "Zulu", 102)
    bravo = materialize_named(repo, "bravo", "Bravo", 103)
    with repo.connection() as db:
        db.execute("UPDATE update_jobs SET created_at='2026-01-01T00:00:00+00:00' WHERE job_id=?", (alfa,))
        db.execute("UPDATE update_jobs SET created_at='2026-02-01T00:00:00+00:00' WHERE job_id=?", (zulu,))
        db.execute("UPDATE update_jobs SET created_at='2026-03-01T00:00:00+00:00' WHERE job_id=?", (bravo,))

    assert [item["product_name"] for item in repo.list(sort_by="name", sort_order="asc", page_size=2)["items"]] == ["Alfa", "Bravo"]
    assert [item["product_name"] for item in repo.list(sort_by="name", sort_order="desc", page_size=2)["items"]] == ["Zulu", "Bravo"]
    assert [item["product_name"] for item in repo.list(sort_by="date", sort_order="desc", page_size=2)["items"]] == ["Bravo", "Zulu"]
    assert [item["product_name"] for item in repo.list(sort_by="date", sort_order="asc", page_size=2)["items"]] == ["Alfa", "Zulu"]


def test_update_filter_search_sort_and_filtered_selection_combine(tmp_path, monkeypatch):
    repo = UpdateRepository(tmp_path)
    materialize_named(repo, "elementor-z", "Elementor Z", 201)
    materialize_named(repo, "elementor-a", "Elementor A", 202)
    materialize_named(repo, "seo", "SEO", 203)
    monkeypatch.setattr("app.updates.service.decisions.list_approved_updates", lambda: [])
    service = UpdateService(tmp_path, repository=repo, executor=UpdateExecutor(repo, enabled=True, allowed_product_ids=frozenset()))

    result = service.selection({"query": "Elementor", "group": "prepared", "sort_by": "name", "sort_order": "asc"})

    assert result["total"] == 2
    assert [item["product_name"] for item in result["items"]] == ["Elementor A", "Elementor Z"]


def test_product_progress_uses_canonical_stage_and_logs(tmp_path, monkeypatch):
    repo = UpdateRepository(tmp_path)
    job_id = materialize_named(repo, "progress", "Produto Progress", 301)
    attempt = repo.begin_attempt(job_id)
    repo.progress(job_id, attempt["attempt_id"], "downloading", "Baixando versão confirmada.")
    monkeypatch.setattr("app.updates.service.decisions.list_approved_updates", lambda: [])
    service = UpdateService(tmp_path, repository=repo, executor=UpdateExecutor(repo, enabled=True, allowed_product_ids=frozenset()))

    running = service.list({"query": "301"})["items"][0]["progress"]
    assert running["active"] is True
    assert running["stage"] == "downloading"
    assert running["label"] == "Baixando arquivo"
    assert running["logs"] == ["Baixando versão confirmada."]

    repo.finish(job_id, attempt["attempt_id"], success=True, stage="completed", sha256="abc")
    completed = service.job(job_id)["item"]["progress"]
    assert completed["complete"] is True and completed["step"] == completed["total"]


class ReconcileWoo:
    def __init__(self, version="2.0"):
        self.version = version

    def get_product_fresh(self, product_id):
        return {"id": product_id, "meta_data": [{"id": 9, "key": "pt_versao", "value": self.version}]}

    def prepare_job(self, job):
        job["target_filename"] = "produto.zip"


class ReconcileInstaller:
    def __init__(self, valid=True):
        self.valid = valid
        self.calls = []

    def validate(self, job, sha256):
        self.calls.append((job.get("target_filename"), sha256))
        return self.valid


def failed_service(tmp_path, monkeypatch, *, woo_version="2.0", zip_valid=True):
    repo = UpdateRepository(tmp_path)
    item = approval("reconcile", woo=401)
    item["source_version"] = "2.0"
    repo.materialize([item])
    job_id = repo._job_id("reconcile")
    attempt = repo.begin_attempt(job_id)
    repo.progress(job_id, attempt["attempt_id"], "installing", "Instalação iniciada.")
    repo.finish(job_id, attempt["attempt_id"], success=False, stage="validating", error={"message": "falha antiga"}, sha256="new-sha")
    monkeypatch.setattr("app.updates.service.decisions.list_approved_updates", lambda: [])
    installer = ReconcileInstaller(zip_valid)
    executor = UpdateExecutor(repo, woo=ReconcileWoo(woo_version), installer=installer, enabled=True, allowed_product_ids=frozenset())
    return repo, job_id, installer, UpdateService(tmp_path, repository=repo, executor=executor)


def test_error_job_reconciles_only_when_version_and_zip_match(tmp_path, monkeypatch):
    repo, job_id, installer, service = failed_service(tmp_path, monkeypatch)

    first = service.reconcile_job(job_id)
    second = service.reconcile_job(job_id)

    assert first["reconciled"] is True
    assert second["reconciled"] is False and second["reason"] == "already_success"
    assert repo.get(job_id)["state"] == "success" and repo.get(job_id)["stage"] == "completed"
    assert repo.history(job_id)[0]["result"] == "error"
    assert installer.calls == [("produto.zip", "new-sha")]
    assert any("Estado reconciliado" in line for line in repo.get(job_id)["logs"])


def test_error_job_is_not_hidden_when_version_or_zip_diverges(tmp_path, monkeypatch):
    repo, job_id, _installer, service = failed_service(tmp_path, monkeypatch, woo_version="1.0")
    assert service.reconcile_job(job_id)["reason"] == "version_mismatch"
    assert repo.get(job_id)["state"] == "error"

    other = tmp_path / "zip"
    other.mkdir()
    repo2, job_id2, _installer2, service2 = failed_service(other, monkeypatch, zip_valid=False)
    assert service2.reconcile_job(job_id2)["reason"] == "artifact_hash_mismatch"
    assert repo2.get(job_id2)["state"] == "error"
