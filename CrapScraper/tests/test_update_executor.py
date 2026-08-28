from app.updates.executor import UpdateExecutor, version_key
from app.updates.adapters import FilesystemInstaller, WooCommerceRequestError
from app.updates.repository import UpdateRepository
from app.updates.sources import SourceRegistry,SourceFailure
from app.updates.models import UpdateError
from tests.update_fakes import approval,FakeInstaller,FakeSource,FakeWoo

def build(tmp_path,*,source=None,woo=None,installer=None):
    repo=UpdateRepository(tmp_path);repo.materialize([approval()]);job=repo.list()["items"][0]
    source=source or FakeSource();executor=UpdateExecutor(repo,sources=SourceRegistry([source]),woo=woo or FakeWoo(),installer=installer or FakeInstaller(),staging_root=tmp_path/"stage",enabled=True,allowed_product_ids=frozenset())
    return repo,job,executor,source

def test_source_is_immutable_and_zero_ultrapack_calls(tmp_path):
    plugin=FakeSource("plugintheme");ultra=FakeSource("ultrapackv2");repo=UpdateRepository(tmp_path);repo.materialize([approval()]);job=repo.list()["items"][0]
    ex=UpdateExecutor(repo,sources=SourceRegistry([plugin,ultra]),woo=FakeWoo(),installer=FakeInstaller(),staging_root=tmp_path/"stage",enabled=True,allowed_product_ids=frozenset())
    assert ex.execute(job["job_id"])["ok"] and plugin.calls==["auth","version","download"] and ultra.calls==[]

def test_already_current_skips_source_and_install(tmp_path):
    source=FakeSource();installer=FakeInstaller();repo,job,ex,_=build(tmp_path,source=source,woo=FakeWoo("2.0"),installer=installer)
    result=ex.execute(job["job_id"])
    assert result["already_current"] and source.calls==[] and installer.installs==0

def test_newer_destination_skips_stale_approval_without_downgrade(tmp_path):
    source=FakeSource();installer=FakeInstaller();repo,job,ex,_=build(tmp_path,source=source,woo=FakeWoo("9.6.4"),installer=installer)
    with repo.connection() as db: db.execute("UPDATE update_jobs SET source_version='9.6.3' WHERE job_id=?",(job["job_id"],))
    result=ex.execute(job["job_id"])
    assert result["already_current"] and repo.get(job["job_id"])["stage"]=="already_current" and source.calls==[] and installer.installs==0

def test_version_key_normalizes_trailing_zero_segments():
    assert version_key("1.0")==version_key("1.0.0")
    assert version_key("1.9")<version_key("1.10")
    assert version_key("1.2.0.4")>version_key("1.2.0.3")

def test_invalid_zip_stops_before_install(tmp_path):
    failure=SourceFailure(UpdateError(message="ZIP inválido",code="source_download_failed",stage="downloading",source="PluginTheme"));installer=FakeInstaller()
    repo,job,ex,_=build(tmp_path,source=FakeSource(fail=failure),installer=installer)
    result=ex.execute(job["job_id"])
    assert not result["ok"] and installer.installs==0 and repo.get(job["job_id"])["state"]=="error"

def test_non_zip_artifact_stops_before_woocommerce_write(tmp_path):
    import hashlib
    from app.updates.sources import DownloadArtifact
    class BadSource(FakeSource):
        def download(self, job, target):
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(b"not-a-zip")
            return DownloadArtifact(target, hashlib.sha256(target.read_bytes()).hexdigest(), target.stat().st_size, job["source_url"], job["source_url"], "application/octet-stream")
    woo=FakeWoo(); repo,job,ex,_=build(tmp_path,source=BadSource(),woo=woo)
    result=ex.execute(job["job_id"])
    assert not result["ok"] and woo.set_calls==[] and repo.get(job["job_id"])["stage"]=="downloading"

def test_install_failure_rolls_back_and_retry_preserves_history(tmp_path):
    installer=FakeInstaller(fail=True);woo=FakeWoo();repo,job,ex,_=build(tmp_path,installer=installer,woo=woo)
    assert not ex.execute(job["job_id"])["ok"] and installer.rollbacks==1 and woo.set_calls==[]
    installer.fail=False
    assert ex.execute(job["job_id"])["ok"]
    history=repo.history(job["job_id"])
    assert len(history)==2 and history[0]["result"]=="success" and history[1]["result"]=="error"

