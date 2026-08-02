class Brain:
    def __init__(self, provider):
        self.provider = provider

    def think(self, prompt: str) -> str:
        return self.provider.generate(prompt)
