from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADD_JS = (ROOT / "app" / "static" / "js" / "add.js").read_text(encoding="utf-8")
LAUNCHER = (ROOT / "Abrir CrapScraper.bat").read_text(encoding="utf-8")
EXECUTOR = (ROOT / "app" / "additions" / "executor.py").read_text(encoding="utf-8")
WORDPRESS = (ROOT / "app" / "additions" / "wordpress.py").read_text(encoding="utf-8")


def test_addition_page_matches_operational_legacy_structure():
    for token in (
        '<strong>Ambiente</strong>',
        '<h2>Adicionar produtos</h2>',
        '<h2>Produtos para adicionar</h2>',
        'id="add-materialize">Sincronizar aprovados</button>',
        'id="add-select-page">Selecionar página</button>',
        'id="add-select-all">Selecionar todo resultado</button>',
        'id="add-clear-selection">Limpar seleção</button>',
        'id="add-batch-start" class="primary" disabled>Executar selecionados</button>',
        'id="add-history-details"',
        'id="add-log-details"',
    ):
        assert token in ADD_JS


def test_addition_environment_reuses_update_prerequisites():
    assert 'get("/api/updates/environment")' in ADD_JS
    assert 'post("/api/updates/environment/check",{})' in ADD_JS
    assert 'id="add-environment-refresh">Verificar pré-requisitos</button>' in ADD_JS


def test_addition_selection_is_sent_as_explicit_job_ids():
    assert 'post("/api/additions/batch/start",{job_ids:ids})' in ADD_JS
    assert 'filteredActionableIds' in ADD_JS
    assert 'data-add-select-check' in ADD_JS
    assert 'pageSize:5' in ADD_JS


def test_local_launcher_enables_real_additions_but_keeps_explicit_off_switch():
    assert 'if not defined SCRAPER_ADDITION_EXECUTION_ENABLED set "SCRAPER_ADDITION_EXECUTION_ENABLED=1"' in LAUNCHER
    assert 'SCRAPER_ADDITION_EXECUTION_ENABLED=0' in LAUNCHER


def test_existing_real_addition_pipeline_creates_and_validates_product():
    for token in (
        'self.store.create_parent(job,media_id,download_ref)',
        'self.store.ensure_variations(product_id,job,download_ref)',
        'self.store.validate(product_id,job,variation_ids)',
    ):
        assert token in EXECUTOR
    assert '"categories":categories' in WORDPRESS
    assert '"tags":tags' in WORDPRESS
    assert '"pt_versao"' in WORDPRESS
