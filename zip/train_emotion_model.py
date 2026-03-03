"""
Train Emotion Detection CNN on FER-2013  (PyTorch + GPU)
=========================================================
Architecture : Pretrained ResNet-18 fine-tuned for emotion classification
Key tricks   : CLAHE preprocessing (matches inference pipeline),
               label smoothing, strong augmentation, cosine annealing,
               test-time augmentation during evaluation,
               differential learning rates for pretrained vs new layers
Dataset      : FER-2013 (28 709 train, 3 589 val, 3 589 test)
Output       : models/emotion_model_best.pth

Run:
    python train_emotion_model.py
"""

import os, sys, json, datetime, math, random

import numpy as np
import cv2

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import torchvision.models as models

# ====================================================================
#  CONFIG
# ====================================================================
IMG_SIZE         = 48
NUM_CLASSES      = 7
BATCH_SIZE       = 128
EPOCHS           = 80
PATIENCE         = 25
INITIAL_LR       = 0.0005
LABEL_SMOOTHING  = 0.05
WEIGHT_DECAY     = 1e-4
NUM_WORKERS      = 0            # Single-process (fastest on Windows)
MODEL_DIR        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
BEST_MODEL_PATH  = os.path.join(MODEL_DIR, "emotion_model_best.pth")
FINAL_MODEL_PATH = os.path.join(MODEL_DIR, "emotion_model.pth")
HISTORY_PATH     = os.path.join(MODEL_DIR, "training_history.json")

EMOTION_LABELS   = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]
HF_DATASET       = "Aaryan333/fer2013_train_publicTest_privateTest"


# ====================================================================
#  DATA LOADING  (with CLAHE -- matches inference pipeline exactly)
# ====================================================================
def load_fer2013():
    """Load FER-2013 from HuggingFace.  Apply CLAHE + normalise to [0,1]."""
    from datasets import load_dataset
    print("[INFO] Loading FER-2013 dataset ...")
    ds = load_dataset(HF_DATASET)

    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))

    def to_arrays(split):
        images, labels_list = [], []
        for s in split:
            img = s["image"].convert("L")
            img_np = np.array(img, dtype=np.uint8)
            if img_np.shape != (IMG_SIZE, IMG_SIZE):
                img_np = cv2.resize(img_np, (IMG_SIZE, IMG_SIZE),
                                    interpolation=cv2.INTER_AREA)
            img_np = clahe.apply(img_np)
            images.append(img_np.astype(np.float32) / 255.0)
            labels_list.append(s["label"])
        return np.stack(images)[..., np.newaxis], np.array(labels_list, dtype=np.int64)

    X_train, y_train = to_arrays(ds["train"])
    X_val,   y_val   = to_arrays(ds["publicTest"])
    X_test,  y_test  = to_arrays(ds["privateTest"])

    print(f"   Train : {X_train.shape[0]:>6,}  |  Val : {X_val.shape[0]:>5,}  "
          f"|  Test : {X_test.shape[0]:>5,}")
    return (X_train, y_train), (X_val, y_val), (X_test, y_test)


