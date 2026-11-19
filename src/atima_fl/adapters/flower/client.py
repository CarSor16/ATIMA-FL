"""Flower messages adapted to the independent client training engine."""

import json
from pathlib import Path
import torch
from flwr.app import ArrayRecord, ConfigRecord, Context, Message, MetricRecord, RecordDict
from flwr.clientapp import ClientApp
from atima_fl.core.configuration import ExperimentConfig
from atima_fl.engine.client import train_local, submit_local
from atima_fl.engine.attacks import reported_samples
from atima_fl.engine import data as data_engine

app = ClientApp()
_PRIVATE_ARRAYS = "hyperfl_private_arrays"
_PRIVATE_KEYS = "hyperfl_private_keys"


def _load_private_state(context):
    if _PRIVATE_ARRAYS not in context.state or _PRIVATE_KEYS not in context.state:
        return None
    keys = json.loads(context.state[_PRIVATE_KEYS]["keys_json"])
    values = context.state[_PRIVATE_ARRAYS].to_numpy_ndarrays()
    if len(keys) != len(values) or len(set(keys)) != len(keys):
        raise ValueError("Invalid client-private HyperFL++ state")
    return dict(zip(keys, values))


def _save_private_state(context, values):
    keys = sorted(values)
    context.state[_PRIVATE_ARRAYS] = ArrayRecord(
        numpy_ndarrays=[values[key] for key in keys]
    )
    context.state[_PRIVATE_KEYS] = ConfigRecord({"keys_json": json.dumps(keys)})


@app.train()
def handle_train(message: Message, context: Context):
    command = message.content["config"]
    config = ExperimentConfig.from_dict(json.loads(command["config_json"]))
    client = int(context.node_config["partition-id"])
    round_id = int(command["server-round"])
    run = Path(command["run_dir"])
    before = message.content["arrays"].to_numpy_ndarrays()
    if command["phase"] == "train":
        if config.compute_device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("ClientApp has no CUDA device; CPU fallback is forbidden")
        torch.set_num_threads(config.client_cpus)
        private = _load_private_state(context) if config.training_method == "hyperfl_plus_plus" else None
        values, metadata = train_local(
            config,
            run,
            client,
            round_id,
            before,
            data_engine.open_dataset(config),
            config.compute_device,
            client_state=private,
        )
        if config.training_method == "hyperfl_plus_plus":
            _save_private_state(context, private)
    elif command["phase"] == "submit":
        counts = {int(k): int(v) for k, v in json.loads(command["counts_json"]).items()}
        private = _load_private_state(context) if config.training_method == "hyperfl_plus_plus" else None
        values, metadata = submit_local(
            config, run, client, round_id, before, counts, client_state=private
        )
    elif command["phase"] in {"validate", "test"}:
        if config.training_method != "hyperfl_plus_plus":
            raise ValueError("Client-side personalized evaluation is only used by HyperFL++")
        from atima_fl.engine.hyperfl import evaluate_local

        private = _load_private_state(context)
        dataset = data_engine.open_dataset(config)
        result, metadata = evaluate_local(
            config,
            client,
            round_id,
            before,
            dataset,
            config.compute_device,
            private,
            command["phase"],
        )
        values = before
        metadata["original_samples"] = len(dataset.shard(client).y)
        metadata["training_method"] = config.training_method
    else:
        raise ValueError("Unknown protocol phase")

    if command["phase"] in {"validate", "test"}:
        count = int(metadata["original_samples"])
    else:
        count, count_audit = reported_samples(
            config, client, round_id, metadata["original_samples"]
        )
        metadata.update(count_audit)
        metadata["attack_applied"] = metadata.get("attack_applied", False) or count_audit["count_spoofed"]
    return Message(
        content=RecordDict(
            {
                "arrays": ArrayRecord(numpy_ndarrays=values),
                "metrics": MetricRecord({"client-id": client, "num-examples": count}),
                "audit": ConfigRecord({"metadata_json": json.dumps(metadata, allow_nan=False)}),
            }
        ),
        reply_to=message,
    )
