"""
Point of interest of a thumbnail, so the square crop of the grid can be
centered on it instead of the middle of the picture.

- One face (or one face clearly bigger than the others): its center.
- Otherwise, for a portrait picture (taller than wide): the upper third,
  where heads usually are.
- Otherwise nothing: the crop stays centered.

Faces are found with OpenCV's frontal face detector when OpenCV is installed
(most ComfyUI setups have it through other custom nodes). Without it, only
the portrait rule applies.
"""

import os

FOCUS_VERSION = 1

_cascade = None
_cascade_failed = False


def _detector():
    global _cascade, _cascade_failed
    if _cascade is not None or _cascade_failed:
        return _cascade
    try:
        import cv2
        name = "haarcascade_frontalface_default.xml"
        # OpenCV 4 ships the detector's data; OpenCV 5 doesn't anymore, so a copy
        # comes with this package (OpenCV data, Intel license kept in the file).
        path = os.path.join(getattr(getattr(cv2, "data", None), "haarcascades", "") or "", name)
        if not os.path.isfile(path):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", name)
        cascade = cv2.CascadeClassifier(path)
        if cascade.empty():
            raise RuntimeError("no cascade")
        _cascade = cascade
    except Exception:
        _cascade_failed = True
    return _cascade


def opencv_available():
    return _detector() is not None


def focus_point(thumb_path):
    """{"x": 0-1, "y": 0-1, "face": bool} or None (keep the crop centered).
    Never raises."""
    try:
        from PIL import Image
        with Image.open(thumb_path) as img:
            w, h = img.size
            gray = img.convert("L")
            faces = []
            cascade = _detector()
            if cascade is not None:
                import numpy as np
                arr = np.asarray(gray)
                side = min(w, h)
                found = cascade.detectMultiScale(arr, scaleFactor=1.1, minNeighbors=6,
                                                 minSize=(max(24, int(side * 0.08)),) * 2)
                faces = sorted(((int(fw) * int(fh), int(fx), int(fy), int(fw), int(fh)) for fx, fy, fw, fh in found),
                               reverse=True)
        if faces:
            # A single subject: one face, or one much bigger than the next.
            if len(faces) == 1 or faces[1][0] < faces[0][0] * 0.45:
                _, fx, fy, fw, fh = faces[0]
                return {"x": round((fx + fw / 2) / w, 3), "y": round((fy + fh / 2) / h, 3), "face": True}
            return None
        if h > w * 1.1:
            return {"x": 0.5, "y": 0.33, "face": False}
        return None
    except Exception:
        return None
