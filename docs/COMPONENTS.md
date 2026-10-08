# Component contract

Each category folder contains independent Python files exporting `PLUGIN`.
Discovery loads metadata without importing Flower/PyTorch. Heavy dependencies
belong inside execution hooks. External plugins are trusted executable code.

```python
# plugins/aggregatori/example.py
from atima_fl.core.contracts import Component

def aggregate(matrix, counts, params):
    return matrix.mean(axis=0), {"weighting": "uniform"}

PLUGIN = Component(
    "example_mean", "aggregator", "Example mean", "Uniform coordinate mean",
    hooks={"aggregate": aggregate},
)
```

Run `atima ui --plugins plugins`. The file appears automatically; removing it
causes configurations selecting it to fail. IDs are unique within each category.
No central list changes. Parameter schemas support integer, number, boolean,
string, array, object; defaults, bounds, choices and array item schemas.

| Kind / folder | Required hook | Contract |
|---|---|---|
| attack / attacchi | optional prepare/transform | `prepare(x,y,context) -> TrainingBatch`; `transform(context) -> (arrays,audit)` |
| model / modelli | build | `build(config,params,seed) -> torch.nn.Module`; named parameters define attack scope |
| aggregator / aggregatori | aggregate | `(matrix,counts,params) -> (vector,audit)`; flattened float64 deltas |
| defense / difese | apply | `(matrix,params) -> (same_shape_matrix,audit)`; no malicious identity oracle |
| dataset / dati | open | `(config,params) -> object` with `shard(id)`, `split(name)`, `audit()`, `classes` |
| partition / partizioni | location | `(root,config,params) -> prepared partition path` |
| optimizer / ottimizzatori | build | `(model.parameters(),config,params) -> optimizer`; recreated each fit |
| loss / perdite | build | `(config,params) -> criterion` |
| metrics / metriche | evaluate | `(y,probabilities,classes,params) -> finite JSON metrics` |

Optional `validate(config,params)` checks component-specific invariants.
Attack `knowledge(context)` declares accessible logical client IDs;
`evaluate(weights,x,y,config,device)` supports final ASR-style metrics;
`warnings(config,params)` exposes scientific caveats in the GUI.

Attack transforms see trainable tensors only; unselected buffers retain local
values. Hooks must preserve shape/dtype, avoid modifying caller inputs and return
finite values. Data poisoning records altered label/input indices and added
samples. Client IDs, seeds and round IDs are logical identities, independent of
actor scheduling. Source file hashes protect paired comparisons.

The configuration knows protocol categories, not installed component names.
The engine remains responsible for round orchestration, numerical guards,
sample-count integrity and persistence. Changing those contracts requires an ABI
change and tests; not every possible algorithm fits an existing hook unchanged.
