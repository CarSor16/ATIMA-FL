"""Experiment configuration, independent of any particular attack/model implementation."""

from dataclasses import asdict, dataclass, field, fields
import hashlib
import json
import math
from pathlib import Path
from .registry import Registry


@dataclass(frozen=True)
class ExperimentConfig:
    name: str = "Baseline"
    dataset_root: str = ""
    output_root: str = "results"
    seed: int = 2026
    clients: int = 10
    servers: int = 1
    client_servers: tuple = ()
    server_execution: str = "processes"
    rounds: int = 50
    local_epochs: int = 3
    batch_size: int = 128
    learning_rate: float = 0.001
    input_dim: int = 60
    num_classes: int = 5
    dataset: str = "edge_iiot"
    dataset_params: dict = field(default_factory=dict)
    partition: str = "iid"
    partition_params: dict = field(default_factory=dict)
    model: str = "mlp"
    model_params: dict = field(default_factory=dict)
    optimizer: str = "adam"
    optimizer_params: dict = field(default_factory=dict)
    loss: str = "cross_entropy"
    loss_params: dict = field(default_factory=dict)
    metrics: str = "classification"
    metrics_params: dict = field(default_factory=dict)
    attack: str = "none"
    attack_params: dict = field(default_factory=dict)
    malicious_clients: tuple = (0, 1)
    attack_start: int = 10
    attack_end: int = 50
    aggregation: str = "fedavg"
    aggregation_params: dict = field(default_factory=dict)
    defenses: tuple = ()
    minimum_rounds: int = 30
    patience: int = 10
    min_delta: float = 0.001
    recall_floor: float = 0.5
    coverage_window: int = 5
    cpu_budget: int = 48
    client_cpus: int = 4
    client_gpu_fraction: float = 0.5
    paired_clean: str = ""
    paired_rounds: int = 0
    plugin_directory: str = ""

    def registry(self):
        if not hasattr(self, "_component_snapshot"):
            object.__setattr__(self, "_component_snapshot", Registry(self.plugin_directory or None))
        return self._component_snapshot

    def __getstate__(self):
        # A process receives plain configuration, never cached dynamic functions.
        return asdict(self)

    def __setstate__(self, state):
        expected = {item.name for item in fields(self)}
        if set(state) != expected:
            raise ValueError("Serialized configuration fields differ from this version")
        for key, value in state.items():
            object.__setattr__(self, key, value)

    def validate(self, registry=None):
        registry = registry or Registry(self.plugin_directory or None)
        object.__setattr__(self, "_component_snapshot", registry)
        if not self.name or any(v in self.name for v in "/\\") or self.name in {".", ".."}:
            raise ValueError("Experiment name must be a single directory name")
        integer_keys = (
            "seed",
            "clients",
            "servers",
            "rounds",
            "local_epochs",
            "batch_size",
            "input_dim",
            "num_classes",
            "attack_start",
            "attack_end",
            "minimum_rounds",
            "patience",
            "coverage_window",
            "cpu_budget",
            "client_cpus",
            "paired_rounds",
        )
        if any(type(getattr(self, key)) is not int for key in integer_keys):
            raise ValueError("Integer training/resource parameters required")
        if (
            self.seed < 0
            or min(self.clients, self.local_epochs, self.batch_size, self.input_dim) < 1
        ):
            raise ValueError("Invalid seed/training dimensions")
        if self.num_classes < 2 or not 1 <= self.rounds <= 50:
            raise ValueError("Classification requires >=2 classes; experiments allow 1..50 rounds")
        if not 1 <= self.servers <= self.clients:
            raise ValueError("Aggregation server count must be between 1 and total clients")
        if self.server_execution not in {"processes", "slurm_nodes"}:
            raise ValueError("Server execution must be processes or slurm_nodes")
        if self.server_execution == "slurm_nodes" and self.servers < 2:
            raise ValueError("Physical multi-host aggregation requires at least two servers")
        assignment = self.server_assignment()
        if len(assignment) != self.clients or any(
            type(sid) is not int or not 0 <= sid < self.servers for sid in assignment
        ):
            raise ValueError("Assign exactly one valid aggregation server to every client")
        if set(assignment) != set(range(self.servers)):
            raise ValueError("Every aggregation server requires at least one client")
        if not math.isfinite(self.learning_rate) or self.learning_rate <= 0:
            raise ValueError("Learning rate must be finite and positive")
        if min(self.minimum_rounds, self.patience, self.coverage_window, self.client_cpus) < 1:
            raise ValueError("Positive stopping/resource parameters required")
        if (
            not math.isfinite(self.min_delta)
            or self.min_delta < 0
            or not 0 <= self.recall_floor <= 1
        ):
            raise ValueError("Invalid stopping thresholds")
        if (
            self.cpu_budget < self.client_cpus + self.servers + 1
            or not 0 < self.client_gpu_fraction <= 1
        ):
            raise ValueError("Invalid CPU/GPU resource budget")
        if any(
            type(cid) is not int or not 0 <= cid < self.clients for cid in self.malicious_clients
        ):
            raise ValueError("Malicious client IDs must be valid logical integers")
        if len(set(self.malicious_clients)) != len(self.malicious_clients):
            raise ValueError("Duplicate malicious client IDs")
        if not 1 <= self.attack_start <= self.attack_end <= 50:
            raise ValueError("Attack window must be within 1..50")
        if self.attack != "none" and not self.malicious_clients:
            raise ValueError("An attack requires malicious clients")
        if self.attack != "none" and self.attack_start > self.rounds:
            raise ValueError("Attack starts after the round cap")
        if self.paired_rounds and not 1 <= self.paired_rounds <= self.rounds:
            raise ValueError("Invalid paired round cap")
        for kind, identifier, params in self.selections():
            registry.parameters(kind, identifier, params)
            hook = registry.get(kind, identifier).hooks.get("validate")
            if hook:
                hook(self, registry.parameters(kind, identifier, params))
                if kind == "aggregator" and self.servers > 1:
                    from dataclasses import replace

                    for sid in range(self.servers):
                        ids = [cid for cid, group in enumerate(assignment) if group == sid]
                        group_config = replace(
                            self,
                            clients=len(ids),
                            servers=1,
                            client_servers=(),
                            server_execution="processes",
                            malicious_clients=tuple(
                                i for i, cid in enumerate(ids) if cid in self.malicious_clients
                            ),
                        )
                        try:
                            hook(group_config, registry.parameters(kind, identifier, params))
                        except ValueError as error:
                            raise ValueError(f"Aggregation server {sid}: {error}") from error
        for defense in self.defenses:
            if set(defense) != {"id", "params"}:
                raise ValueError("Defense stages require id and params")
            registry.parameters("defense", defense["id"], defense["params"])
        if len({d["id"] for d in self.defenses}) != len(self.defenses):
            raise ValueError("Duplicate defense stage")
        return self

    def server_assignment(self):
        """Stable logical routing; explicit assignments override round-robin groups."""
        return tuple(self.client_servers) or tuple(
            cid % self.servers for cid in range(self.clients)
        )

    def selections(self):
        return [
            ("attack", self.attack, self.attack_params),
            ("model", self.model, self.model_params),
            ("dataset", self.dataset, self.dataset_params),
            ("partition", self.partition, self.partition_params),
            ("optimizer", self.optimizer, self.optimizer_params),
            ("loss", self.loss, self.loss_params),
            ("metrics", self.metrics, self.metrics_params),
            ("aggregator", self.aggregation, self.aggregation_params),
        ]

    def parameters(self, kind):
        for selected_kind, identifier, params in self.selections():
            if selected_kind == kind:
                return self.registry().parameters(kind, identifier, params)
        raise ValueError(kind)

    def resolved(self, registry=None):
        registry = registry or self.registry()
        value = asdict(self)
        for kind, identifier, params in self.selections():
            key = "aggregation_params" if kind == "aggregator" else f"{kind}_params"
            value[key] = registry.parameters(kind, identifier, params)
        value["defenses"] = [
            {"id": d["id"], "params": registry.parameters("defense", d["id"], d["params"])}
            for d in self.defenses
        ]
        return value

    def pairing_id(self, dataset_hashes):
        payload = self.resolved()
        for key in (
            "name",
            "output_root",
            "attack",
            "attack_params",
            "malicious_clients",
            "attack_start",
            "attack_end",
            "paired_clean",
            "paired_rounds",
            "plugin_directory",
        ):
            payload.pop(key)
        payload["dataset_hashes"] = dataset_hashes
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_dict(cls, values):
        values = dict(values)
        unknown = set(values) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown experiment fields: {sorted(unknown)}")
        for key in ("malicious_clients", "defenses", "client_servers"):
            if key in values:
                values[key] = tuple(values[key])
        return cls(**values).validate()

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.suffix == ".json":
            value = json.loads(path.read_text(encoding="utf-8"))
        else:
            import tomllib

            with path.open("rb") as stream:
                value = tomllib.load(stream)
        return cls.from_dict(value.get("experiment", value))

    def save(self, path):
        import tomli_w

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(tomli_w.dumps({"experiment": self.resolved()}).encode())
