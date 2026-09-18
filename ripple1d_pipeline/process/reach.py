from dataclasses import dataclass

from .model import Model


@dataclass
class Reach:
    id: int
    to_id: int
    model: Model
