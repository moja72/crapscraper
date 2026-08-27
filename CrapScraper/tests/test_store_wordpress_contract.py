import hashlib,hmac,json
from app.store.wordpress import WordPressManualQueueClient

def test_plugin_routes_and_hmac_contract():
    captured=[]
    def transport(request):captured.append(request);return 200,json.dumps({"ok":True,"requests":[]}).encode()
    secret="x"*32;client=WordPressManualQueueClient("https://example.test",secret,transport);assert client.pending()==[];request=captured[0];headers={k.lower():v for k,v in request.header_items()};route="/crapscraper/v1/manual-updates/pending";message="\n".join((headers["x-crapscraper-timestamp"],headers["x-crapscraper-nonce"],"GET",route,"poll"));assert headers["x-crapscraper-signature"]==hmac.new(secret.encode(),message.encode(),hashlib.sha256).hexdigest();assert request.full_url.endswith("/wp-json"+route)
def test_status_contract_uses_request_id_subject():
    captured=[]
    def transport(request):captured.append(request);return 200,b'{"ok":true}'
    WordPressManualQueueClient("https://example.test","x"*32,transport).report("abc-123",status="completed",message="OK");assert captured[0].full_url.endswith("/manual-updates/abc-123/status") and json.loads(captured[0].data)["status"]=="completed"