# ====================================================================
#  PYTORCH DATASET WITH AUGMENTATION
# ====================================================================
class FERDataset(Dataset):
    """FER-2013 Dataset with optional augmentation."""

    def __init__(self, images, labels, augment=False):
        # Pre-replicate to 3 channels and pre-transpose to CHW for speed
        # images: (N, 48, 48, 1) -> (N, 3, 48, 48)
        imgs_chw = np.transpose(images, (0, 3, 1, 2))  # (N, 1, 48, 48)
        self.images_3ch = np.repeat(imgs_chw, 3, axis=1).astype(np.float32)  # (N, 3, 48, 48)
        self.images_raw = images  # Keep raw for augmentation
        self.labels = labels
        self.augment = augment

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        label = self.labels[idx]

        if self.augment:
            img = self.images_raw[idx].copy()  # (48, 48, 1)
            img = self._augment(img)
            img = np.transpose(img, (2, 0, 1))  # (1, 48, 48)
            img = np.repeat(img, 3, axis=0)      # (3, 48, 48)
            return torch.from_numpy(img), torch.tensor(label, dtype=torch.long)
        else:
            # Use pre-computed 3-channel CHW image (fast path)
            return torch.from_numpy(self.images_3ch[idx].copy()), torch.tensor(label, dtype=torch.long)

    def _augment(self, img):
        """Strong augmentation."""
        # Random horizontal flip
        if random.random() > 0.5:
            img = img[:, ::-1, :].copy()

        # Random brightness
        delta = random.uniform(-0.15, 0.15)
        img = img + delta

        # Random contrast
        factor = random.uniform(0.80, 1.20)
        mean = img.mean()
        img = (img - mean) * factor + mean

        # Random shift (up to +-4 pixels)
        dx = random.randint(-4, 4)
        dy = random.randint(-4, 4)
        img = np.roll(np.roll(img, dx, axis=1), dy, axis=0)

        # Random zoom (crop and resize back)
        if random.random() > 0.5:
            crop_frac = random.uniform(0.85, 1.0)
            crop_size = max(36, int(IMG_SIZE * crop_frac))
            max_offset = IMG_SIZE - crop_size
            if max_offset > 0:
                oh = random.randint(0, max_offset)
                ow = random.randint(0, max_offset)
                cropped = img[oh:oh+crop_size, ow:ow+crop_size, :]
                cropped_2d = cropped[:, :, 0]
                resized = cv2.resize(cropped_2d, (IMG_SIZE, IMG_SIZE),
                                     interpolation=cv2.INTER_LINEAR)
                img = resized[..., np.newaxis]

        # Random erasing / cutout
        if random.random() > 0.5:
            erase_h = random.randint(6, 14)
            erase_w = random.randint(6, 14)
            top = random.randint(0, IMG_SIZE - erase_h)
            left = random.randint(0, IMG_SIZE - erase_w)
            mean_val = img.mean()
            img[top:top+erase_h, left:left+erase_w, :] = mean_val

        img = np.clip(img, 0.0, 1.0)
        return img


# ====================================================================
#  MODEL -- Pretrained ResNet-18 adapted for 48x48 grayscale
# ====================================================================
class EmotionResNet(nn.Module):
    """
    ResNet-18 adapted for 48x48 face emotion classification.
    - First conv changed to 3x3 stride 1 (48x48 is too small for 7x7 stride 2)
    - Initial maxpool removed (preserve spatial resolution)
    - Final FC replaced for 7 emotion classes
    - Pretrained ImageNet weights kept for layers 1-4
    """

    def __init__(self, num_classes=7, pretrained=True):
        super().__init__()

        if pretrained:
            resnet = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
        else:
            resnet = models.resnet18(weights=None)

        # Replace first conv: 7x7 stride 2 -> 3x3 stride 1
        self.conv1 = nn.Conv2d(3, 64, kernel_size=3, stride=1, padding=1, bias=False)
        if pretrained:
            with torch.no_grad():
                pretrained_weight = resnet.conv1.weight.data
                self.conv1.weight.copy_(pretrained_weight[:, :, 2:5, 2:5])

        self.bn1 = resnet.bn1
        self.relu = resnet.relu

        self.layer1 = resnet.layer1   # 64 ch
        self.layer2 = resnet.layer2   # 128 ch
        self.layer3 = resnet.layer3   # 256 ch
        self.layer4 = resnet.layer4   # 512 ch

        self.avgpool = nn.AdaptiveAvgPool2d(1)
        self.dropout = nn.Dropout(0.3)

        self.fc = nn.Linear(512, num_classes)
        nn.init.xavier_uniform_(self.fc.weight)
        nn.init.constant_(self.fc.bias, 0)

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        x = self.avgpool(x)
        x = x.view(x.size(0), -1)
        x = self.dropout(x)
        x = self.fc(x)
        return x


