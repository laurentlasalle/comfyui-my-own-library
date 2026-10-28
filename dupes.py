"""
Fingerprints used to spot duplicates: the same file byte for byte (SHA-256),
or the same content with different metadata (same pixels, frames or samples),
which is what running the same workflow with the same seed again gives.
"""

import hashlib
import subprocess
import sys

from . import metadata as md

HASH_VERSION = 1

_FLAGS = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _image_hash(path):
    from PIL import Image
    h = hashlib.sha256()
    with Image.open(path) as img:
        frames = getattr(img, "n_frames", 1) or 1
        h.update(("%dx%d:%d" % (img.width, img.height, frames)).encode())
        for i in range(frames):
            img.seek(i)
            h.update(img.convert("RGBA").tobytes())
    return h.hexdigest()


def _media_hash(path):
    """Hash of the decoded video and audio, through ffmpeg."""
    exe = md.ffmpeg_exe()
    if not exe:
        return None
    out = subprocess.run([exe, "-v", "error", "-i", path, "-map", "0:v:0?", "-map", "0:a?",
                          "-f", "hash", "-hash", "sha256", "-"],
                         capture_output=True, timeout=600, creationflags=_FLAGS).stdout
    text = out.decode("ascii", "ignore").strip()
    return text.split("=", 1)[1] if text.startswith("SHA256=") else None


def content_hash(path, kind):
    """Fingerprint of what the file shows or plays, ignoring metadata. Never raises."""
    try:
        if kind == "image":
            return _image_hash(path)
        if kind in ("video", "audio"):
            return _media_hash(path)
    except Exception:
        return None
    return None


def fingerprints(path, kind):
    sha = None
    try:
        sha = file_sha256(path)
    except OSError:
        pass
    return {"sha": sha, "chash": content_hash(path, kind), "hash_v": HASH_VERSION}
