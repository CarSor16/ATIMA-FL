from atima_fl.core.contracts import Component


def transform(context):
    factor = context.config.parameters("attack")["factor"]
    return (
        [g + factor * (local - g) for g, local in zip(context.global_arrays, context.local_arrays)],
        {
            "attack_applied": factor != 1,
            "factor": factor,
            "definition": "delta_sent=factor*delta_local",
            "objective": "amplitude manipulation; performance degradation is not guaranteed",
        },
    )


PLUGIN = Component(
    "update_scaling",
    "attack",
    "Delta scaling",
    "Changes delta magnitude without a trigger or sign reversal. Mechanistic control.",
    {"factor": {"type": "number", "default": 5.0, "minimum": 1}},
    {"transform": transform},
    references=("https://arxiv.org/abs/2502.03801",),
    threats=("large_norm", "byzantine_update"),
    translations={
        "it": {
            "title": "Amplificazione del delta",
            "description": "Modifica solo l’ampiezza del delta, senza trigger e senza invertirne il segno. Controllo meccanistico.",
        }
    },
)
