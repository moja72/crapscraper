from __future__ import annotations

import hashlib
import time
import zipfile

import pytest

from app.updates.adapters import (
    FilesystemInstaller,
    VersionPersistenceError,
    WooCommerceGateway,
    normalize_version,
)
from app.updates.batch import UpdateBatchService
from app.updates.executor import UpdateExecutor
from app.updates.repository import UpdateRepository
from app.updates.sources import SourceRegistry
from tests.update_fakes import FakeSource, approval


def product(value="1.0", *, product_id=101, meta_id=7, duplicate=False):
    metadata=[{"id":meta_id,"key":"pt_versao","value":value}]
    if duplicate:metadata.append({"id":meta_id+1,"key":"pt_versao","value":value})
    return {"id":product_id,"type":"variable","meta_data":metadata}


class Response:
    def __init__(self, payload, *, status=200, url="https://example.test/wp-json/wc/v3/products/101"):
        self.payload=payload;self.status_code=status;self.url=url;self.history=[]
        self.headers={"Content-Type":"application/json","Cache-Control":"no-store","X-LiteSpeed-Cache":"miss"}
        self.content=b"{}" if payload is not None else b"";self.text=self.content.decode()
    def json(self):return self.payload


def gateway(monkeypatch, responses):
    monkeypatch.setenv("SCRAPER_WP_BASE_URL","https://example.test")
    monkeypatch.setenv("SCRAPER_WC_CONSUMER_KEY","key")
    monkeypatch.setenv("SCRAPER_WC_CONSUMER_SECRET","secret")
    woo=WooCommerceGateway(confirmation_delays=(0,0),sleeper=lambda _delay:None);calls=[]
    def request(method,url,**kwargs):
        calls.append({"method":method,"url":url,"kwargs":kwargs})
        return responses.pop(0)
    woo.session.request=request
    return woo,calls


def test_immediate_write_uses_exact_meta_id_and_confirms(monkeypatch):
    woo,calls=gateway(monkeypatch,[Response(product("1.0")),Response(product("2.0")),Response(product("2.0"))])
    write=woo.set_version(101,"2.0");confirmation=woo.confirm_version(101,"2.0")
    assert write["http_status"]==200 and write["put"]["value"]=="2.0"
    assert confirmation["confirmation_status"]=="confirmed"
    put=next(call for call in calls if call["method"]=="PUT")
    assert put["url"].endswith("/wp-json/wc/v3/products/101")
    assert put["kwargs"]["json"]=={"meta_data":[{"id":7,"key":"pt_versao","value":"2.0"}]}


def test_eventual_consistency_retries_fresh_get_without_rollback(monkeypatch):
    woo,calls=gateway(monkeypatch,[Response(product("1.0")),Response(product("2.0")),Response(product("1.0")),Response(product("2.0"))])
    woo.set_version(101,"2.0");evidence=woo.confirm_version(101,"2.0")
    assert [item["observed_pt_versao"] for item in evidence["gets"]]==["1.0","2.0"]
    get_calls=[call for call in calls if call["method"]=="GET"]
    assert all("_crapscraper_fresh" in call["kwargs"]["params"] for call in get_calls)
    assert get_calls[-1]["kwargs"]["headers"]["Cache-Control"]=="no-cache"


def test_put_and_all_fresh_gets_staying_old_is_real_failure(monkeypatch):
    woo,_calls=gateway(monkeypatch,[Response(product("1.0")),Response(product("1.0")),Response(product("1.0")),Response(product("1.0"))])
    write=woo.set_version(101,"2.0")
    assert write["confirmation_status"]=="put_diverged" and write["put"]["value"]=="1.0"
    with pytest.raises(VersionPersistenceError) as raised:woo.confirm_version(101,"2.0")
    assert [item["observed_pt_versao"] for item in raised.value.evidence["gets"]]==["1.0","1.0"]


def test_duplicate_pt_versao_is_blocked_before_put(monkeypatch):
    woo,calls=gateway(monkeypatch,[Response(product("1.0",duplicate=True))])
    with pytest.raises(VersionPersistenceError) as raised:woo.set_version(101,"2.0")
    assert raised.value.evidence["before"]["count"]==2
    assert [call["method"] for call in calls]==["GET"]


def test_normalized_value_is_equal_but_real_difference_is_not(monkeypatch):
    assert normalize_version(" 2.3.4 ")==normalize_version("2.3.4")
    assert normalize_version("2.3.4")!=normalize_version("2.3.5")
    woo,_calls=gateway(monkeypatch,[Response(product(" 2.3.4 "))])
    assert woo.confirm_version(101,"2.3.4")["confirmation_status"]=="confirmed"
    other,_calls=gateway(monkeypatch,[Response(product("2.3.5")),Response(product("2.3.5"))])
    with pytest.raises(VersionPersistenceError) as raised:other.confirm_version(101,"2.3.4")
    assert "Esperado: 2.3.4" in str(raised.value) and "Encontrado: 2.3.5" in str(raised.value)


