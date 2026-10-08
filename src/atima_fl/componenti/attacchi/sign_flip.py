from atima_fl.core.contracts import Component


def transform(context):
    strength = context.config.parameters("attack")["strength"]
    return (
        [
            g - strength * (local - g)
            for g, local in zip(context.global_arrays, context.local_arrays)
        ],
        {
            "attack_applied": True,
            "strength": strength,
            "definition": "delta_sent=-strength*delta_local",
        },
    )


PLUGIN = Component(
    "sign_flip",
    "attack",
    "Delta sign flip",
    "Reverses the local delta direction with a declared strength.",
    {"strength": {"type": "number", "default": 1.0, "minimum": 0.000001}},
    {"transform": transform},
    references=("https://arxiv.org/abs/2502.03801",),
    threats=("byzantine_update",),
    translations={
        "it": {
            "title": "Inversione del delta",
            "description": "Inverte la direzione del delta locale, con intensità dichiarata.",
        }
    },
)