def test_running_job_cannot_start_duplicate_attempt(tmp_path):
    repo,job,ex,_=build(tmp_path)
    first=repo.begin_attempt(job["job_id"])
    try:
        ex.execute(job["job_id"])
    except ValueError as error:
        assert "já está em execução" in str(error)
    else:
        raise AssertionError("execução duplicada deveria ser rejeitada")
    assert repo.get(job["job_id"])["attempts"]==1

def test_woocommerce_403_is_terminal_error_with_rest_diagnostics(tmp_path):
    class ForbiddenWoo(FakeWoo):
        def get_product(self,pid):
            raise WooCommerceRequestError(method="GET",endpoint=f"/products/{pid}",status=403,code="woocommerce_rest_cannot_view",response_message="not allowed",final_url=f"https://example.test/products/{pid}")
    repo,job,ex,_=build(tmp_path,woo=ForbiddenWoo())
    result=ex.execute(job["job_id"]); item=repo.get(job["job_id"])
    assert not result["ok"] and item["state"]=="error" and item["stage"]=="validating"
    assert item["error"]["code"]=="woocommerce_http_error" and item["error"]["http_status"]==403
    assert "woocommerce_rest_cannot_view" in item["error"]["technical_message"]

def test_html_403_has_friendly_message_and_proxy_diagnosis(tmp_path):
    class HtmlForbiddenWoo(FakeWoo):
        def get_product(self,pid):
            raise WooCommerceRequestError(method="GET",endpoint=f"/products/{pid}",status=403,response_message="Resposta não-JSON (HTML ou proxy)",content_type="text/html",server="LiteSpeed",final_url="https://example.test/products/{pid}")
    repo,job,ex,_=build(tmp_path,woo=HtmlForbiddenWoo())
    result=ex.execute(job["job_id"]); error=result["error"]
    assert "Resposta não-JSON" in error["message"] and "servidor/proxy" in error["diagnosis"]
    assert "<html" not in error["message"].lower() and "text/html" in error["technical_message"]

def test_real_filesystem_installer_changes_zip_before_woocommerce_write(tmp_path):
    import hashlib, zipfile
    root=tmp_path/"downloads";root.mkdir();target=root/"produto.zip"
    with zipfile.ZipFile(target,"w") as archive:archive.writestr("plugin/file.php","old")
    old_sha=hashlib.sha256(target.read_bytes()).hexdigest()
    class Woo(FakeWoo):
        def prepare_job(self,job):job["target_filename"]="produto.zip"
    woo=Woo();repo,job,executor,_=build(tmp_path,woo=woo,installer=FilesystemInstaller(root))
    result=executor.execute(job["job_id"]);new_sha=hashlib.sha256(target.read_bytes()).hexdigest()
    assert result["ok"] and new_sha!=old_sha and woo.set_calls==["2.0"]
    with zipfile.ZipFile(target) as archive:assert archive.read("plugin/file.php")==b"ok"
    history=repo.history(job["job_id"])[0]
    stages=[item["stage"] for item in history["stages"]]
    assert stages.index("installing") < stages.index("updating_woocommerce") < stages.index("completed")

def test_storage_preflight_failure_prevents_download_and_put(tmp_path):
    source=FakeSource();woo=FakeWoo();repo,job,executor,_=build(tmp_path,source=source,woo=woo,installer=FilesystemInstaller())
    result=executor.execute(job["job_id"])
    assert not result["ok"] and source.calls==[] and woo.set_calls==[]
    assert "Armazenamento de destino" in result["error"]["message"]

def test_filesystem_installer_backup_and_rollback_restore_original_bytes(tmp_path):
    import zipfile
    root=tmp_path/"downloads";root.mkdir();target=root/"produto.zip";artifact=tmp_path/"novo.zip"
    with zipfile.ZipFile(target,"w") as archive:archive.writestr("plugin/file.php","old")
    with zipfile.ZipFile(artifact,"w") as archive:archive.writestr("plugin/file.php","new")
    original=target.read_bytes();installer=FilesystemInstaller(root);job={"target_filename":"produto.zip"}
    backup=installer.backup(job,tmp_path/"attempt");installer.install(job,artifact,backup)
    assert target.read_bytes()!=original
    installer.rollback(job,backup)
    assert target.read_bytes()==original
