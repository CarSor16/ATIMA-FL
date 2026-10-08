# LopezCNN packet-header adapter

The `lopez_cnn` model follows the project's original `src/networks/lopez17cnn.py`
for ten packets with six ordered fields. The existing 60 input features are
reshaped to NCHW `(batch, 1, 10, 6)` without reordering or additional scaling.
Its two blocks use 32/64 channels, 4×2 convolutions, ReLU, 3×2 stride-one
max pooling and BatchNorm. Asymmetric zero padding preserves the 10×6 shape.
A 200-unit ReLU head produces class logits. The five-class model has 786,133
trainable parameters, compared with 6,149 for the default MLP.

BatchNorm uses fixed momentum 0.1 and epsilon 1e-5. Affine weights and running
means/variances follow the existing global weighted aggregation. The integer
`num_batches_tracked` counter is omitted from exchanged state: it is unused
by fixed-momentum normalization. This is not FedBN, local BatchNorm, or a
defense. The loader preserves PyTorch state-dict module version metadata so
loading does not trigger legacy counter insertion. A regression test checks
exact training/evaluation equality against standard fixed-momentum BatchNorm.

LabelFlip changes client training labels only. This comparison does not
establish compatibility of sign-flip or other update attacks with BatchNorm.
No negative-variance state should be accepted as a valid final result.

The MLP/CNN campaign keeps the prepared data, IID shards, seed, client count,
optimizer, local epochs, batch size, LabelFlip settings and CPU budget fixed.
It evaluates the four conditions separately: MLP clean/LabelFlip and CNN
clean/LabelFlip. For CNN, minimum rounds is set to the cap of 50 to match the
50 rounds actually completed by MLP. CNN LabelFlip follows its own completed
clean reference. Compare the attack effect within each architecture first,
then compare effect sizes and absolute clean performance across models.
Different initialization shapes, model capacity and BatchNorm prevent a
claim that architecture alone explains any difference. One seed remains
exploratory; distributed network overhead and non-IID behavior are not tested.
