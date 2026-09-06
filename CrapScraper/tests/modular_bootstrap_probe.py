"""Fresh-process integration: production bootstrap, SQLite and executor, local IO."""
import json
import os
import sys
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.bootstrap import create_application
from app.web.api import ApplicationServices
from app.updates.service import UpdateService, UpdateExecutionBlocked
from app.updates.executor import UpdateExecutor
from app.updates.repository import UpdateRepository
from app.updates.adapters import FilesystemInstaller
from app.updates.sources import SourceRegistry
from app.comparison import decisions
from tests.update_fakes import FakeSource, approval


def run(root):
    entered, release = threading.Event(), threading.Event()
    blocked_key = ['a']
    source = FakeSource('ultrapackv2')
    source.validate_access = lambda job: {'version': '2.1'}
    source.confirm_version = lambda job: '2.1'
    download = source.download

    def controlled_download(job, target):
        if job['comparison_item_id'] == blocked_key[0]:
            entered.set()
            assert release.wait(10), 'worker was not released'
        return download(job, target)

    source.download = controlled_download

    class Woo:
        base, auth = 'https://store.example.test', ('fixture', 'fixture')
        versions = {101: '1.0', 102: '1.0', 103: '1.0'}
        writes = []
        def check_connection(self): return {'ok': True}
        def get_product(self, pid): return {'id': pid, 'meta_data': [{'key': 'pt_versao', 'value': self.versions[pid]}]}
        get_product_fresh = get_product
        def prepare_job(self, job): job['target_filename'] = f"{job['woo_product_id']}.zip"
        def set_version(self, pid, version): self.writes.append((pid, version)); self.versions[pid] = version

    woo = Woo()
    downloads = root / 'downloads'
    downloads.mkdir()
    for pid in woo.versions:
        with zipfile.ZipFile(downloads / f'{pid}.zip', 'w') as archive:
            archive.writestr('plugin/main.php', 'old')

    def services(settings, runtime):
        repo = UpdateRepository(root)
        for key, pid in zip('abc', woo.versions):
            row = approval(key, kind='UltraPackV2', woo=pid)
            decisions.save_decision(key, 'approve_update', site_id=str(pid), site_name=row['site_name'],
                source_name=row['source_name'], source_version=row['source_version'], site_version='1.0',
                source_product_url=row['source_product_url'], status='update_available',
                recommended_action='review_and_approve_update')
        repo.materialize(decisions.list_approved_updates())
        executor = UpdateExecutor(repo, sources=SourceRegistry([source]), woo=woo,
            installer=FilesystemInstaller(downloads), enabled=True, allowed_product_ids=frozenset())
        return SimpleNamespace(updates=UpdateService(root, repository=repo, executor=executor))

    with patch.object(ApplicationServices, 'build', side_effect=services), patch(
            'app.current_app_recovery.ensure_source_session', return_value=object()):
        app = create_application()
        service, repo = app.services.updates, app.services.updates.repository
        jobs = {row['comparison_item_id']: row for row in repo.list(page_size=100)['items']}
        a = jobs['a']['job_id']
        attempt = repo.begin_attempt(a)
        repo.finish(a, attempt['attempt_id'], success=False, stage='validating',
            error={'code': 'source_version_drift', 'recoverable': False, 'message': 'source drift'})
        result, failures = [], []

        def retry():
            try: result.append(service.retry(a))
            except Exception as error: failures.append(repr(error))

        worker = threading.Thread(target=retry)
        worker.start()
        try:
            assert entered.wait(10), failures
            assert service.job(a)['item']['state'] == 'running'
            try: service.retry(a)
            except ValueError: pass
            else: raise AssertionError('duplicate retry was accepted')
        finally:
            release.set()
            worker.join(10)
        assert not worker.is_alive() and not failures and result[0]['ok'], (result, failures)
        assert woo.writes == [(101, '2.1')]
        assert repo.get(a)['source_version'] == '2.1'
        assert decisions.get_decision('a')['status'] == 'updated'
        assert decisions.get_decision('a')['source_version'] == '2.1'
        assert service.materialize()['created'] == 0
        assert repo.get(a)['state'] == 'success'
        try: service.execute(a)
        except UpdateExecutionBlocked: pass
        else: raise AssertionError('completed job restarted')

        # Batch retries traverse the same guarded service and real transaction.
        b = jobs['b']['job_id']
        attempt = repo.begin_attempt(b)
        repo.finish(b, attempt['attempt_id'], success=False, stage='validating',
            error={'code': 'source_version_drift', 'recoverable': False, 'message': 'source drift'})
        blocked_key[0] = 'b'
        entered.clear()
        release.clear()
        service.batch_start([b, jobs['c']['job_id']])
        try:
            assert entered.wait(10), service.batch.results
            snapshot = service.list()
            assert snapshot['counts']['queued'] == snapshot['counts']['running'] == 1
            assert service.job(jobs['c']['job_id'])['item']['state'] == 'queued'
            try: service.retry(jobs['c']['job_id'])
            except UpdateExecutionBlocked: pass
            else: raise AssertionError('queued product was individually dispatched')
        finally:
            release.set()
            service.batch.thread.join(10)
        assert service.batch.state()['success'] == 2, service.batch.results
        assert repo.count() == 3 and len(woo.writes) == 3
        assert all(row['state'] == 'success' for row in service.list()['items'])
        assert decisions.list_approved_updates() == []

        # Parse and provenance run with every bootstrap adapter installed.
        from app.additions import chatgpt_content_response_runtime as content
        from app.additions import chatgpt_playwright as browser
        from app.additions import strict_job_identity_runtime as strict
        from app.additions.chatgpt_job_cache_recovery_runtime import _restore_exact_job_chat
        from app.additions.executor import AdditionExecutor
        from app.additions.repository import AdditionRepository
        from tests.addition_fakes import approval as addition_approval
        import time
        additions = AdditionRepository(root)
        additions.materialize([addition_approval('agricola')])
        job = additions.patch(additions.job_id('agricola'),
            product_name='Agricola - Agriculture and Organic Farm WordPress Theme', kind='theme',
            official_url='https://themeforest.net/item/agricola/39853177', developer='Ultrapack')
        strict.bind_job_identity(job)
        generated = content.parse_content_response((ROOT / 'tests/fixtures/agricola_dom_response.txt').read_text(encoding='utf-8'), job)
        values = {key: generated[key] for key in ('short_description', 'content', 'categories', 'tags')}
        job = additions.patch(job['job_id'], **values)
        browser._update_job_state(job['job_id'],
            conversation_url='https://chatgpt.com/g/g-p-test/c/agricola',
            isolated_chat_version=strict._ISOLATION_VERSION,
            isolated_chat_fingerprint=strict.strict_job_conversation_fingerprint(job['job_id']),
            cache_until=int(time.time()) + 600, content_ready=True,
            content_fingerprint=browser._content_fingerprint(job), content_sha256=browser.content_digest(job))
        persisted = AdditionExecutor(additions)._persist_chatgpt_cache(job['job_id'])
        browser._write_state({})
        assert _restore_exact_job_chat(persisted)
        assert browser.content_reusable(persisted)
        assert not browser.content_reusable({**persisted, 'content': 'another product ' * 50})
        assert not _restore_exact_job_chat({**persisted, 'job_id': 'other-job'})
    return {'ok': True, 'bootstrap': True, 'individualRetry': True, 'batchRetry': True,
            'duplicateBlocked': True, 'completionConsumed': True, 'agricolaRestart': True}


if __name__ == '__main__':
    print(json.dumps(run(Path(os.environ['SCRAPER_DATA_DIR']))))
