class NelError(Exception):
    pass


class ProviderError(NelError):
    pass


class ApplicationError(NelError):
    pass


class PersistenceStartupError(NelError):
    pass