class TransactionWoo:
    def __init__(self, *, fail_target=False, stale_once=False, duplicate=False):
        self.value="1.0";self.fail_target=fail_target;self.stale_once=stale_once;self.duplicate=duplicate
        self.set_calls=[];self.confirm_calls=[];self.target_writes=0
    def _product(self):return product(self.value,duplicate=self.duplicate)
    def get_product_fresh(self,_product_id):return self._product()
    get_product=get_product_fresh
    def prepare_job(self,job):job["target_filename"]="produto.zip"
    def set_version(self,product_id,version):
        requested=normalize_version(version);previous=self.value;self.set_calls.append(requested)
        if requested=="2.0":
            self.target_writes+=1
            if not self.fail_target:self.value=requested
        else:self.value=requested
        return {"method":"PUT","endpoint":f"/products/{product_id}","product_id":product_id,"previous_pt_versao":previous,"requested_pt_versao":requested,"payload":{"meta_data":[{"id":7,"key":"pt_versao","value":requested}]},"http_status":200,"put":{"product_id":product_id,"status":"single","count":1,"entries":[{"id":7,"key":"pt_versao","value":self.value}],"meta_id":7,"value":self.value},"gets":[],"confirmation_status":"put_confirmed" if self.value==requested else "put_diverged"}
    def confirm_version(self,product_id,version):
        expected=normalize_version(version);self.confirm_calls.append(expected)
        if expected=="2.0" and self.fail_target:
            gets=[{"number":1,"product_id":product_id,"observed_pt_versao":"1.0","status":"single","count":1,"meta_id":7,"entries":[],"cache_busted":True},{"number":2,"product_id":product_id,"observed_pt_versao":"1.0","status":"single","count":1,"meta_id":7,"entries":[],"cache_busted":True}]
            raise VersionPersistenceError("Validação final do pt_versao divergiu. Esperado: 2.0. Encontrado: 1.0.",{"method":"GET","endpoint":f"/products/{product_id}","product_id":product_id,"requested_pt_versao":expected,"observed_pt_versao":"1.0","gets":gets,"confirmation_status":"diverged"})
        gets=[]
        if expected=="2.0" and self.stale_once:
            gets.append({"number":1,"product_id":product_id,"observed_pt_versao":"1.0","status":"single","count":1,"meta_id":7,"entries":[],"cache_busted":True});self.stale_once=False
        gets.append({"number":len(gets)+1,"product_id":product_id,"observed_pt_versao":self.value,"status":"single","count":1,"meta_id":7,"entries":[],"cache_busted":True})
        return {"method":"GET","endpoint":f"/products/{product_id}","product_id":product_id,"requested_pt_versao":expected,"expected_pt_versao":expected,"observed_pt_versao":self.value,"gets":gets,"confirmation_status":"confirmed"}


def build_transaction(tmp_path,woo):
    downloads=tmp_path/"downloads";downloads.mkdir(exist_ok=True);target=downloads/"produto.zip"
    if not target.exists():
        with zipfile.ZipFile(target,"w") as archive:archive.writestr("plugin/file.php","old")
    original=target.read_bytes();repo=UpdateRepository(tmp_path/"data");repo.materialize([approval()]);job=repo.list()["items"][0]
    executor=UpdateExecutor(repo,sources=SourceRegistry([FakeSource()]),woo=woo,installer=FilesystemInstaller(downloads),staging_root=tmp_path/"stage",enabled=True,allowed_product_ids=frozenset())
    return repo,job,executor,target,original


def test_executor_eventual_read_succeeds_without_rollback(tmp_path):
    woo=TransactionWoo(stale_once=True);repo,job,executor,target,original=build_transaction(tmp_path,woo)
    result=executor.execute(job["job_id"])
    assert result["ok"] and woo.value=="2.0" and target.read_bytes()!=original
    assert woo.set_calls==["2.0"] and repo.get(job["job_id"])["stage"]=="completed"


def test_real_non_persistence_rolls_back_zip_and_version_with_evidence(tmp_path):
    woo=TransactionWoo(fail_target=True);repo,job,executor,target,original=build_transaction(tmp_path,woo)
    original_sha=hashlib.sha256(original).hexdigest();result=executor.execute(job["job_id"]);saved=repo.get(job["job_id"])
    assert not result["ok"] and saved["stage"]=="rolled_back"
    assert hashlib.sha256(target.read_bytes()).hexdigest()==original_sha and woo.value=="1.0"
    assert woo.set_calls==["2.0","1.0"]
    assert result["error"]["code"]=="woocommerce_version_diverged"
    assert result["error"]["details"]["rollback"]["zip"]["confirmed"] is True
    assert "Esperado: 2.0" in result["error"]["message"] and "Encontrado: 1.0" in result["error"]["message"]


def test_retry_creates_second_successful_attempt_and_keeps_first(tmp_path):
    woo=TransactionWoo(fail_target=True);repo,job,executor,_target,_original=build_transaction(tmp_path,woo)
    assert not executor.execute(job["job_id"])["ok"]
    woo.fail_target=False
    assert executor.execute(job["job_id"])["ok"]
    history=repo.history(job["job_id"])
    assert [(item["attempt_number"],item["result"]) for item in history]==[(2,"success"),(1,"error")]
    assert repo.get(job["job_id"])["stage"]=="completed" and woo.target_writes==2


def test_batch_keeps_running_after_middle_failure():
    class Executor:
        def __init__(self):self.calls=[]
        def execute(self,job_id):
            self.calls.append(job_id);return {"ok":job_id!="B","job_id":job_id}
    executor=Executor();batch=UpdateBatchService(executor);batch.start(["A","B","C"])
    for _ in range(100):
        if not batch.state()["running"]:break
        time.sleep(.01)
    assert executor.calls==["A","B","C"]
    assert (batch.state()["success"],batch.state()["errors"],batch.state()["processed"])==(2,1,3)
