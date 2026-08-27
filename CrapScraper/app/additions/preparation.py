from pathlib import Path
from app.additions.content import valid_content

def reusable_artifact(job):
    path=Path(str(job.get("artifact_path") or ""));return path if path.is_file() and bool(job.get("artifact_sha256")) else None
def reusable_content(job):return valid_content(job)
