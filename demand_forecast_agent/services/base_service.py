from abc import ABC, abstractmethod


class AgentService(ABC):

    def __init__(self, name):
        self.name = name

    @abstractmethod
    def execute(self):
        pass