from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from paperman.models.paper import Paper, SourceType


class BaseFetcher(ABC):
    name: str = "base"

    @abstractmethod
    def fetch(self, identifier: str, source_type: SourceType) -> Optional[Paper]:
        ...
