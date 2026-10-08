"""Discover one-file components. Adding/removing an implementation needs no central list."""

from copy import deepcopy
import hashlib
import importlib.util
import math
from pathlib import Path
import sys
from threading import RLock
from .contracts import Component

# These are protocol categories, not a list of installed implementations.
FOLDERS = {
    "attack": "attacks",
    "model": "models",
    "defense": "defenses",
    "aggregator": "aggregators",
    "dataset": "datasets",
    "partition": "partitions",
    "optimizer": "optimizers",
    "loss": "losses",
    "metrics": "metrics",
}

_FILE_DIGESTS = {}
_REGISTRY_LOCK = RLock()


def validate_parameters(component, values):
    if not isinstance(values, dict):
        raise ValueError(f"{component.id}: parameters must be an object")
    unknown = set(values) - set(component.parameters)
    if unknown:
        raise ValueError(f"{component.id}: unknown parameters {sorted(unknown)}")
    result = {}
    for name, spec in component.parameters.items():
        value = deepcopy(values.get(name, spec.get("default")))
        kind = spec["type"]
        valid = {
            "integer": lambda: type(value) is int,
            "number": lambda: type(value) in (int, float) and math.isfinite(value),
            "boolean": lambda: type(value) is bool,
            "string": lambda: type(value) is str,
            "array": lambda: type(value) is list,
            "object": lambda: type(value) is dict,
        }[kind]()
        if not valid:
            raise ValueError(f"{component.id}.{name}: expected {kind}")
        if "choices" in spec and value not in spec["choices"]:
            raise ValueError(f"{component.id}.{name}: choose from {spec['choices']}")
        if "minimum" in spec and value < spec["minimum"]:
            raise ValueError(f"{component.id}.{name}: minimum {spec['minimum']}")
        if "maximum" in spec and value > spec["maximum"]:
            raise ValueError(f"{component.id}.{name}: maximum {spec['maximum']}")
        if kind == "array" and "items" in spec:
            for item in value:
                check = Component(component.id, component.kind, "", "", {name: spec["items"]})
                validate_parameters(check, {name: item})
        result[name] = value
    return result


class Registry:
    def __init__(self, extra_directory=None, fresh=False):
        with _REGISTRY_LOCK:
            self._discover(extra_directory, fresh)

    def _discover(self, extra_directory, fresh):
        builtins = Path(__file__).resolve().parents[1] / "components"
        self.components = {kind: {} for kind in FOLDERS}
        self.sources = {}
        self.extra_directory = Path(extra_directory).resolve() if extra_directory else None
        roots = [builtins] + ([self.extra_directory] if self.extra_directory else [])
        for root in roots:
            for kind, folder in FOLDERS.items():
                for path in sorted((root / folder).glob("*.py")):
                    if path.name.startswith("_"):
                        continue
                    stat = path.stat()
                    signature = (stat.st_mtime_ns, stat.st_size)
                    cached_file = _FILE_DIGESTS.get(str(path))
                    if fresh or cached_file is None or cached_file[0] != signature:
                        digest = hashlib.sha256(path.read_bytes()).hexdigest()
                        _FILE_DIGESTS[str(path)] = (signature, digest)
                    else:
                        digest = cached_file[1]
                    name = (
                        "atima_component_"
                        + hashlib.sha256((str(path) + digest).encode()).hexdigest()[:20]
                    )
                    spec = importlib.util.spec_from_file_location(name, path)
                    module = sys.modules.get(name)
                    cached = module is not None
                    if not cached:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[name] = module
                    try:
                        if not cached:
                            spec.loader.exec_module(module)
                        component = module.PLUGIN
                    except Exception as error:
                        sys.modules.pop(name, None)
                        raise ValueError(f"Invalid component file {path.name}: {error}") from error
                    if not isinstance(component, Component) or component.kind != kind:
                        raise ValueError(f"{path.name}: component kind/contract mismatch")
                    if not component.id or component.id in self.components[kind]:
                        raise ValueError(f"Duplicate or empty {kind} ID: {component.id}")
                    required = {
                        "model": "build",
                        "dataset": "open",
                        "partition": "location",
                        "aggregator": "aggregate",
                        "defense": "apply",
                        "optimizer": "build",
                        "loss": "build",
                        "metrics": "evaluate",
                    }.get(kind)
                    if required and required not in component.hooks:
                        raise ValueError(f"{component.id}: missing {required} hook")
                    if any(not callable(hook) for hook in component.hooks.values()):
                        raise ValueError(f"{component.id}: hooks must be callable")
                    self.components[kind][component.id] = component
                    self.sources[f"{kind}/{component.id}"] = digest

    def get(self, kind, identifier):
        try:
            return self.components[kind][identifier]
        except KeyError as error:
            raise ValueError(
                f"Unavailable {kind}: {identifier}; add its file or choose another"
            ) from error

    def parameters(self, kind, identifier, values):
        return validate_parameters(self.get(kind, identifier), values)

    def catalog(self):
        return {
            kind: [value.public() for value in entries.values()]
            for kind, entries in self.components.items()
        }
