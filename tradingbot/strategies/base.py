class Strategy:
    name: str = "base"

    def signal(self, closes: list[float]) -> str:
        raise NotImplementedError
