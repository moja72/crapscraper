class StoreHistoryService:
    def __init__(self,repository):self.repository=repository
    def monitor(self):return self.repository.history()
