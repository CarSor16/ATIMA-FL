import numpy as np
from .numerics import check_arrays


def flatten(arrays):
    check_arrays(arrays)
    return np.concatenate([a.astype(np.float64).ravel() for a in arrays])


def restore(vector, reference):
    arrays, offset = [], 0
    for array in reference:
        arrays.append(vector[offset : offset + array.size].reshape(array.shape).astype(array.dtype))
        offset += array.size
    if offset != len(vector):
        raise ValueError("Wrong vector dimension")
    check_arrays(arrays, reference)
    return arrays


def krum_scores(matrix, bound):
    n = len(matrix)
    if n <= 2 * bound + 2 or bound < 0:
        raise ValueError("Krum requires n >= 2f+3")
    distances = np.sum((matrix[:, None, :] - matrix[None, :, :]) ** 2, axis=2)
    np.fill_diagonal(distances, np.inf)
    return np.sort(distances, axis=1)[:, : n - bound - 2].sum(axis=1)
