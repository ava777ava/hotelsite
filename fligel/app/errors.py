class ApiError(Exception):
    """Ошибка, которую API отдаёт клиенту как {"error": message}."""

    def __init__(self, status: int, message: str, extra: dict | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra or {}
