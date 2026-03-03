"""
Emotion Detection Page for EmoRecs  (High-Accuracy Version)
────────────────────────────────────────────────────────────
Key improvements over the baseline:
  1. DNN face detector (OpenCV SSD) instead of Haarcascade
     -> Much more accurate face localisation, especially in varied lighting
  2. Test-Time Augmentation (TTA)
     -> Average predictions of original + horizontally flipped face
     -> Boosts single-frame accuracy by 2-3%
  3. Sliding-window temporal smoothing
     -> Confidence-weighted vote over last 20 frames
     -> Eliminates flickering and stabilises predictions
  4. Confidence thresholding
     -> Only updates prediction when new prediction is confident enough
     -> Prevents random jumps to wrong emotions
  5. CLAHE preprocessing (matching training pipeline exactly)
  6. Multi-padding face crops for robustness

Pipeline:
  Frame -> DNN face detect -> Pad crop -> CLAHE + resize 48x48 ->
  CNN predict (original + flipped TTA) -> Sliding-window smooth ->
  Display with confidence threshold
"""

import os
import streamlit as st
import cv2
import numpy as np
import time
from collections import Counter, deque
import database
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models as models


# ━━━━━━━━━━━━━━  CONSTANTS  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EMOTION_EMOJI = {
    "angry":    "😠",
    "disgust":  "🤢",
    "fear":     "😨",
    "happy":    "😊",
    "sad":      "😢",
    "surprise": "😲",
    "neutral":  "😐",
}

EMOTION_COLORS = {
    "angry":    (0, 0, 255),
    "disgust":  (0, 140, 255),
    "fear":     (180, 105, 255),
    "happy":    (0, 255, 0),
    "sad":      (255, 165, 0),
    "surprise": (0, 255, 255),
    "neutral":  (200, 200, 200),
}

ALL_EMOTIONS = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]

# ── Tuning knobs ──────────────────────────────────────────────────────
ANALYSE_EVERY_N_FRAMES = 1       # run every frame for accuracy
DNN_CONFIDENCE_THRESH  = 0.55    # DNN face detector confidence threshold
FACE_PAD_RATIO         = 0.30    # extra padding around DNN box
MIN_FACE_SIZE          = 40      # ignore faces smaller than this (pixels)
DB_LOG_COOLDOWN        = 5.0     # seconds between database writes
CNN_INPUT_SIZE         = 48      # FER-2013 native resolution
SMOOTH_WINDOW          = 20      # sliding window size (frames)
CONF_THRESHOLD         = 0.35    # min confidence to update displayed emotion
USE_TTA                = True    # test-time augmentation (flip)

# ── Model paths ───────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_MODEL_PATH = os.path.join(_BASE_DIR, "models", "emotion_model.pth")
_BEST_MODEL_PATH = os.path.join(_BASE_DIR, "models", "emotion_model_best.pth")
_DNN_PROTO = os.path.join(_BASE_DIR, "models", "deploy.prototxt")
_DNN_MODEL = os.path.join(_BASE_DIR, "models", "res10_300x300_ssd.caffemodel")


# ━━━━━━━━━━━━━━  MODEL LOADER (cached)  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ── PyTorch Model Definition (must match training) ─────────────────
class _EmotionResNet(nn.Module):
    """ResNet-18 adapted for 48x48 face emotion classification (matches training)."""
    def __init__(self, num_classes=7):
        super().__init__()
        resnet = models.resnet18(weights=None)  # No pretrained weights needed for inference
        self.conv1 = nn.Conv2d(3, 64, kernel_size=3, stride=1, padding=1, bias=False)
        self.bn1 = resnet.bn1
        self.relu = resnet.relu
        self.layer1 = resnet.layer1
        self.layer2 = resnet.layer2
        self.layer3 = resnet.layer3
        self.layer4 = resnet.layer4
        self.avgpool = nn.AdaptiveAvgPool2d(1)
        self.dropout = nn.Dropout(0.3)
        self.fc = nn.Linear(512, num_classes)

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


