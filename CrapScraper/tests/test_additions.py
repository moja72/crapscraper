from app.additions.repository import AdditionRepository
from tests.addition_fakes import approval

def test_materialization_idempotent_counts_and_immutable_source(tmp_path):
    repo=AdditionRepository(tmp_path);assert repo.materialize([approval()])["created"]==1;assert repo.materialize([approval()])["created"]==0
    changed=approval();changed.update(source_name="UltraPackV2",source_product_url="https://ultrapackv2.com/changed");repo.materialize([changed]);job=repo.list()["items"][0]
    assert job["source_kind"]=="plugintheme" and "plugintheme" in job["source_url"]
    c=repo.list()["counts"];assert c["total"]==sum(c[x] for x in ("prepared","running","success","error"))
