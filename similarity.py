"""
Similarity signatures, used to suggest versions only among creations that
actually look (or sound) alike.

- Images: a 256-bit difference hash (structure: shapes, composition, light and
  dark areas) plus a 4x4 grid of average colors.
- Videos: the same signature on four frames spread over the video.
- Audio: the loudness envelope (64 steps) and the duration.

Only Pillow and ffmpeg are used (both already present with ComfyUI).
"""

import math
import os
import re
import struct
import subprocess
import sys

from . import metadata as md

SIG_VERSION = 1

# Minimum score (0 to 1) for two creations to count as versions of each other,
# and minimum color agreement for images and videos ("color"), so that two
# pictures with a similar layout but different dominant colors never match.
LEVELS = {
    "strict": {"image": 0.86, "video": 0.84, "audio": 0.85, "color": 0.80},
    "normal": {"image": 0.78, "video": 0.76, "audio": 0.75, "color": 0.70},
    "loose": {"image": 0.68, "video": 0.66, "audio": 0.62, "color": 0.58},
}

_FLAGS = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


# --------------------------------------------------------------------- images

def _image_sig(img):
    from PIL import Image
    img = img.convert("RGB")
    gray = img.convert("L").resize((17, 16), Image.BILINEAR)
    px = list(gray.getdata())
    bits = 0
    for y in range(16):
        row = px[y * 17:(y + 1) * 17]
        for x in range(16):
            bits = (bits << 1) | (1 if row[x] > row[x + 1] else 0)
    colors = list(img.resize((4, 4), Image.BOX).getdata())
    return {"dh": "%064x" % bits, "col": [c for rgb in colors for c in rgb]}


def image_signature(path):
    from PIL import Image
    with Image.open(path) as img:
        img.seek(0)
        return {"kind": "image", "v": SIG_VERSION, **_image_sig(img)}


def _image_parts(a, b):
    ham = bin(int(a["dh"], 16) ^ int(b["dh"], 16)).count("1") / 256.0
    structure = 1.0 - ham
    diff = sum(abs(x - y) for x, y in zip(a["col"], b["col"])) / (len(a["col"]) * 255.0)
    color = max(0.0, 1.0 - diff * 3.0)
    return 0.65 * structure + 0.35 * color, color


def _image_score(a, b):
    return _image_parts(a, b)[0]


# --------------------------------------------------------------------- videos

