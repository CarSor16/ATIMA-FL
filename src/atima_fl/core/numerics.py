from pathlib import Path
import hashlib
import math
import numpy as np


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def round_seed(seed, client, round_id):
    # Stable logical identity; independent of actor/PID/task scheduling.
    return int(np.random.SeedSequence([seed, client, round_id]).generate_state(1)[0] % (2**31 - 1))


class PlateauPolicy:
    def __init__(self, config):
        self.config = config
        self.best = -math.inf
        self.last_improved = 0
        self.coverage = []

    def step(self, round_id, macro_f1, recall):
        if not math.isfinite(macro_f1) or not np.isfinite(recall).all():
            raise ValueError("Numerically invalid validation; stop immediately")
        if macro_f1 > self.best + self.config.min_delta:
            self.best = macro_f1
            self.last_improved = round_id
        self.coverage = (self.coverage + [float(np.min(recall))])[-self.config.coverage_window :]
        return (
            round_id >= self.config.minimum_rounds
            and round_id - self.last_improved >= self.config.patience
            and len(self.coverage) == self.config.coverage_window
            and min(self.coverage) >= self.config.recall_floor
        )


def check_arrays(arrays, reference=None):
    if reference is not None and len(arrays) != len(reference):
        raise ValueError("Layer count changed")
    for index, array in enumerate(arrays):
        if not np.isfinite(array).all():
            raise ValueError("Nonfinite model/update")
        if reference is not None and (
            array.shape != reference[index].shape or array.dtype != reference[index].dtype
        ):
            raise ValueError("Shape/dtype changed")


def weighted_average(updates, counts):
    if not updates or len(updates) != len(counts) or any(n <= 0 for n in counts):
        raise ValueError("Complete positive sample counts required")
    for update in updates:
        check_arrays(update, updates[0])
    total = sum(counts)
    return [
        sum(
            a[index].astype(np.float64) * (count / total) for a, count in zip(updates, counts)
        ).astype(updates[0][index].dtype)
        for index in range(len(updates[0]))
    ]


def trajectory_metrics(attacked, clean, attacked_previous, clean_previous):
    def vector(arrays):
        check_arrays(arrays)
        return np.concatenate([a.astype(np.float64).ravel() for a in arrays])

    check_arrays(attacked, clean)
    check_arrays(attacked_previous, attacked)
    check_arrays(clean_previous, clean)
    a, c, ap, cp = map(vector, (attacked, clean, attacked_previous, clean_previous))
    da, dc = a - ap, c - cp
    norm_product = np.linalg.norm(da) * np.linalg.norm(dc)
    return {
        "weight_l2": float(np.linalg.norm(a - c)),
        "weight_l2_normalized": float(np.linalg.norm(a - c) / (np.linalg.norm(c) + 1e-12)),
        "global_update_l2": float(np.linalg.norm(da - dc)),
        "update_cosine": None if norm_product == 0 else float(np.dot(da, dc) / norm_product),
    }
