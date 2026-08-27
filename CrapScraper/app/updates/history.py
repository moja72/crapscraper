from app.updates.repository import UpdateRepository


class UpdateHistory:
    def __init__(self, repository: UpdateRepository): self.repository=repository
    def for_job(self, job_id: str): return self.repository.history(job_id)
