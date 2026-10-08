"""Small contracts shared by components; no Flower or PyTorch imports."""

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Component:
    id: str
    kind: str
    title: str
    description: str
    parameters: dict = field(default_factory=dict)
    hooks: dict[str, Callable] = field(default_factory=dict, repr=False)
    references: tuple[str, ...] = ()
    version: str = "1"

    def public(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "description": self.description,
            "parameters": self.parameters,
            "references": list(self.references),
            "version": self.version,
            "hooks": sorted(self.hooks),
        }


@dataclass
class DataBatch:
    x: Any
    y: Any
    source_ids: Any
    metadata: dict = field(default_factory=dict)


@dataclass
class TrainingBatch:
    x: Any
    y: Any
    changed_label_indices: Any
    added_sample_indices: Any
    notes: dict = field(default_factory=dict)


@dataclass
class AttackContext:
    config: Any
    client: int
    round_id: int
    global_arrays: Any = None
    local_arrays: Any = None
    raw_by_client: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)
    attackable_indices: tuple = ()

    @property
    def active(self):
        return (
            self.config.attack != "none"
            and self.client in self.config.malicious_clients
            and self.config.attack_start <= self.round_id <= self.config.attack_end
        )
