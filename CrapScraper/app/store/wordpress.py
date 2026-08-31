from __future__ import annotations
import hashlib,hmac,json,os,time
from urllib.request import Request,urlopen

class WordPressManualQueueClient:
    """Implementa exatamente o contrato HMAC do plugin crapscraper-manual-update."""
    pending_route="/crapscraper/v1/manual-updates/pending"
    status_route="/crapscraper/v1/manual-updates/{request_id}/status"
    history_route="/crapscraper/v1/update-history"
    history_confirm_route="/crapscraper/v1/update-history/{operation_id}"
    terminal_states=frozenset({"up_to_date","no_match","source_not_found","source_version_missing","relationship_required","comparison_stale","completed","error","blocked","rolled_back","rollback_required"})
    def __init__(self,base_url=None,secret=None,transport=None):self.base_url=(base_url or os.getenv("SCRAPER_WP_BASE_URL","")).rstrip("/");self.secret=secret or os.getenv("SCRAPER_WORDPRESS_MANUAL_SECRET","");self.transport=transport or self._transport
    @property
    def configured(self):return self.base_url.startswith("https://") and len(self.secret)>=24
    def _transport(self,request):
        with urlopen(request,timeout=20) as response:return response.status,response.read()
    def _request(self,method,route,subject,payload=None):
        if not self.configured:raise RuntimeError("Monitor WordPress não configurado")
        timestamp=str(int(time.time()));nonce=os.urandom(16).hex();message="\n".join((timestamp,nonce,method,route,subject));signature=hmac.new(self.secret.encode(),message.encode(),hashlib.sha256).hexdigest();body=json.dumps(payload).encode() if payload is not None else None;request=Request(self.base_url+"/wp-json"+route,data=body,method=method,headers={"Accept":"application/json","Content-Type":"application/json","X-CrapScraper-Timestamp":timestamp,"X-CrapScraper-Nonce":nonce,"X-CrapScraper-Signature":signature});status,raw=self.transport(request)
        if status>=400:raise RuntimeError(f"WordPress recusou monitor: HTTP {status}")
        value=json.loads(raw or b"{}");
        if not isinstance(value,dict) or value.get("ok") is False:raise RuntimeError(str(value.get("message") if isinstance(value,dict) else "Resposta WordPress inválida"))
        return value
    def pending(self):return list(self._request("GET",self.pending_route,"poll").get("requests",[]))
    def report(self,request_id,**payload):return self._request("POST",self.status_route.format(request_id=request_id),request_id,payload)
    def send_history(self, event):
        operation_id=str(event.get("operation_id") or "")
        if not operation_id:raise ValueError("operation_id obrigatório")
        return self._request("POST",self.history_route,operation_id,event)
    def confirm_history(self, operation_id):
        operation_id=str(operation_id or "")
        if not operation_id:raise ValueError("operation_id obrigatório")
        return self._request("GET",self.history_confirm_route.format(operation_id=operation_id),operation_id)

class FixtureManualQueue:
    configured=True
    def __init__(self):self.reports=[]
    def pending(self):return []
    def report(self,request_id,**payload):self.reports.append((request_id,payload));return {"ok":True}
