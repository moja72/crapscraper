from app.additions.executor import AdditionExecutor
from app.additions.repository import AdditionRepository
from app.updates.sources import SourceFailure
from app.updates.models import UpdateError
from tests.addition_fakes import approval,Content,FakeSource,Images,Publisher,Research,Sources,Store

def build(tmp_path,source=None,store=None,content=None,images=None,publisher=None,approval_row=None):
    repo=AdditionRepository(tmp_path);repo.materialize([approval_row or approval()]);job=repo.list()["items"][0];source=source or FakeSource();content=content or Content();images=images or Images(tmp_path/"images");store=store or Store();publisher=publisher or Publisher();executor=AdditionExecutor(repo,sources=Sources(source),research=Research(),content=content,images=images,store=store,publisher=publisher,staging_root=tmp_path/"staging",execution_enabled=True,allowed_item_ids=frozenset())
    return repo,job,executor,source,content,images,store,publisher

def test_plugintheme_is_immutable_and_ultrapack_zero_calls(tmp_path):
    plugin=FakeSource("plugintheme");ultra=FakeSource("ultrapackv2");repo=AdditionRepository(tmp_path);repo.materialize([approval()]);job=repo.list()["items"][0]
    executor=AdditionExecutor(repo,sources=Sources(plugin,ultra),research=Research(),content=Content(),images=Images(tmp_path/"images"),store=Store(),publisher=Publisher(),staging_root=tmp_path/"stage",execution_enabled=True,allowed_item_ids=frozenset())
    assert executor.execute(job["job_id"])["ok"] and plugin.calls==["auth","version","download"] and ultra.calls==[]
def test_ultrapack_is_immutable_and_plugin_zero_calls(tmp_path):
    plugin=FakeSource("plugintheme");ultra=FakeSource("ultrapackv2");row=approval(source="UltraPackV2");repo=AdditionRepository(tmp_path);repo.materialize([row]);job=repo.list()["items"][0]
    executor=AdditionExecutor(repo,sources=Sources(plugin,ultra),research=Research(),content=Content(),images=Images(tmp_path/"images"),store=Store(),publisher=Publisher(),staging_root=tmp_path/"stage",execution_enabled=True,allowed_item_ids=frozenset())
    assert executor.execute(job["job_id"])["ok"] and ultra.calls==["auth","version","download"] and plugin.calls==[]
def test_invalid_zip_stops_before_expensive_stages(tmp_path):
    failure=SourceFailure(UpdateError(message="ZIP inválido",code="source_download_failed",source="PluginTheme"));content=Content();images=Images(tmp_path/"images");store=Store();repo,job,executor,*_=build(tmp_path,source=FakeSource(fail=failure),content=content,images=images,store=store)
    result=executor.execute(job["job_id"]);assert not result["ok"] and content.calls==images.calls==store.create_calls==0
def test_retry_reuses_zip_content_image_and_history(tmp_path):
    store=Store(fail_validate=True);repo,job,executor,source,content,images,store,publisher=build(tmp_path,store=store)
    assert not executor.execute(job["job_id"])["ok"];store.fail_validate=False;assert executor.execute(job["job_id"])["ok"]
    assert source.calls.count("download")==1 and content.calls==1 and images.calls==1 and publisher.calls==1 and store.create_calls==1
    history=repo.history(job["job_id"]);assert len(history)==2 and history[0]["result"]=="success" and history[1]["result"]=="error" and repo.get(job["job_id"])["error"] is None
def test_lost_create_response_reconciles_without_duplicate(tmp_path):
    store=Store(lose_response=True);repo,job,executor,*_=build(tmp_path,store=store)
    assert not executor.execute(job["job_id"])["ok"];assert executor.execute(job["job_id"])["ok"] and store.create_calls==1 and repo.get(job["job_id"])["woo_product_id"]==501
import pytest

@pytest.fixture(autouse=True)
def fake_creative_mode(monkeypatch):
    # These tests inject content/image services, not the browser provenance store.
    monkeypatch.setenv("SCRAPER_CHATGPT_AUTOMATION_MODE", "api")
