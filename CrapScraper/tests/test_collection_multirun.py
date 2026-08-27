from unittest.mock import patch

import pytest

from app.collection.legacy_core.app import AccountInUseError, ScraperRunManager
from app.collection.legacy_core.storage import normalize_run_queue_rules


def context(site="ultrapackv2", item_type="plugin", account="coproducaolancamentos", slot="default"):
    return {"site_key":site,"item_type_key":item_type,"account_key":account,"slot_name":slot}


def test_manager_allows_independent_sites_and_locks_same_account_context():
    manager=ScraperRunManager();first=manager.create_run(context(),auto_load_summary=False);same=manager.create_run(context(slot="secondary"),auto_load_summary=False);other=manager.create_run(context(site="plugintheme",item_type="plugin_theme"),auto_load_summary=False)
    manager._acquire_account_lock(first)
    with pytest.raises(AccountInUseError):manager._acquire_account_lock(same)
    assert manager._acquire_account_lock(other)=="plugintheme:coproducaolancamentos"


def test_stopped_secondary_run_can_be_removed_cleanly():
    manager=ScraperRunManager();manager.create_run(context(),auto_load_summary=False);secondary=manager.create_run(context(site="plugintheme",item_type="plugin_theme"),auto_load_summary=False)
    result=manager.remove_run(secondary.run_id)
    assert result["ok"] and secondary.run_id not in manager.list_run_ids()


def test_queue_starts_reusable_target_and_does_not_duplicate_running_target():
    source=context(site="plugintheme",item_type="plugin_theme");target=context();manager=ScraperRunManager()
    class Target:
        run_id="target-run"
        def is_running(self):return False
    reusable=Target();manager._find_reusable_run_for_context=lambda _context:reusable;calls=[];manager.start_run=lambda run_id,**kwargs:calls.append((run_id,kwargs)) or {"message":"ok"}
    rule={"id":"one","enabled":True,"source":source,"target":target}
    with patch("app.collection.legacy_core.app.load_run_queue_rules",return_value=[rule]):result=manager.trigger_queue_for_context(source,source_run_id="source-run")
    assert result["started"][0]["run_id"]=="target-run" and calls[0][1]["run_payload"]["queue_source_run_id"]=="source-run"
    reusable.is_running=lambda:True
    with patch("app.collection.legacy_core.app.load_run_queue_rules",return_value=[rule]):duplicate=manager.trigger_queue_for_context(source)
    assert not duplicate["started"] and duplicate["skipped"]


def test_queue_normalization_rejects_self_links_duplicates_and_cycles():
    a=context();b=context(site="plugintheme",item_type="plugin_theme");c=context(site="ultrapackv2",item_type="theme")
    rows=normalize_run_queue_rules([{"id":"ab","source":a,"target":b},{"id":"bc","source":b,"target":c},{"id":"ca","source":c,"target":a},{"id":"same","source":a,"target":a},{"id":"dup","source":a,"target":b}])
    assert [x["id"] for x in rows]==["ab","bc"]
