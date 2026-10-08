"""Lopez17CNN header adapter: ten packets, six ordered fields per packet.

Architecture follows the project's original src/networks/lopez17cnn.py at
10x6 input (same padding). BatchNorm uses fixed momentum=0.1. Its unused
integer batch counter is omitted; affine weights and running mean/variance
are federated. This avoids integer scalar updates in the floating delta
protocol without changing normalization. Inputs are not reordered.
"""

from atima_fl.core.contracts import Component


def validate(config, params):
    if config.input_dim != 60:
        raise ValueError("LopezCNN requires 10 packets × 6 fields (60 ordered features)")


def build(config, params, seed):
    import torch
    from torch import nn
    from torch.nn import functional as functional

    torch.manual_seed(seed)

    class LopezCNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(1, 32, (4, 2))
            self.bn1 = nn.BatchNorm2d(32)
            self.conv2 = nn.Conv2d(32, 64, (4, 2))
            self.bn2 = nn.BatchNorm2d(64)
            # The counter matters only for cumulative (momentum=None) averaging.
            # Fixed-momentum BatchNorm has identical train/eval behavior without it.
            self.bn1.num_batches_tracked = None
            self.bn2.num_batches_tracked = None
            self.fc1 = nn.Linear(10 * 6 * 64, 200)
            self.fc = nn.Linear(200, config.num_classes)

        def forward(self, inputs):
            values = inputs.reshape(-1, 1, 10, 6)
            values = functional.relu(self.conv1(functional.pad(values, (0, 1, 1, 2))))
            values = functional.max_pool2d(
                functional.pad(values, (0, 1, 1, 1)), (3, 2), stride=1
            )
            values = self.bn1(values)
            values = functional.relu(self.conv2(functional.pad(values, (0, 1, 1, 2))))
            values = functional.max_pool2d(
                functional.pad(values, (0, 1, 1, 1)), (3, 2), stride=1
            )
            values = self.bn2(values).flatten(start_dim=1)
            return self.fc(functional.relu(self.fc1(values)))

    return LopezCNN()


PLUGIN = Component(
    "lopez_cnn",
    "model",
    "LopezCNN · packet headers",
    "Two convolution/pooling/BatchNorm blocks and a 200-unit head; 10×6 packet fields.",
    {},
    {"validate": validate, "build": build},
    translations={
        "it": {
            "title": "LopezCNN · header dei pacchetti",
            "description": "Due blocchi convoluzione/pooling/BatchNorm e testa da 200 unità; 10×6 campi.",
        }
    },
)
