"""Isolated modular UI server; no external HTTP or production credentials."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.bootstrap import create_application
from app.sync import E2EExecutionRecorder


class CatalogGateway:
    def categories(self):
        return [{'id': 1, 'name': 'Plugins', 'count': 15}]

    def products(self, **filters):
        return [{'id': 101 + i, 'name': f'E2E Plugin {i + 1}', 'type': 'variable',
                 'status': 'publish', 'permalink': f'https://shop.test/{i + 1}',
                 'categories': [{'id': 1, 'name': 'Plugins'}],
                 'meta_data': [{'key': 'pt_versao', 'value': '1.0'},
                               {'key': 'site_oficial', 'value': f'https://vendor.test/{i + 1}'}]}
                for i in range(15)]


if __name__ == '__main__':
    with patch('requests.sessions.Session.request', side_effect=RuntimeError('External HTTP disabled in E2E')), patch(
            'app.credits.CreditService.refresh', return_value={
                'ok': True, 'authenticated': False, 'credits': None, 'status': 'not_configured', 'logs': []}):
        app = create_application()
        app.services.catalogs.gateway = CatalogGateway()
        # Seed approvals as well as jobs: the real reconciliation removes ready
        # products whose approval has been revoked or was never persisted.
        from app.comparison import decisions
        for job in app.services.additions.repository.list(page_size=100)['items']:
            decisions.save_decision(job['comparison_item_id'], 'approve_new_product',
                source_name=job['product_name'], source_version=job['source_version'],
                source_product_url=job['source_url'], source_official_url=job['official_url'],
                status='new_source')
        for service in (app.services.updates, app.services.additions):
            recorder = E2EExecutionRecorder()
            service.executor.execute = recorder.execute
            service.executor.calls = recorder.calls
            service.executor.enabled = True
        app.services.updates.environment_validation = {
            'woocommerce': {'ok': True}, 'storage': {'ok': True}, 'source': {'ok': True},
            'sources': {key: {'ok': True} for key in ('plugintheme', 'ultrapackv2')},
        }
        app.serve()
