class NelError(Exception):
    pass


class ProviderError(NelError):
    pass


class ApplicationError(NelError):
    pass


class PersistenceStartupError(NelError):
    pass


class ContextAssemblyError(ApplicationError):
    def __init__(self, reason_code: str):
        super().__init__("Söhbət konteksti hazırda əlçatan deyil.")
        self.reason_code = reason_code