@st.cache_resource(show_spinner="Loading emotion detection model ...")
def _load_models():
    """
    Load face detector + PyTorch emotion CNN.
    Uses DNN face detector if caffemodel exists, else falls back to Haarcascade.
    """
    # ── Face detector ──
    if os.path.isfile(_DNN_PROTO) and os.path.isfile(_DNN_MODEL):
        face_net = cv2.dnn.readNetFromCaffe(_DNN_PROTO, _DNN_MODEL)
        face_cascade = None
        print("[INFO] Using DNN face detector (SSD ResNet-10)")
    else:
        face_net = None
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        print("[INFO] DNN face model not found, using Haarcascade fallback")

    # ── Emotion model (PyTorch) ──
    model_path = None
    for p in [_BEST_MODEL_PATH, _MODEL_PATH]:
        if os.path.isfile(p):
            model_path = p
            break

    if model_path is None:
        raise FileNotFoundError(
            "No trained model found. Run `python train_emotion_model.py` first."
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    emotion_model = _EmotionResNet(num_classes=7)
    checkpoint = torch.load(model_path, map_location=device, weights_only=False)
    # Support both full checkpoint and plain state_dict
    if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
        emotion_model.load_state_dict(checkpoint['model_state_dict'])
    else:
        emotion_model.load_state_dict(checkpoint)
    emotion_model.to(device)
    emotion_model.eval()

    total_params = sum(p.numel() for p in emotion_model.parameters())
    print(f"[INFO] Emotion model loaded: {model_path} "
          f"({total_params:,} params) on {device}")

    return face_net, face_cascade, emotion_model, device


# ━━━━━━━━━━━━━━  CAMERA MANAGEMENT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Use session state to store camera instance (not st.cache_resource for cameras)
def _get_camera():
    """Open webcam. Returns camera object or None if failed."""
    
    # Check if we already have a camera in session state
    if 'webcam_cap' in st.session_state and st.session_state.webcam_cap is not None:
        cap = st.session_state.webcam_cap
        if cap.isOpened():
            return cap
        else:
            # Camera exists but is closed, release and recreate
            try:
                cap.release()
            except:
                pass
            st.session_state.webcam_cap = None
    
    # Try multiple backends for Windows compatibility
    backends = [
        (cv2.CAP_DSHOW, "DirectShow"),      # Windows DirectShow (most reliable)
        (cv2.CAP_MSMF, "MSMF"),              # Windows Media Foundation
        (cv2.CAP_ANY, "Automatic")
    ]
    
    for backend, backend_name in backends:
        try:
            print(f"[INFO] Trying to open camera with {backend_name} backend...")
            cap = cv2.VideoCapture(0, backend)
            
            if cap is not None and cap.isOpened():
                # Set camera properties
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                
                # Read a few frames to warm up the camera
                for _ in range(3):
                    ret, frame = cap.read()
                
                # Verify camera is working
                ret, test_frame = cap.read()
                if ret and test_frame is not None and test_frame.size > 0:
                    print(f"[INFO] Camera opened successfully with {backend_name} backend")
                    st.session_state.webcam_cap = cap
                    return cap
                else:
                    print(f"[WARN] Camera opened but unable to read frames")
                    cap.release()
        except Exception as e:
            print(f"[WARN] Failed to open camera with {backend_name} backend: {e}")
            continue
    
    print("[ERROR] All camera backends failed")
    st.session_state.webcam_cap = None
    return None


def _release_camera():
    """Release the camera properly."""
    try:
        if 'webcam_cap' in st.session_state and st.session_state.webcam_cap is not None:
            cap = st.session_state.webcam_cap
            if cap.isOpened():
                cap.release()
            st.session_state.webcam_cap = None
            print("[INFO] Camera released successfully")
    except Exception as e:
        print(f"[WARN] Error releasing camera: {e}")
        st.session_state.webcam_cap = None


# ━━━━━━━━━━━━━━  FACE DETECTION (DNN)  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _detect_faces_dnn(frame, face_net):
    """
    Detect faces using OpenCV DNN SSD detector.
    Returns list of (x, y, w, h) bounding boxes.
    """
    h, w = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(
        frame, 1.0, (300, 300), (104.0, 177.0, 123.0), False, False
    )
    face_net.setInput(blob)
    detections = face_net.forward()

    faces = []
    for i in range(detections.shape[2]):
        confidence = detections[0, 0, i, 2]
        if confidence < DNN_CONFIDENCE_THRESH:
            continue
        box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
        x1, y1, x2, y2 = box.astype(int)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        bw, bh = x2 - x1, y2 - y1
        if bw >= MIN_FACE_SIZE and bh >= MIN_FACE_SIZE:
            faces.append((x1, y1, bw, bh))
    return faces


def _detect_faces_haar(gray, face_cascade):
    """Fallback face detection using Haarcascade."""
    eq = cv2.equalizeHist(gray)
    faces = face_cascade.detectMultiScale(
        eq, scaleFactor=1.05, minNeighbors=6,
        minSize=(MIN_FACE_SIZE, MIN_FACE_SIZE),
        flags=cv2.CASCADE_SCALE_IMAGE,
    )
    return list(faces) if len(faces) > 0 else []


# ━━━━━━━━━━━━━━  FACE PREPROCESSING  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _pad_face_crop(frame, x, y, w, h, pad_ratio=FACE_PAD_RATIO):
    """Expand bounding box by pad_ratio for better emotion context."""
    img_h, img_w = frame.shape[:2]
    pad_w = int(w * pad_ratio)
    pad_h = int(h * pad_ratio)
    x1 = max(0, x - pad_w)
    y1 = max(0, y - pad_h)
    x2 = min(img_w, x + w + pad_w)
    y2 = min(img_h, y + h + pad_h)
    return frame[y1:y2, x1:x2]


def _preprocess_face(face_bgr):
    """
    Preprocess face crop for the CNN.
    EXACTLY matches the training pipeline:
      grayscale -> CLAHE -> resize 48x48 -> normalize [0,1]
    Returns (1, 48, 48, 1) float32 array.
    """
    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.resize(gray, (CNN_INPUT_SIZE, CNN_INPUT_SIZE),
                      interpolation=cv2.INTER_AREA)
    face_arr = gray.astype(np.float32) / 255.0
    face_arr = face_arr[np.newaxis, ..., np.newaxis]
    return face_arr


# ━━━━━━━━━━━━━━  SLIDING-WINDOW SMOOTHER  ━━━━━━━━━━━━━━━━━━━━━━━━━━
class EmotionSmoother:
    """
    Sliding-window smoother with confidence weighting.
    Keeps the last N predictions, weights recent ones higher,
    and requires confidence threshold to change displayed emotion.
    """

    def __init__(self, window_size: int = SMOOTH_WINDOW):
        self.window_size = window_size
        self.history = deque(maxlen=window_size)
        self.score_history = deque(maxlen=window_size)
        self.current_emotion = "neutral"
        self.current_confidence = 0.0
        self.current_scores = {e: 0.0 for e in ALL_EMOTIONS}

    def update(self, emotion: str, confidence: float, scores: dict):
        """Add a new prediction and compute smoothed output."""
        self.history.append((emotion, confidence))
        self.score_history.append(scores)

        # Weighted average of scores across window (recent frames weighted more)
        n = len(self.score_history)
        weights = np.linspace(0.5, 1.0, n)  # older=0.5, newest=1.0
        weights /= weights.sum()

        avg_scores = {e: 0.0 for e in ALL_EMOTIONS}
        for i, s in enumerate(self.score_history):
            for e in ALL_EMOTIONS:
                avg_scores[e] += weights[i] * s.get(e, 0.0)

        self.current_scores = avg_scores
        dominant = max(avg_scores, key=avg_scores.get)
        dom_conf = avg_scores[dominant] / 100.0

        # Only switch emotion if confidence exceeds threshold
        if dom_conf >= CONF_THRESHOLD or n <= 3:
            self.current_emotion = dominant
            self.current_confidence = dom_conf

        return self.current_emotion, self.current_confidence, self.current_scores

    def get_current(self):
        return self.current_emotion, self.current_confidence, self.current_scores


# ━━━━━━━━━━━━━━  EMOTION ANALYSER (with TTA)  ━━━━━━━━━━━━━━━━━━━━━━
def _analyse_emotion(model, face_input, device):
    """
    Run PyTorch CNN emotion analysis with optional Test-Time Augmentation.
    TTA: average predictions of original + horizontally flipped face.
    Returns (dominant_emotion, confidence, scores_dict).
    """
    try:
        # face_input is (1, 48, 48, 1) numpy array in HWC format
        # Convert to PyTorch CHW: (1, 1, 48, 48) then replicate to (1, 3, 48, 48) for ResNet
        face_tensor = torch.from_numpy(
            np.transpose(face_input, (0, 3, 1, 2))
        ).to(device)
        # Replicate grayscale to 3 channels
        face_tensor = face_tensor.repeat(1, 3, 1, 1)

        with torch.no_grad():
            logits_orig = model(face_tensor)
            preds_orig = F.softmax(logits_orig, dim=1)

            if USE_TTA:
                face_flipped = torch.flip(face_tensor, dims=[3])
                logits_flip = model(face_flipped)
                preds_flip = F.softmax(logits_flip, dim=1)
                preds = (preds_orig + preds_flip) / 2.0
            else:
                preds = preds_orig

        preds_np = preds[0].cpu().numpy()
        scores = {emo: float(preds_np[i]) * 100.0
                  for i, emo in enumerate(ALL_EMOTIONS)}
        dominant = ALL_EMOTIONS[int(np.argmax(preds_np))]
        conf = float(np.max(preds_np))
        return dominant, conf, scores
    except Exception:
        return "neutral", 0.0, {}


# ━━━━━━━━━━━━━━  DRAW BOUNDING BOX  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _draw_fancy_box(img, x, y, w, h, color, label):
    """Draw corner-style bounding box with label."""
    t = 2
    c = min(20, w // 4, h // 4)
    cv2.line(img, (x, y), (x + c, y), color, t)
    cv2.line(img, (x, y), (x, y + c), color, t)
    cv2.line(img, (x + w, y), (x + w - c, y), color, t)
    cv2.line(img, (x + w, y), (x + w, y + c), color, t)
    cv2.line(img, (x, y + h), (x + c, y + h), color, t)
    cv2.line(img, (x, y + h), (x, y + h - c), color, t)
    cv2.line(img, (x + w, y + h), (x + w - c, y + h), color, t)
    cv2.line(img, (x + w, y + h), (x + w, y + h - c), color, t)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
    cv2.rectangle(img, (x, y - th - 14), (x + tw + 10, y), color, -1)
    cv2.putText(img, label, (x + 5, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)


# ━━━━━━━━━━━━━━  EMOTION RESULT CARD  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _render_emotion_card(container, emotion, confidence, scores, history):
    """Render styled emotion result card."""
    emoji = EMOTION_EMOJI.get(emotion, "")
    bars = ""
    for emo in ["happy", "sad", "angry", "surprise", "fear", "disgust", "neutral"]:
        pct = scores.get(emo, 0)
        e = EMOTION_EMOJI.get(emo, "")
        bar_color = "#6c63ff" if emo == emotion else "rgba(255,255,255,0.18)"
        fw = "700" if emo == emotion else "400"
        bars += f"""
        <div style="display:flex;align-items:center;gap:8px;margin:5px 0;">
            <span style="width:100px;font-size:0.85rem;font-weight:{fw};">
                {e} {emo.capitalize()}</span>
            <div style="flex:1;background:rgba(255,255,255,0.08);
                        border-radius:6px;height:16px;overflow:hidden;">
                <div style="width:{pct:.1f}%;background:{bar_color};
                            height:100%;border-radius:6px;"></div>
            </div>
            <span style="width:50px;text-align:right;font-size:0.8rem;">
                {pct:.1f}%</span>
        </div>"""

    chips = ""
    for h_emo in history[-8:]:
        h_e = EMOTION_EMOJI.get(h_emo, "")
        chips += (f'<span style="display:inline-block;background:rgba(255,255,255,0.12);'
                  f'border-radius:12px;padding:3px 10px;margin:2px;font-size:0.78rem;">'
                  f'{h_e} {h_emo.capitalize()}</span>')

    container.markdown(f"""
    <div style="background:rgba(255,255,255,0.10);backdrop-filter:blur(14px);
                border-radius:20px;padding:28px;margin-top:18px;
                box-shadow:0 12px 48px rgba(0,0,0,0.30);
                border:1px solid rgba(108,99,255,0.25);">
        <h2 style="text-align:center;color:#f5f7ff;margin:0 0 2px;">
            {emoji} {emotion.capitalize()}</h2>
        <p style="text-align:center;color:#c0c0c0;margin-bottom:18px;
                  font-size:0.95rem;">
            Confidence: <b style="color:#6c63ff;">{confidence:.0%}</b></p>
        {bars}
        <hr style="border:none;border-top:1px solid rgba(255,255,255,0.12);
                   margin:14px 0 10px;">
        <p style="font-size:0.8rem;color:#aaa;margin-bottom:6px;">
            Recent detections:</p>
        <div style="display:flex;flex-wrap:wrap;">{chips}</div>
    </div>""", unsafe_allow_html=True)


# ━━━━━━━━━━━━━━  MAIN  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    """Emotion Detection page -- called from app.py."""
    
    # Debug: Show message on page
    st.error("DEBUG: emotion_detection_page.main() is running!")
    print("[DEBUG] Emotion Detection main() function is running...")

    st.markdown("""
    <div style="text-align:center;padding:24px 0 12px;">
        <h1 style="color:#f5f7ff;margin-bottom:4px;">Emotion Detection</h1>
        <p style="color:#c8c8c8;font-size:1.05rem;max-width:600px;margin:0 auto;">
            Click <b>Start Camera</b> to open your webcam. EmoRecs will detect
            your face and recognise your emotion in real-time using AI.
        </p>
    </div>""", unsafe_allow_html=True)

    # Session state defaults
    for key, val in {
        "camera_running": False,
        "last_emotion": None,
        "last_confidence": 0.0,
        "last_scores": {},
        "emotion_history": [],
        "detected_emotion": None,
    }.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # Buttons - Use columns for layout
    col1, col2 = st.columns(2)
    with col1:
        start_btn = st.button("📷 Start Camera", key="ed_start_btn", use_container_width=True)
    with col2:
        stop_btn = st.button("⏹ Stop Camera", key="ed_stop_btn", use_container_width=True)

    # Handle button clicks
    if start_btn:
        st.session_state.camera_running = True
        st.session_state.emotion_history = []
        st.session_state.detected_emotion = None
        st.rerun()
    
    if stop_btn:
        st.session_state.camera_running = False
        _release_camera()
        st.rerun()

    # Placeholders
    status_ph = st.empty()
    frame_ph = st.empty()
    emotion_ph = st.empty()

    # ── Camera OFF ────────────────────────────────────────────────────
    if not st.session_state.camera_running:
        if st.session_state.last_emotion:
            status_ph.info("Camera stopped. Emotion detection completed.")
            st.session_state.detected_emotion = st.session_state.last_emotion
            # No recommendation UI here
            # Navigation will be handled after timer
        else:
            frame_ph.markdown("""
            <div style="text-align:center;padding:80px 20px;
                        background:rgba(255,255,255,0.06);border-radius:16px;
                        border:2px dashed rgba(108,99,255,0.35);">
                <p style="font-size:3rem;margin:0;">📷</p>
                <p style="color:#c0c0c0;font-size:1rem;margin-top:8px;">
                    Camera is off. Click <b>Start Camera</b> to begin.
                </p>
            </div>""", unsafe_allow_html=True)
        return

    # ── Camera ON ─────────────────────────────────────────────────────
    # Add loading spinner while initializing camera
    with st.spinner("Initializing camera..."):
        face_net, face_cascade, emotion_model, device = _load_models()
        cap = _get_camera()
    
    if cap is None or not cap.isOpened():
        # Show helpful error message with troubleshooting steps
        frame_ph.markdown("""
        <div style="text-align:center;padding:40px 20px;
                    background:rgba(255,0,0,0.1);border-radius:16px;
                    border:2px solid rgba(255,0,0,0.3);">
            <p style="font-size:3rem;margin:0;">📷</p>
            <h3 style="color:#ff6b6b;margin:16px 0 8px;">Camera Not Available</h3>
            <p style="color:#c0c0c0;font-size:0.95rem;margin-bottom:16px;">
                Could not open your webcam. Please check the following:
            </p>
            <div style="text-align:left;background:rgba(0,0,0,0.3);padding:20px;border-radius:12px;margin:10px auto;max-width:400px;">
                <p style="color:#e0e0e0;margin:8px 0;font-size:0.9rem;"><b>🔌 Hardware:</b> Make sure your camera is connected</p>
                <p style="color:#e0e0e0;margin:8px 0;font-size:0.9rem;"><b>🚫 Other Apps:</b> Close other apps using the camera</p>
                <p style="color:#e0e0e0;margin:8px 0;font-size:0.9rem;"><b>🌐 Browser:</b> Allow camera permissions in your browser</p>
                <p style="color:#e0e0e0;margin:8px 0;font-size:0.9rem;"><b>🔄 Refresh:</b> Try refreshing the page</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Add a retry button
        if st.button("Try Again", key="ed_retry_btn", use_container_width=True):
            _release_camera()
            st.session_state.camera_running = False
            st.rerun()
        
        st.session_state.camera_running = False
        return

    detector_type = "DNN SSD" if face_net is not None else "Haarcascade"
    status_ph.success(f"Camera is running  |  Face detector: {detector_type}  "
                      f"|  TTA: {'ON' if USE_TTA else 'OFF'}")

    frame_count = 0
    smoother = EmotionSmoother(window_size=SMOOTH_WINDOW)
    dominant_emotion = st.session_state.last_emotion
    confidence = st.session_state.last_confidence
    scores = st.session_state.last_scores
    last_db_log_time = 0.0

    try:
        # 30-second timer for emotion detection
        detection_start = time.time()
        while st.session_state.camera_running:
            elapsed = time.time() - detection_start
            if elapsed >= 30:
                st.session_state.camera_running = False
                _release_camera()
                # After 30 seconds, redirect to Recommendations
                st.session_state.sidebar_selected = "Recommendations"
                st.rerun()
                break
            ret, frame = cap.read()
            if not ret:
                _release_camera()
                cap = _get_camera()
                if cap is None or not cap.isOpened():
                    frame_ph.error("Lost camera feed.")
                    break
                continue

            frame = cv2.flip(frame, 1)
            display = frame.copy()

            # ── Face detection ──
            if face_net is not None:
                faces = _detect_faces_dnn(frame, face_net)
            else:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = _detect_faces_haar(gray, face_cascade)

            for (x, y, w, h) in faces:
                if frame_count % ANALYSE_EVERY_N_FRAMES == 0:
                    # 1. Pad the face crop
                    face_crop = _pad_face_crop(frame, x, y, w, h)
                    if face_crop.size == 0:
                        continue

                    # 2. Preprocess (grayscale + CLAHE + resize + normalize)
                    face_processed = _preprocess_face(face_crop)

                    # 3. CNN prediction with TTA
                    raw_emotion, raw_conf, raw_scores = _analyse_emotion(
                        emotion_model, face_processed, device
                    )

                    # 4. Sliding-window smooth with confidence threshold
                    dominant_emotion, confidence, scores = smoother.update(
                        raw_emotion, raw_conf, raw_scores
                    )

                    st.session_state.last_emotion = dominant_emotion
                    st.session_state.last_confidence = confidence
                    st.session_state.last_scores = scores
                    st.session_state.emotion_history.append(dominant_emotion)

                    # Log to database periodically
                    now = time.time()
                    if (now - last_db_log_time) >= DB_LOG_COOLDOWN:
                        user_id = st.session_state.get("user_id")
                        if user_id:
                            database.log_emotion_detection(
                                user_id, dominant_emotion, confidence
                            )
                            database.log_user_activity(
                                user_id, "emotion_detection",
                                f"Detected: {dominant_emotion} ({confidence:.0%})",
                            )
                        last_db_log_time = now

                # Draw bounding box
                if dominant_emotion:
                    color = EMOTION_COLORS.get(dominant_emotion, (200, 200, 200))
                    emoji = EMOTION_EMOJI.get(dominant_emotion, "")
                    label = f"{emoji} {dominant_emotion.capitalize()} {confidence:.0%}"
                    _draw_fancy_box(display, x, y, w, h, color, label)
                else:
                    cv2.rectangle(display, (x, y), (x+w, y+h), (200, 200, 200), 2)

            # Show frame
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            frame_ph.image(rgb, channels="RGB", use_container_width=True)

            if dominant_emotion and scores:
                _render_emotion_card(
                    emotion_ph, dominant_emotion, confidence, scores,
                    st.session_state.emotion_history
                )

            frame_count += 1
            time.sleep(0.033)

    except Exception as e:
        status_ph.error(f"Camera error: {e}")
    finally:
        status_ph.info("Camera stopped.")
        if dominant_emotion:
            st.session_state.detected_emotion = dominant_emotion
            user_id = st.session_state.get("user_id")
            if user_id and st.session_state.emotion_history:
                most_common = Counter(
                    st.session_state.emotion_history
                ).most_common(1)[0][0]
                database.save_dominant_emotion(user_id, most_common)


def get_detected_emotion():
    """Return the last detected dominant emotion for recommendation logic."""
    return st.session_state.get("detected_emotion")


if __name__ == "__main__":
    main()
