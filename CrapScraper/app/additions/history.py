class AdditionHistory:
    def __init__(self,repository):self.repository=repository
    def for_job(self,job_id):return self.repository.history(job_id)
