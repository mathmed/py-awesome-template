from abc import ABC, abstractmethod


class ReadinessCheckContract(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_ready(self) -> bool: ...
