from __future__ import annotations
import hashlib,os,zipfile
from pathlib import Path
from app.additions.chatgpt import ChatGPTContentService
from app.additions.content import valid_content
from app.additions.images import ImageService
from app.additions.logging import safe_message
from app.additions.models import AdditionError
from app.additions.preparation import reusable_artifact
from app.additions.source import AdditionSourceService,ProductResearchService
from app.additions.wordpress import AdditionStoreGateway,ArtifactPublisher
from app.updates.sources import SourceFailure

def enabled(name):return os.getenv(name,"").strip().lower() in {"1","true","yes","on"}

class AdditionExecutor:
    def __init__(self,repository,*,sources=None,research=None,content=None,images=None,store=None,publisher=None,staging_root=None,execution_enabled=None,allowed_item_ids=None):
        self.repository=repository;self.sources=sources or AdditionSourceService();self.research=research or ProductResearchService();self.content=content or ChatGPTContentService();self.images=images or ImageService(repository.path.parent/"addition_images");self.store=store or AdditionStoreGateway();self.publisher=publisher or ArtifactPublisher();self.staging_root=staging_root or repository.path.parent/"addition_staging";self.enabled=enabled("SCRAPER_ADDITION_EXECUTION_ENABLED") if execution_enabled is None else execution_enabled;self.allowed=frozenset(x.strip() for x in os.getenv("SCRAPER_ADDITION_EXECUTION_ALLOWED_ITEM_IDS","").split(",") if x.strip()) if allowed_item_ids is None else frozenset(allowed_item_ids)
    def authorize(self,job):
        if not self.enabled:raise PermissionError("Execução real desabilitada por SCRAPER_ADDITION_EXECUTION_ENABLED")
        if self.allowed and job["comparison_item_id"] not in self.allowed and job["job_id"] not in self.allowed:raise PermissionError(f"Item {job['comparison_item_id']} não autorizado")
    def execute(self,job_id):
        job=self.repository.get(job_id)
        if job["state"]=="running":raise ValueError("Job já está em execução")
        attempt=self.repository.begin(job_id);aid=attempt["attempt_id"];stage="validating"
        def progress(s,m):
            nonlocal stage;stage=s;self.repository.progress(job_id,aid,s,m)
        try:
            self.authorize(job);progress("validating",f"Validando adição de {job['product_name']}.")
            if not job["source_url"] or not job["source_version"]:raise ValueError("Fonte e versão aprovadas são obrigatórias")
            resolved=self.research.resolve(job)
            if not resolved.get("official_url"):raise RuntimeError("Página oficial não confirmada")
            if not resolved.get("developer"):raise RuntimeError("Desenvolvedor não confirmado por fonte confiável")
            job=self.repository.patch(job_id,official_url=resolved["official_url"],developer=resolved["developer"]);progress("resolving_source",f"Desenvolvedor e página oficial confirmados: {job['developer']}.")
            source=self.sources.source(job)
            if source.kind!=job["source_kind"]:raise RuntimeError("Fonte resolvida diverge da aprovação imutável")
            source.validate_authentication();version=source.confirm_version(job)
            if version!=job["source_version"]:raise RuntimeError(f"Versão mudou desde a aprovação: {job['source_version']} → {version}")
            artifact=reusable_artifact(job)
            if artifact:
                digest=hashlib.sha256(artifact.read_bytes()).hexdigest()
                if digest!=job["artifact_sha256"] or not zipfile.is_zipfile(artifact):artifact=None
            if artifact is None:
                progress("downloading",f"Baixando exclusivamente do {source.display_name}.");target=self.staging_root/job_id/"artifact.zip";download=source.download(job,target);artifact=download.path;job=self.repository.patch(job_id,source_download_url=download.final_url,artifact_path=str(artifact),artifact_sha256=download.sha256)
            progress("validating_zip",f"ZIP íntegro e SHA-256 confirmado: {job['artifact_sha256'][:12]}…")
            if not valid_content(job):
                progress("generating_description","Gerando breve descrição, conteúdo, categorias e tags no ChatGPT.");generated=self.content.generate(job);job=self.repository.patch(job_id,product_name=generated.get("product_name") or job["product_name"],short_description=generated["short_description"],content=generated["content"],categories=generated["categories"],tags=generated["tags"])
            else:progress("generating_description","Conteúdo válido já persistido; etapa reutilizada.")
            if not self.images.valid(job.get("image_path","")):
                progress("generating_image","Gerando imagem principal em etapa isolada.")
                try:image=self.images.generate(job);job=self.repository.patch(job_id,image_state="ready",image_path=str(image),image_error="")
                except Exception as exc:self.repository.patch(job_id,image_state="error",image_error=safe_message(exc));raise
            else:progress("generating_image","Imagem válida já persistida; etapa reutilizada.")
            progress("reconciling_woocommerce","Reconciliando o job antes de criar qualquer produto.");product_id=int(job.get("woo_product_id") or self.store.reconcile(job) or 0)
            download_ref=str(job.get("published_download_url") or "")
            if not product_id:
                if not download_ref:
                    progress("uploading_file","Publicando ZIP validado no destino de downloads.");download_ref=self.publisher.publish(job,artifact);job=self.repository.patch(job_id,published_download_url=download_ref)
                media_id=int(job.get("media_id") or 0)
                if not media_id:
                    progress("uploading_image","Enviando imagem à Biblioteca de Mídia.");media_id=self.store.upload_media(Path(job["image_path"]),job["product_name"]);job=self.repository.patch(job_id,media_id=media_id)
                progress("creating_woocommerce","Criando produto pai variável inicialmente como rascunho.");product=self.store.create_parent(job,media_id,download_ref);product_id=int(product.get("id") or 0)
                if not product_id:raise RuntimeError("WooCommerce não retornou o ID do produto")
                job=self.repository.patch(job_id,woo_product_id=product_id)
            else:
                job=self.repository.patch(job_id,woo_product_id=product_id);progress("creating_woocommerce",f"Produto WooCommerce #{product_id} reconciliado; criação não repetida.")
                if not download_ref:
                    progress("uploading_file","Produto reconciliado sem URL de ZIP persistida; publicando o artefato validado.");download_ref=self.publisher.publish(job,artifact);job=self.repository.patch(job_id,published_download_url=download_ref)
            variation_ids=self.store.ensure_variations(product_id,job,download_ref);job=self.repository.patch(job_id,woo_variation_ids=variation_ids)
            progress("validating","Validando produto, metadados, imagem, ZIP e duas variações.")
            if not self.store.validate(product_id,job,variation_ids):raise RuntimeError("Validação final do WooCommerce divergiu")
            status=os.getenv("SCRAPER_ADDITION_PUBLICATION_STATE","draft").strip().lower()
            if status not in {"draft","pending","publish"}:raise ValueError("SCRAPER_ADDITION_PUBLICATION_STATE inválido")
            if status!="draft":self.store.set_status(product_id,status)
            self.repository.patch(job_id,publication_state=status);progress("completed",f"Produto #{product_id} concluído com estado {status}.");self.repository.finish(job_id,aid,True,"completed");return {"ok":True,"job_id":job_id,"woo_product_id":product_id,"publication_state":status}
        except Exception as exc:
            if isinstance(exc,SourceFailure):base=exc.error;error=AdditionError(message=base.message,technical_message=base.technical_message,code=base.code,stage=stage,source=base.source,recoverable=base.recoverable)
            else:error=AdditionError(message=safe_message(exc),technical_message=repr(exc),code="addition_execution_failed",stage=stage,source=job.get("source_name",""),recoverable=not isinstance(exc,(PermissionError,ValueError)))
            error.job_id=job_id;error.attempt_id=aid;self.repository.finish(job_id,aid,False,stage,error.to_dict());return {"ok":False,"job_id":job_id,"error":error.to_dict()}