def _duration(path):
    exe = md.ffmpeg_exe()
    if not exe:
        return None
    try:
        err = subprocess.run([exe, "-hide_banner", "-i", path], capture_output=True, timeout=30,
                             creationflags=_FLAGS).stderr.decode("utf-8", "ignore")
    except Exception:
        return None
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def video_signature(path):
    from io import BytesIO
    from PIL import Image
    exe = md.ffmpeg_exe()
    duration = _duration(path)
    if not exe or not duration:
        return None
    frames = []
    for frac in (0.1, 0.35, 0.6, 0.85):
        try:
            out = subprocess.run(
                [exe, "-v", "error", "-ss", "%.3f" % (duration * frac), "-i", path, "-frames:v", "1",
                 "-vf", "scale=128:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                capture_output=True, timeout=30, creationflags=_FLAGS).stdout
            if out:
                with Image.open(BytesIO(out)) as img:
                    frames.append(_image_sig(img))
        except Exception:
            continue
    if not frames:
        return None
    return {"kind": "video", "v": SIG_VERSION, "frames": frames, "dur": round(duration, 2)}


def _video_parts(a, b):
    fa, fb = a["frames"], b["frames"]
    n = min(len(fa), len(fb))
    if not n:
        return 0.0, 0.0
    parts = [_image_parts(fa[i], fb[i]) for i in range(n)]
    frames = sum(p[0] for p in parts) / n
    color = sum(p[1] for p in parts) / n
    da, db = a.get("dur") or 0, b.get("dur") or 0
    dur = min(da, db) / max(da, db) if da and db else 1.0
    return 0.85 * frames + 0.15 * dur, color


# ---------------------------------------------------------------------- audio

def audio_signature(path):
    from array import array
    exe = md.ffmpeg_exe()
    if not exe:
        return None
    rate = 4000
    try:
        raw = subprocess.run([exe, "-v", "error", "-i", path, "-ac", "1", "-ar", str(rate),
                              "-f", "s16le", "-"], capture_output=True, timeout=120,
                             creationflags=_FLAGS).stdout
    except Exception:
        return None
    samples = array("h")
    samples.frombytes(raw[:len(raw) - len(raw) % 2])
    if sys.byteorder != "little":
        samples.byteswap()
    n = len(samples)
    if n < rate // 10:
        return None
    bins = 64
    env = []
    for i in range(bins):
        chunk = samples[i * n // bins:(i + 1) * n // bins]
        env.append(math.sqrt(sum(s * s for s in chunk) / max(1, len(chunk))))
    peak = max(env) or 1.0
    return {"kind": "audio", "v": SIG_VERSION, "env": [round(e / peak, 4) for e in env],
            "dur": round(n / rate, 2)}


def _audio_score(a, b):
    x, y = a["env"], b["env"]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    vx = math.sqrt(sum((v - mx) ** 2 for v in x))
    vy = math.sqrt(sum((v - my) ** 2 for v in y))
    r = sum((p - mx) * (q - my) for p, q in zip(x, y)) / (vx * vy) if vx and vy else 0.0
    da, db = a.get("dur") or 0, b.get("dur") or 0
    dur = min(da, db) / max(da, db) if da and db else 0.0
    return 0.65 * (r + 1) / 2 + 0.35 * dur


# -------------------------------------------------------------------- public

def signature(path, kind, thumb=None):
    """Signature of a library file. 'thumb' (the library thumbnail) is used for
    images, and for videos when ffmpeg can't read them. Never raises."""
    try:
        if kind == "image":
            src = thumb if thumb and os.path.isfile(thumb) else path
            return image_signature(src)
        if kind == "video":
            sig = video_signature(path)
            if sig is None and thumb and os.path.isfile(thumb):
                sig = {"kind": "video", "v": SIG_VERSION, "frames": [image_signature(thumb)], "dur": None}
                sig["frames"][0].pop("kind", None)
            return sig
        if kind == "audio":
            return audio_signature(path)
    except Exception:
        return None
    return None


def compare(a, b):
    """(similarity from 0 to 1, color agreement from 0 to 1 or None for audio),
    or None when it can't be told."""
    if not a or not b or a.get("kind") != b.get("kind"):
        return None
    try:
        if a["kind"] == "image":
            return _image_parts(a, b)
        if a["kind"] == "video":
            return _video_parts(a, b)
        if a["kind"] == "audio":
            return _audio_score(a, b), None
    except Exception:
        return None
    return None


def score(a, b):
    """Similarity from 0 to 1, or None when it can't be told."""
    parts = compare(a, b)
    return None if parts is None else parts[0]


def threshold(kind, level):
    return LEVELS.get(level, LEVELS["normal"]).get(kind, 0.78)


def matches(parts, kind, level):
    """Whether a compare() result is close enough to count as versions."""
    if parts is None:
        return False
    value, color = parts
    if value < threshold(kind, level):
        return False
    return color is None or color >= LEVELS.get(level, LEVELS["normal"])["color"]


# ------------------------------------------------------- across workflows
# Creations without any link in their metadata are suggested only when they
# look almost identical (Loose level).
LOOKALIKE = 0.92


def lookalike_pairs(entries, threshold=LOOKALIKE):
    """Pairs of (id_a, id_b, score) among [(id, kind, sig)] that look almost
    identical. Images and videos only; compared all against all with NumPy,
    then confirmed with compare()."""
    import numpy as np
    rows = []
    for item_id, kind, sig in entries:
        if not sig or kind not in ("image", "video"):
            continue
        base = sig if kind == "image" else (sig.get("frames") or [None])[0]
        if not base or "dh" not in base:
            continue
        rows.append((item_id, kind, sig, base))
    n = len(rows)
    if n < 2:
        return []
    hashes = np.array([np.frombuffer(bytes.fromhex(r[3]["dh"]), dtype=np.uint8) for r in rows])
    cols = np.array([r[3]["col"] for r in rows], dtype=np.float32)
    kinds = np.array([0 if r[1] == "image" else 1 for r in rows])
    popcount = np.array([bin(v).count("1") for v in range(256)], dtype=np.uint16)
    out = []
    block = 32  # rows compared at once: keeps memory low for large libraries
    for start in range(0, n, block):
        a_hash = hashes[start:start + block]
        a_cols = cols[start:start + block]
        ham = popcount[a_hash[:, None, :] ^ hashes[None, :, :]].sum(axis=2) / 256.0
        diff = np.abs(a_cols[:, None, :] - cols[None, :, :]).sum(axis=2) / (cols.shape[1] * 255.0)
        score = 0.65 * (1.0 - ham) + 0.35 * np.clip(1.0 - diff * 3.0, 0.0, 1.0)
        # Rough first pass a little below the bar, exact check after.
        cand = np.argwhere(score >= threshold - 0.04)
        for i, j in cand:
            gi = start + int(i)
            gj = int(j)
            if gj <= gi or kinds[gi] != kinds[gj]:
                continue
            parts = compare(rows[gi][2], rows[gj][2])
            if parts and parts[0] >= threshold:
                out.append((rows[gi][0], rows[gj][0], parts[0]))
    return out
