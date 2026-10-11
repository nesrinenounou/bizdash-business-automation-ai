import base64
import io
import json
from pathlib import Path

import joblib
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image, ImageDraw
from torchvision import models, transforms

MODELS = Path(__file__).parent / "models" / "deployment"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
CLASSES = json.loads((MODELS / "classes.json").read_text())

# Same as the Kaggle eval_transform
eval_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])

# EfficientNet-B0 WITH its fine-tuned head (needed for Grad-CAM);
# the 1280 features for XGBoost are taken before the head.
net = models.efficientnet_b0(weights=None)
net.classifier[1] = nn.Linear(net.classifier[1].in_features, len(CLASSES))
net.load_state_dict(torch.load(MODELS / "efficientnet_b0_finetuned.pt", map_location=DEVICE))
net = net.to(DEVICE).eval()
xgb_model = joblib.load(MODELS / "xgb_model.pkl")

# Optional: YOLO (your best.pt) + SAM2 (auto-downloaded by ultralytics)
yolo = sam = None
try:
    from ultralytics import SAM, YOLO
    if (MODELS / "yolo_best.pt").exists():
        yolo = YOLO(str(MODELS / "yolo_best.pt"))
        sam = SAM("sam2.1_t.pt")
except Exception as e:  # keep the classifier working even if these fail
    print("YOLO/SAM2 disabled:", e)


def _b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _norm(name: str) -> str:  # 'rolled-in_scale' and 'Rolled' -> 'roll'
    return name.lower()[:4]


def _features_and_cam(x, class_idx=None):
    """1280 features + Grad-CAM of the CNN head for class_idx (None -> no CAM)."""
    with torch.enable_grad():
        fmap = net.features(x)
        fmap.retain_grad()
        feats = torch.flatten(net.avgpool(fmap), 1)
        if class_idx is None:
            return feats.detach().cpu().numpy(), None
        net.classifier(feats)[0, class_idx].backward()
        w = fmap.grad.mean((2, 3), keepdim=True)
        cam = F.relu((w * fmap).sum(1, keepdim=True))
        cam = F.interpolate(cam, size=(224, 224), mode="bilinear", align_corners=False)[0, 0]
        cam = (cam - cam.min()) / (cam.max() - cam.min() + 1e-8)
    return feats.detach().cpu().numpy(), cam.detach().cpu().numpy()


def _overlay_cam(image, cam):
    base = image.resize((224, 224)).convert("RGB")
    c = np.clip(cam, 0, 1)
    heat = np.stack([c, 1 - np.abs(2 * c - 1), 1 - c], -1) * 255
    return Image.blend(base, Image.fromarray(heat.astype(np.uint8)), 0.45).resize(image.size)


def _where(cam):
    ys, xs = np.where(cam > 0.5)
    if len(xs) == 0:
        return "no clear region", 0.0
    v = "top" if ys.mean() < 224 / 3 else "bottom" if ys.mean() > 448 / 3 else "middle"
    h = "left" if xs.mean() < 224 / 3 else "right" if xs.mean() > 448 / 3 else "center"
    return f"{v}-{h}", float(len(xs) / cam.size * 100)


def _segment(image):
    """YOLO boxes -> SAM2 masks. Returns (detections, overlay_png_b64) or (None, None)."""
    if yolo is None:
        return None, None
    r = yolo.predict(image, verbose=False)[0]
    if len(r.boxes) == 0:
        return [], None
    boxes = r.boxes.xyxy.cpu().numpy()
    masks = sam(image, bboxes=boxes.tolist(), verbose=False)[0].masks.data.cpu().numpy()
    out = image.convert("RGBA")
    dets = []
    palette = [(255, 60, 60), (60, 160, 255), (60, 220, 120), (255, 200, 60)]
    for i, (b, m) in enumerate(zip(boxes, masks)):
        col = palette[i % len(palette)]
        layer = Image.fromarray((m * 110).astype(np.uint8)).resize(image.size)
        out = Image.alpha_composite(out, Image.merge("RGBA", [Image.new("L", image.size, v) for v in col] + [layer]))
        ImageDraw.Draw(out).rectangle(list(map(float, b)), outline=col + (255,), width=2)
        dets.append({
            "label": r.names[int(r.boxes.cls[i])],
            "confidence": float(r.boxes.conf[i]),
            "box": [round(float(v), 1) for v in b],
            "mask_area_pct": round(float(m.mean() * 100), 2),
        })
    return dets, _b64(out.convert("RGB"))


def analyze_bytes(data: bytes) -> dict:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    x = eval_transform(image).unsqueeze(0).to(DEVICE)

    feats, _ = _features_and_cam(x)
    probs = xgb_model.predict_proba(feats)[0]
    idx = int(probs.argmax())
    top, second = np.argsort(probs)[::-1][:2]

    net.zero_grad()
    _, cam = _features_and_cam(x, idx)
    region, area = _where(cam)
    dets, seg_png = _segment(image)

    why = [
        f"XGBoost chose {CLASSES[idx]} with {probs[idx]*100:.1f}%; "
        f"runner-up is {CLASSES[second]} at {probs[second]*100:.1f}% "
        f"(margin {(probs[top]-probs[second])*100:.1f} points).",
        f"The CNN's attention (Grad-CAM) for this class is concentrated in the {region} area, "
        f"covering about {area:.0f}% of the image.",
    ]
    if probs[idx] < 0.6:
        why.append("Confidence is low: treat this prediction as uncertain.")
    agreement = None
    if dets:
        yolo_labels = {_norm(d["label"]) for d in dets}
        agreement = _norm(CLASSES[idx]) in yolo_labels
        why.append(
            "YOLO and the classifier agree on the defect type."
            if agreement else
            f"YOLO detected {', '.join(sorted({d['label'] for d in dets}))}, which disagrees "
            f"with the classifier: the result is unreliable."
        )
    elif dets is not None:
        why.append("YOLO found no defect box, so the localization does not support the classifier.")

    return {
        "prediction": CLASSES[idx],
        "confidence": float(probs[idx]),
        "probabilities": {c: float(p) for c, p in zip(CLASSES, probs)},
        "gradcam_png": _b64(_overlay_cam(image, cam)),
        "segmentation_png": seg_png,
        "detections": dets,
        "agreement": agreement,
        "explanation": why,
    }
