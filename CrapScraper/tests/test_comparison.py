from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.comparison import decisions
from app.comparison.models import DECISIONS, RELATIONSHIPS, STATUSES
from app.comparison.service import ComparisonService


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


@pytest.fixture
def comparison(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ComparisonService:
    write_csv(tmp_path/"slots/default/ultrapackv2/plugin/account/catalog.csv",[
        {"nome_produto":"Alpha Plugin","versao_produto":"2.0.0","pagina_oficial":"https://vendor.test/alpha","categoria_nome":"Plugins","link_produto":"https://source.test/alpha"},
        {"nome_produto":"Novo Plugin","versao_produto":"1.0","pagina_oficial":"https://vendor.test/new","categoria_nome":"Plugins","link_produto":"https://source.test/new"},
    ])
    write_csv(tmp_path/"imports/plugintema-products.csv",[
        {"ID":"10","Nome":"Alpha Plugin","Tipo":"variable","Metadado: pt_versao":"1.0.0","Metadado: site_oficial":"https://vendor.test/alpha","URL":"https://shop.test/alpha","Categorias":"Plugins"},
        {"ID":"11","Nome":"Só no Site","Tipo":"variable","Metadado: pt_versao":"1.0","Metadado: site_oficial":"https://vendor.test/site","URL":"https://shop.test/site","Categorias":"Plugins"},
    ])
    monkeypatch.setattr(decisions.settings,"COMPARISON_DECISIONS_DB_PATH",tmp_path/"comparison_decisions.sqlite3")
    return ComparisonService(tmp_path)


def test_real_matching_statuses_and_pagination(comparison: ComparisonService):
    catalogs=comparison.catalogs();result=comparison.run({"source_id":catalogs["source_id"],"site_id":catalogs["site_id"],"page_size":2,"force":True})
    statuses={row["status"] for row in result["rows"]};assert "update_available" in statuses
    assert result["pagination"]["total_rows"]==3 and result["pagination"]["total_pages"]==2
    assert set(STATUSES)>={"updated","new_source","site_only"}


def test_filters_search_and_candidate_lookup(comparison: ComparisonService):
    comparison.catalogs();value=comparison.run({"query":"Alpha","status":"update_available","page_size":30,"force":True})
    assert len(value["rows"])==1 and value["rows"][0]["match_method"] in {"official_url","normalized_name"}
    found=comparison.candidates({"role":"source","query":"Novo"});assert found["items"][0]["name"]=="Novo Plugin"


def test_decision_sqlite_persistence_cache_revision_and_approvals(comparison: ComparisonService):
    comparison.catalogs();row=comparison.run({"page_size":10,"force":True})["rows"][0]
    saved=comparison.save_decision({"comparison_item_id":row["comparison_item_id"],"decision":"approve_update","snapshot":row})
    assert saved["revision"]==1 and decisions.get_decision(row["comparison_item_id"])["decision"]=="approve_update"
    assert len(decisions.get_decision_history(row["comparison_item_id"]))==1
    assert comparison.approvals()["updates"][0]["comparison_item_id"]==row["comparison_item_id"]
    assert set(DECISIONS)>={"approve_update","approve_new_product"}


def test_manual_relationship_confirm_and_reject(comparison: ComparisonService):
    comparison.catalogs();row=comparison.run({"page_size":10,"force":True})["rows"][0]
    confirmed=comparison.save_relationship({"site_product_key":row["site_product_key"],"source_product_key":row["source_product_key"],"relationship_state":"manual_confirmed","site_id":row["site_id"],"site_name":row["site_name"],"source_name":row["source_name"]})
    assert confirmed["item"]["relationship_state"]=="manual_confirmed"
    rejected=comparison.save_relationship({"site_product_key":row["site_product_key"],"source_product_key":row["source_product_key"],"relationship_state":"manual_rejected"})
    assert rejected["item"]["relationship_state"]=="manual_rejected" and "pending_review" in RELATIONSHIPS


def test_advanced_filters_bulk_reset_history_and_cached_operation(comparison: ComparisonService):
    comparison.catalogs();first=comparison.run({"candidate_count_min":1,"score_min":50,"page_size":1,"force":True})
    assert first["filters"]["candidate_count_min"]==1 and first["filters"]["score_min"]==50
    cached=comparison.run({"candidate_count_min":0,"score_max":100,"page_size":1})
    assert cached["operation"]["cached"] is True and cached["operation"]["duration_seconds"]>=0 and cached["operation"]["log"]
    selected=comparison.selection({"candidate_count_min":0,"score_max":100})
    assert selected["total"]==3
    rows=selected["items"][:2];bulk=comparison.save_decisions_bulk({"items":rows,"decision":"review_later"})
    assert bulk["total_saved"]==2 and all(decisions.get_decision(row["comparison_item_id"])["decision"]=="review_later" for row in rows)
    reset=comparison.reset_decision({"comparison_item_id":rows[0]["comparison_item_id"]})
    assert reset["item"]["decision"]=="pending"
    history=comparison.decision_history({"comparison_item_id":rows[0]["comparison_item_id"]})
    assert len(history["items"])==2 and history["items"][0]["operator"]=="consolidated-ui"


def test_filtered_selection_reuses_local_comparison_cache(monkeypatch: pytest.MonkeyPatch, comparison: ComparisonService):
    comparison.catalogs();calls=0;original=__import__("app.comparison.service",fromlist=["matching"]).matching.build_comparison_payload
    def counted(**kwargs):
        nonlocal calls;calls+=1;return original(**kwargs)
    monkeypatch.setattr("app.comparison.service.matching.build_comparison_payload",counted)
    result=comparison.selection({"page_size":1})
    assert result["total"]==3 and calls==1
