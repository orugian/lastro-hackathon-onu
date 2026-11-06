"""Converte os pesos da U-Net siamesa treinada no Colab (state_dict) para ONNX.

Executar num ambiente efêmero (não adiciona torch ao projeto):
  uv run --with torch --with segmentation-models-pytorch==0.5.0 --with onnx python scripts/export_unet_onnx.py
"""
from pathlib import Path

import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
PT = ROOT / "data/processed/dl/lastro_unet.pt"
OUT = ROOT / "data/processed/dl/lastro_unet.onnx"


class SiameseUNet(nn.Module):
    """Idêntica ao notebook: dois ramos de 6 bandas, ResNet34 compartilhada, fusão 1x1 por nível."""

    def __init__(self):
        super().__init__()
        import segmentation_models_pytorch as smp
        self.net = smp.Unet(encoder_name="resnet34", encoder_weights=None, in_channels=6, classes=1)
        self.fuse = nn.ModuleList([nn.Conv2d(2 * c, c, 1) for c in self.net.encoder.out_channels])

    def forward(self, x):
        a, b = self.net.encoder(x[:, :6]), self.net.encoder(x[:, 6:])
        fused = [layer(torch.cat([p, q], 1)) for layer, p, q in zip(self.fuse, a, b)]
        return self.net.segmentation_head(self.net.decoder(fused))[:, 0]


def main():
    model = SiameseUNet()
    state = torch.load(PT, map_location="cpu", weights_only=True)
    missing, unexpected = model.load_state_dict(state, strict=True), None
    model.eval()
    x = torch.randn(1, 12, 224, 224)
    with torch.no_grad():
        ref = model(x).numpy()
    torch.onnx.export(model, x, OUT, input_names=["x"], output_names=["logits"],
                      dynamic_axes={"x": {0: "b", 2: "h", 3: "w"}, "logits": {0: "b", 1: "h", 2: "w"}}, opset_version=17, dynamo=False)
    import onnxruntime as ort
    out = ort.InferenceSession(str(OUT), providers=["CPUExecutionProvider"]).run(None, {"x": x.numpy()})[0]
    print("onnx ok", OUT.stat().st_size // 2**20, "MB; max |diff| =", float(np.abs(out - ref).max()))


if __name__ == "__main__":
    main()
