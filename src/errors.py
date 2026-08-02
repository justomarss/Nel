class NelError(Exception):
    pass


class ProviderError(NelError):
    pass


class ApplicationError(NelError):
    pass


class PersistenceStartupError(NelError):
    pass


class PersistenceOperationError(ApplicationError):
    def __init__(self):
        super().__init__("Yaddaş xidməti hazırda əlçatan deyil.")


class ContextAssemblyError(ApplicationError):
    def __init__(self, reason_code: str):
        super().__init__("Söhbət konteksti hazırda əlçatan deyil.")
        self.reason_code = reason_code
