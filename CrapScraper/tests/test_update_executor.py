from app.updates.executor import UpdateExecutor
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

def test_invalid_zip_stops_before_install(tmp_path):
    failure=SourceFailure(UpdateError(message="ZIP inválido",code="source_download_failed",stage="downloading",source="PluginTheme"));installer=FakeInstaller()
    repo,job,ex,_=build(tmp_path,source=FakeSource(fail=failure),installer=installer)
    result=ex.execute(job["job_id"])
    assert not result["ok"] and installer.installs==0 and repo.get(job["job_id"])["state"]=="error"

def test_install_failure_rolls_back_and_retry_preserves_history(tmp_path):
    installer=FakeInstaller(fail=True);repo,job,ex,_=build(tmp_path,installer=installer)
    assert not ex.execute(job["job_id"])["ok"] and installer.rollbacks==1
    installer.fail=False
    assert ex.execute(job["job_id"])["ok"]
    history=repo.history(job["job_id"])
    assert len(history)==2 and history[0]["result"]=="success" and history[1]["result"]=="error"
