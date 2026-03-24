from .utils import validate


class Engine:
    def __init__(self, name):
        self.name = validate(name)

    def run(self):
        return f"Engine {self.name} running"