# ====================================================================
#  TRAINING
# ====================================================================
def train():
    os.makedirs(MODEL_DIR, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[INFO] Using device: {device}")
    if device.type == "cuda":
        print(f"   GPU: {torch.cuda.get_device_name(0)}")
        print(f"   VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

    # 1. Load data
    (X_train, y_train), (X_val, y_val), (X_test, y_test) = load_fer2013()

    # 2. Class weights
    from sklearn.utils.class_weight import compute_class_weight
    cw_raw = compute_class_weight("balanced",
                                  classes=np.arange(NUM_CLASSES), y=y_train)
    class_weights = torch.tensor(
        [min(float(w), 2.5) for w in cw_raw], dtype=torch.float32
    ).to(device)

    print("\n[INFO] Class weights (capped at 2.5):")
    for i, emo in enumerate(EMOTION_LABELS):
        cnt = int(np.sum(y_train == i))
        print(f"   {emo:>10s} : {class_weights[i]:.3f}  ({cnt:>5,} samples)")

    # 3. Datasets & DataLoaders
    train_dataset = FERDataset(X_train, y_train, augment=True)
    val_dataset = FERDataset(X_val, y_val, augment=False)
    test_dataset = FERDataset(X_test, y_test, augment=False)

    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True,
                              num_workers=NUM_WORKERS, drop_last=True)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False,
                            num_workers=NUM_WORKERS)
    test_loader = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False,
                             num_workers=NUM_WORKERS)

    # 4. Build model
    model = EmotionResNet(num_classes=NUM_CLASSES, pretrained=True).to(device)
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"\n[INFO] Model: EmotionResNet (ResNet-18 pretrained)")
    print(f"   Total params     : {total_params:>10,}")
    print(f"   Trainable params : {trainable_params:>10,}")

    # 5. Loss, optimizer with differential LR, scheduler
    criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=LABEL_SMOOTHING)

    # Differential learning rates
    pretrained_params = []
    new_params = []
    for name, param in model.named_parameters():
        if name.startswith('fc.') or name.startswith('dropout.') or name.startswith('conv1.'):
            new_params.append(param)
        else:
            pretrained_params.append(param)

    optimizer = torch.optim.AdamW([
        {'params': pretrained_params, 'lr': INITIAL_LR * 0.1},
        {'params': new_params, 'lr': INITIAL_LR},
    ], weight_decay=WEIGHT_DECAY)

    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=EPOCHS, eta_min=1e-6
    )

    # 6. Training loop
    print(f"\n[START] Training -- {EPOCHS} epochs, batch {BATCH_SIZE}")
    print(f"   Pretrained LR : {INITIAL_LR * 0.1:.6f}")
    print(f"   New layers LR : {INITIAL_LR:.6f}")
    print(f"   Weight decay  : {WEIGHT_DECAY}")
    print(f"   Label smooth  : {LABEL_SMOOTHING}")
    print(f"   Best model    -> {BEST_MODEL_PATH}")
    start = datetime.datetime.now()

    best_val_acc = 0.0
    patience_counter = 0
    start_epoch = 1
    history = {"train_loss": [], "train_acc": [], "val_loss": [], "val_acc": [], "lr": []}

    # Resume from checkpoint if available
    if os.path.exists(BEST_MODEL_PATH):
        try:
            ckpt = torch.load(BEST_MODEL_PATH, map_location=device, weights_only=False)
            if 'model_state_dict' in ckpt and ckpt.get('model_type') == 'EmotionResNet':
                model.load_state_dict(ckpt['model_state_dict'])
                start_epoch = ckpt.get('epoch', 0) + 1
                best_val_acc = ckpt.get('val_acc', 0.0)
                if 'optimizer_state_dict' in ckpt:
                    optimizer.load_state_dict(ckpt['optimizer_state_dict'])
                if 'scheduler_state_dict' in ckpt:
                    scheduler.load_state_dict(ckpt['scheduler_state_dict'])
                else:
                    for _ in range(start_epoch - 1):
                        scheduler.step()
                print(f"\n[RESUME] Loaded checkpoint from epoch {start_epoch-1} "
                      f"(val_acc={best_val_acc:.4f})")
        except Exception as e:
            print(f"[WARN] Could not resume: {e} -- training from scratch")

    num_batches = len(train_loader)

    for epoch in range(start_epoch, EPOCHS + 1):
        # ── Train ──
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0
        epoch_start = datetime.datetime.now()

        for batch_idx, (images, labels) in enumerate(train_loader):
            images, labels = images.to(device, non_blocking=True), labels.to(device, non_blocking=True)

            optimizer.zero_grad(set_to_none=True)
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            running_loss += loss.item() * images.size(0)
            _, predicted = outputs.max(1)
            total += labels.size(0)
            correct += predicted.eq(labels).sum().item()

            pass  # no per-batch output (I/O overhead)

        scheduler.step()

        train_loss = running_loss / total
        train_acc = correct / total
        epoch_time = (datetime.datetime.now() - epoch_start).total_seconds()

        # ── Validate ──
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device, non_blocking=True), labels.to(device, non_blocking=True)
                outputs = model(images)
                loss = criterion(outputs, labels)
                val_loss += loss.item() * images.size(0)
                _, predicted = outputs.max(1)
                val_total += labels.size(0)
                val_correct += predicted.eq(labels).sum().item()

        val_loss /= val_total
        val_acc = val_correct / val_total
        current_lr = optimizer.param_groups[1]['lr']

        history["train_loss"].append(train_loss)
        history["train_acc"].append(train_acc)
        history["val_loss"].append(val_loss)
        history["val_acc"].append(val_acc)
        history["lr"].append(current_lr)

        improved = ""
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            patience_counter = 0
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'scheduler_state_dict': scheduler.state_dict(),
                'val_acc': val_acc,
                'val_loss': val_loss,
                'model_type': 'EmotionResNet',
            }, BEST_MODEL_PATH)
            improved = " *** SAVED ***"
        else:
            patience_counter += 1

        print(f"Epoch {epoch:3d}/{EPOCHS}  |  "
              f"train_loss: {train_loss:.4f}  train_acc: {train_acc:.4f}  |  "
              f"val_loss: {val_loss:.4f}  val_acc: {val_acc:.4f}  |  "
              f"lr: {current_lr:.6f}  [{epoch_time:.0f}s]{improved}",
              flush=True)

        # Write progress to file for monitoring
        with open(os.path.join(MODEL_DIR, "progress.txt"), "w") as pf:
            pf.write(f"epoch={epoch}/{EPOCHS} val_acc={val_acc:.4f} best={best_val_acc:.4f} time={epoch_time:.0f}s\n")

        if patience_counter >= PATIENCE:
            print(f"\n[EARLY STOP] No improvement for {PATIENCE} epochs. Stopping.")
            break

    elapsed = datetime.datetime.now() - start
    print(f"\n[DONE] Training completed in {elapsed}")
    print(f"   Best val accuracy: {best_val_acc:.4f} ({best_val_acc:.1%})")

    # 7. Load best model
    checkpoint = torch.load(BEST_MODEL_PATH, map_location=device, weights_only=True)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()

    # 8. Evaluate on test set
    print("\n[EVAL] Test set evaluation ...")
    test_correct = 0
    test_total = 0
    all_preds = []
    all_labels = []

    with torch.no_grad():
        for images, labels in test_loader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            _, predicted = outputs.max(1)
            test_total += labels.size(0)
            test_correct += predicted.eq(labels).sum().item()
            all_preds.extend(predicted.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())

    test_acc = test_correct / test_total
    print(f"   Test accuracy : {test_acc:.4f}  ({test_acc:.1%})")

    # TTA
    print("\n[EVAL] Test set with TTA (horizontal flip) ...")
    tta_preds_list = []

    with torch.no_grad():
        for images, labels in test_loader:
            images = images.to(device)
            out_orig = F.softmax(model(images), dim=1)
            out_flip = F.softmax(model(torch.flip(images, dims=[3])), dim=1)
            out_avg = (out_orig + out_flip) / 2.0
            tta_preds_list.append(out_avg.argmax(dim=1).cpu().numpy())

    tta_preds = np.concatenate(tta_preds_list)
    all_labels_arr = np.array(all_labels)
    tta_acc = (tta_preds == all_labels_arr).mean()
    print(f"   TTA accuracy  : {tta_acc:.4f}  ({tta_acc:.1%})")

    # Per-class accuracy
    print("\n   Per-class accuracy (with TTA):")
    for i, emo in enumerate(EMOTION_LABELS):
        mask = all_labels_arr == i
        if mask.sum() > 0:
            acc = (tta_preds[mask] == i).mean()
            print(f"      {emo:>10s} : {acc:.1%}  ({mask.sum()} samples)")

    # 9. Save final model
    torch.save(model.state_dict(), FINAL_MODEL_PATH)
    print(f"\n[SAVE] Final model -> {FINAL_MODEL_PATH}")

    history["test_accuracy"] = float(test_acc)
    history["tta_accuracy"] = float(tta_acc)
    history["training_time"] = str(elapsed)
    history["best_val_accuracy"] = float(best_val_acc)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)
    print(f"[SAVE] History -> {HISTORY_PATH}")

    print("\nTRAINING COMPLETE")
    return model


# ====================================================================
if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

    print("=" * 60)
    print("  EmoRecs -- Emotion CNN Training (PyTorch + GPU)")
    print("  Architecture: ResNet-18 (pretrained on ImageNet)")
    print("=" * 60)
    print()
    train()
    print("\n[OK] Done! The trained model is ready for use in the app.")
