import pytest
from app.store.pricing import StorePricingService
from app.store.repository import StoreRepository
from app.store.woocommerce import FixtureStoreGateway

def payload():return {"kinds":["plugin","theme"],"annual_regular":"99","annual_sale":"79","lifetime_regular":"199","lifetime_sale":"149"}
def test_preview_covers_plugin_theme_annual_lifetime(tmp_path):
    gateway=FixtureStoreGateway();result=StorePricingService(gateway,StoreRepository(tmp_path)).preview(payload(),gateway.products());assert {x["period"] for x in result["changes"]}=={"annual","lifetime"};assert {x["status"] for x in result["changes"]}=={"unchanged"}
def test_gate_and_confirmation(tmp_path):
    gateway=FixtureStoreGateway();disabled=StorePricingService(gateway,StoreRepository(tmp_path),False)
    with pytest.raises(PermissionError):disabled.apply(payload(),gateway.products())
    enabled=StorePricingService(gateway,StoreRepository(tmp_path),True)
    with pytest.raises(ValueError):enabled.apply(payload(),gateway.products())
def test_unchanged_does_not_write(tmp_path):
    gateway=FixtureStoreGateway();data=payload();data["confirmation"]="ALTERAR PRECOS";result=StorePricingService(gateway,StoreRepository(tmp_path),True).apply(data,gateway.products());assert result["changed"]==0 and not gateway.writes
def test_individual_failure_does_not_abort_batch(tmp_path):
    gateway=FixtureStoreGateway();original=gateway.update_variations
    def update(pid,rows):
        if pid==101:raise RuntimeError("produto falhou")
        return original(pid,rows)
    gateway.update_variations=update;data=payload();data.update(confirmation="ALTERAR PRECOS",annual_regular="100")
    result=StorePricingService(gateway,StoreRepository(tmp_path),True).apply(data,gateway.products());assert result["errors"] and result["changed"]>0
