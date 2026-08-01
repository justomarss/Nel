class MemoryPolicy:
    def allows(self, _result, _context) -> bool:
        return False


class KnowledgePolicy:
    def allows(self, _result, _context) -> bool:
        return False


class IdentityPolicy:
    def allows(self, _result, _context) -> bool:
        return False
