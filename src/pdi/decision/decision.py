from dataclasses import dataclass, field

from .action import Action
from .requirement import RequirementType


@dataclass
class Decision:
    actions: list[Action] = field(default_factory=list)
    requirements: list[RequirementType] = field(default_factory=list)
    reason: str = ""
    confidence: float = 1.0