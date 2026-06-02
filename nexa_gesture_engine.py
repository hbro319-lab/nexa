"""
NEXA — Gesture Engine
Uses MediaPipe Hands to detect gestures from a webcam and sends them
to the NEXA dispatcher as structured JSON commands.

Install dependencies:
    pip install mediapipe opencv-python

Run:
    python nexa_gesture_engine.py
"""

import json
import time
import sys

# ── GESTURE → MODULE MAP (from nexa_config.json) ────────────────────
GESTURE_MAP = {
    "swipe_left":   {"module": "gesture_interface", "action": "navigate",   "parameters": {"direction": "left"}},
    "swipe_right":  {"module": "gesture_interface", "action": "navigate",   "parameters": {"direction": "right"}},
    "thumbs_up":    {"module": "gesture_interface", "action": "confirm",    "parameters": {"gesture": "thumbs_up"}},
    "closed_fist":  {"module": "gesture_interface", "action": "cancel",     "parameters": {"gesture": "closed_fist"}},
    "open_hand":    {"module": "gesture_interface", "action": "pause",      "parameters": {"gesture": "open_hand"}},
    "point":        {"module": "gesture_interface", "action": "select",     "parameters": {"gesture": "point"}},
}

COOLDOWN_SECONDS = 1.5  # Minimum time between gesture triggers

# ── LANDMARK ANALYSIS ────────────────────────────────────────────────

def finger_extended(landmarks, tip_id, pip_id):
    """Returns True if a finger is extended (tip above PIP joint)."""
    return landmarks[tip_id].y < landmarks[pip_id].y


def classify_gesture(hand_landmarks, prev_wrist_x=None):
    """
    Classify gesture from MediaPipe hand landmark data.
    Returns a gesture name string or None.
    """
    lm = hand_landmarks.landmark

    # Finger states
    index_up  = finger_extended(lm, 8, 6)
    middle_up = finger_extended(lm, 12, 10)
    ring_up   = finger_extended(lm, 16, 14)
    pinky_up  = finger_extended(lm, 20, 18)
    thumb_up  = lm[4].y < lm[3].y  # simplified thumb check

    fingers_up = sum([index_up, middle_up, ring_up, pinky_up])

    # Closed fist
    if fingers_up == 0 and not thumb_up:
        return "closed_fist"

    # Open hand (all 5 fingers up)
    if fingers_up >= 3 and thumb_up:
        return "open_hand"

    # Thumbs up (only thumb extended, others curled)
    if thumb_up and fingers_up == 0:
        return "thumbs_up"

    # Point (only index finger extended)
    if index_up and not middle_up and not ring_up and not pinky_up:
        return "point"

    # Swipe detection (based on wrist x-movement)
    wrist_x = lm[0].x
    if prev_wrist_x is not None:
        delta = wrist_x - prev_wrist_x
        if delta < -0.05:
            return "swipe_left"
        if delta > 0.05:
            return "swipe_right"

    return None


# ── MAIN LOOP ────────────────────────────────────────────────────────

def run():
    try:
        import cv2
        import mediapipe as mp
    except ImportError:
        print("Missing dependencies. Install with:")
        print("  pip install mediapipe opencv-python")
        sys.exit(1)

    from nexa_dispatcher import dispatch

    mp_hands = mp.solutions.hands
    mp_draw  = mp.solutions.drawing_utils

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[NEXA GESTURE] Could not open camera.")
        sys.exit(1)

    print("[NEXA GESTURE] Engine running. Press Q to quit.")

    last_gesture_time = 0
    prev_wrist_x = None

    with mp_hands.Hands(
        max_num_hands=1,
        min_detection_confidence=0.75,
        min_tracking_confidence=0.6
    ) as hands:

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)

            if result.multi_hand_landmarks:
                for hand_lm in result.multi_hand_landmarks:
                    mp_draw.draw_landmarks(frame, hand_lm, mp_hands.HAND_CONNECTIONS)

                    gesture = classify_gesture(hand_lm, prev_wrist_x)
                    prev_wrist_x = hand_lm.landmark[0].x

                    now = time.time()
                    if gesture and (now - last_gesture_time) > COOLDOWN_SECONDS:
                        last_gesture_time = now
                        cmd = GESTURE_MAP.get(gesture)
                        if cmd:
                            print(f"\n[GESTURE DETECTED] {gesture}")
                            dispatch(cmd)

                        cv2.putText(frame, gesture.upper(), (20, 50),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (120, 80, 255), 2)
            else:
                prev_wrist_x = None

            cv2.imshow("NEXA Gesture Engine", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    cv2.destroyAllWindows()
    print("[NEXA GESTURE] Engine stopped.")


if __name__ == "__main__":
    run()
