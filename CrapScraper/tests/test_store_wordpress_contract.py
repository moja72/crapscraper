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

def test_already_updated_is_a_terminal_protocol_state():
    assert "already_updated" in WordPressManualQueueClient.terminal_states

def test_history_post_and_confirmation_use_operation_hmac_subject():
    captured=[]
    event={"operation_id":"upd-1-a2","job_id":"upd-1","woo_product_id":89893,"source":"UltraPackV2","previous_version":"2.3.2.1","new_version":"2.3.4","status":"completed","completed_at":"2026-08-31T03:42:00+00:00"}
    def transport(request):captured.append(request);return 200,json.dumps({"ok":True,"event":event}).encode()
    client=WordPressManualQueueClient("https://example.test","x"*32,transport);client.send_history(event);client.confirm_history(event["operation_id"])
    assert captured[0].full_url.endswith("/wp-json/crapscraper/v1/update-history")
    assert captured[1].full_url.endswith("/wp-json/crapscraper/v1/update-history/upd-1-a2")
    for request,method in zip(captured,("POST","GET")):
        headers={key.lower():value for key,value in request.header_items()};route="/crapscraper/v1/update-history"+("/upd-1-a2" if method=="GET" else "")
        message="\n".join((headers["x-crapscraper-timestamp"],headers["x-crapscraper-nonce"],method,route,"upd-1-a2"))
        assert headers["x-crapscraper-signature"]==hmac.new(("x"*32).encode(),message.encode(),hashlib.sha256).hexdigest()
