"""Flower messages adapted to the independent client training engine."""

import json
from pathlib import Path
import torch
from flwr.app import ArrayRecord, ConfigRecord, Context, Message, MetricRecord, RecordDict
from flwr.clientapp import ClientApp
from atima_fl.core.configuration import ExperimentConfig
from atima_fl.engine.client import train_local, submit_local
from atima_fl.engine.data import open_dataset

app = ClientApp()


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
        values, metadata = train_local(
            config, run, client, round_id, before, open_dataset(config), config.compute_device
        )
    elif command["phase"] == "submit":
        counts = {int(k): int(v) for k, v in json.loads(command["counts_json"]).items()}
        values, metadata = submit_local(config, run, client, round_id, before, counts)
    else:
        raise ValueError("Unknown protocol phase")
    return Message(
        content=RecordDict(
            {
                "arrays": ArrayRecord(numpy_ndarrays=values),
                "metrics": MetricRecord(
                    {"client-id": client, "num-examples": metadata["original_samples"]}
                ),
                "audit": ConfigRecord({"metadata_json": json.dumps(metadata, allow_nan=False)}),
            }
        ),
        reply_to=message,
    )
