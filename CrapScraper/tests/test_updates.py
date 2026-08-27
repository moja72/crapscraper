from app.updates.repository import UpdateRepository
from tests.update_fakes import approval

def test_materialization_is_idempotent_and_source_is_immutable(tmp_path):
    repo=UpdateRepository(tmp_path)
    assert repo.materialize([approval()])=={"created":1,"total":1}
    assert repo.materialize([approval()])=={"created":0,"total":1}
    changed=approval();changed["source_name"]="UltraPackV2";changed["source_product_url"]="https://ultrapack.example/changed"
    repo.materialize([changed]);job=repo.list()["items"][0]
    assert job["source_kind"]=="plugintheme" and "plugintheme" in job["source_url"]
    counts=repo.list()["counts"]
    assert counts["total"]==sum(counts[x] for x in ("prepared","running","success","error"))
