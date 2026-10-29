"""
Metadata extraction for ComfyUI outputs.

Reads the "prompt" (API format) and "workflow" (UI format) that ComfyUI and
VideoHelperSuite embed in their files, and builds a readable summary:
positive/negative prompts, seeds, models and LoRAs.

Supported sources:
- PNG: tEXt chunks "prompt" and "workflow" (Save Image).
- WebP / JPEG: EXIF strings "prompt:{...}" / "workflow:{...}" (Save Animated WEBP and similar).
- MP4 / MOV / M4V: the "comment" tag written by VideoHelperSuite, a JSON object
  with "prompt" and "workflow" keys.
- Any video with a companion PNG of the same name (VideoHelperSuite saves one
  when save_metadata is on): the PNG is used instead.
- FLAC: Vorbis comments "prompt" and "workflow" (ComfyUI's Save Audio and
  similar). M4A: same tags as MP4. MP3, WAV, OGG/Opus: tags read with ffmpeg.
"""

import json
import os
import re
import struct

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".m4v", ".avi"}
AUDIO_EXTS = {".flac", ".wav", ".mp3", ".ogg", ".opus", ".m4a", ".aac"}
MP4_LIKE = {".mp4", ".mov", ".m4v", ".m4a"}
MODEL_EXTS = (".safetensors", ".ckpt", ".pt", ".pth", ".gguf", ".bin", ".sft", ".onnx")

TEXT_KEYS = ("text", "text_g", "text_l", "prompt", "positive_prompt", "string", "value", "text_a", "choice")
JSON_PROMPT_KEYS = ("user_prompt", "prompt", "positive_prompt", "positive", "text_prompt", "caption")
FALLBACK_TEXT_KEYS = ("prompt", "text", "positive_prompt", "description", "value", "string", "reference_text")
SEED_KEYS = ("seed", "noise_seed", "seed_num")


def kind_of(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    return None


_ffmpeg_path = None


def ffmpeg_exe():
    """ffmpeg from the system, or the one bundled with imageio-ffmpeg (installed
    by VideoHelperSuite). Looked up once, only when first needed."""
    global _ffmpeg_path
    if _ffmpeg_path is not None:
        return _ffmpeg_path or None
    import shutil
    path = shutil.which("ffmpeg")
    if not path:
        try:
            import imageio_ffmpeg
            path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            path = None
    _ffmpeg_path = path or ""
    return path


def _flac_tags(path):
    """Vorbis comments of a FLAC file, as a dict with lowercase keys."""
    tags = {}
    with open(path, "rb") as f:
        if f.read(4) != b"fLaC":
            return tags
        while True:
            header = f.read(4)
            if len(header) < 4:
                break
            last = header[0] & 0x80
            btype = header[0] & 0x7F
            length = int.from_bytes(header[1:4], "big")
            if btype == 4:  # VORBIS_COMMENT
                block = f.read(length)
                pos = 0
                vlen = struct.unpack("<I", block[pos:pos + 4])[0]
                pos += 4 + vlen
                count = struct.unpack("<I", block[pos:pos + 4])[0]
                pos += 4
                for _ in range(count):
                    clen = struct.unpack("<I", block[pos:pos + 4])[0]
                    pos += 4
                    entry = block[pos:pos + clen].decode("utf-8", "ignore")
                    pos += clen
                    key, sep, value = entry.partition("=")
                    if sep:
                        tags.setdefault(key.lower(), value)
                break
            f.seek(length, 1)
            if last:
                break
    return tags


def _ffmpeg_tags(path):
    """Container tags read through ffmpeg's ffmetadata output."""
    import subprocess
    import sys
    exe = ffmpeg_exe()
    if not exe:
        return {}
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    try:
        out = subprocess.run([exe, "-v", "error", "-i", path, "-f", "ffmetadata", "-"],
                             capture_output=True, timeout=30, creationflags=flags).stdout.decode("utf-8", "ignore")
    except Exception:
        return {}
    # Values escape '=', ';', '#', '\' and newlines with a backslash.
    tags, key, value, in_value = {}, [], [], False
    text = out.split("\n", 1)[1] if out.startswith(";FFMETADATA") else out
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            (value if in_value else key).append(text[i + 1])
            i += 2
            continue
        if c == "=" and not in_value:
            in_value = True
        elif c == "\n":
            if in_value and key:
                tags.setdefault("".join(key).strip().lower(), "".join(value))
            key, value, in_value = [], [], False
        else:
            (value if in_value else key).append(c)
        i += 1
    if in_value and key:
        tags.setdefault("".join(key).strip().lower(), "".join(value))
    return tags


def _from_audio(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".flac":
        tags = _flac_tags(path)
    elif ext in MP4_LIKE:
        tags = _mp4_tags(path)
    else:
        tags = _ffmpeg_tags(path)
    prompt, workflow = _loads(tags.get("prompt")), _loads(tags.get("workflow"))
    if prompt is None and workflow is None and isinstance(_loads(tags.get("comment")), dict):
        obj = _loads(tags["comment"])
        prompt, workflow = _loads(obj.get("prompt")), _loads(obj.get("workflow"))
    return prompt, workflow


def _loads(value):
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, (str, bytes)):
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


# --------------------------------------------------------------------------
# Raw extraction
# --------------------------------------------------------------------------

def _from_image(path):
    """Return (prompt, workflow) from an image file, or (None, None)."""
    from PIL import Image  # Pillow is always present in ComfyUI

    prompt = workflow = None
    with Image.open(path) as img:
        info = getattr(img, "info", {}) or {}
        prompt = _loads(info.get("prompt"))
        workflow = _loads(info.get("workflow"))
        if prompt is None and workflow is None:
            try:
                exif = img.getexif()
            except Exception:
                exif = None
            if exif:
                for value in exif.values():
                    if isinstance(value, bytes):
                        try:
                            value = value.decode("utf-8", "ignore")
                        except Exception:
                            continue
                    if not isinstance(value, str) or ":" not in value:
                        continue
                    key, _, payload = value.partition(":")
                    key = key.strip().lower()
                    if key == "prompt" and prompt is None:
                        prompt = _loads(payload)
                    elif key == "workflow" and workflow is None:
                        workflow = _loads(payload)
    return prompt, workflow


def _iter_atoms(f, start, end):
    """Yield (type, payload_start, payload_end) for MP4 atoms between start and end."""
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        header = f.read(8)
        if len(header) < 8:
            return
        size, atype = struct.unpack(">I4s", header)
        header_len = 8
        if size == 1:
            ext = f.read(8)
            if len(ext) < 8:
                return
            size = struct.unpack(">Q", ext)[0]
            header_len = 16
        elif size == 0:
            size = end - pos
        if size < header_len:
            return
        yield atype, pos + header_len, min(pos + size, end)
        pos += size


def _mp4_tags(path):
    """Return the text tags of an MP4/MOV file as a dict.

    Covers both layouts ComfyUI tools use:
    - iTunes-style '©cmt' (comment), written by VideoHelperSuite with the
      prompt and workflow inside one JSON object;
    - QuickTime 'mdta' named keys ('prompt', 'workflow'), written by ComfyUI's
      native Save Video node and by Easy-Media's save nodes.
    """
    file_size = os.path.getsize(path)
    with open(path, "rb") as f:
        moov = None
        for atype, s, e in _iter_atoms(f, 0, file_size):
            if atype == b"moov":
                moov = (s, e)
                break
        if not moov:
            return {}
        # Cap the read: moov holds sample tables, normally a few MB at most.
        length = min(moov[1] - moov[0], 64 * 1024 * 1024)
        f.seek(moov[0])
        data = f.read(length)

    def children(start, end):
        pos = start
        while pos + 8 <= end:
            size, atype = struct.unpack(">I4s", data[pos:pos + 8])
            if size < 8 or pos + size > end:
                return
            yield atype, pos + 8, pos + size
            pos += size

    def meta_body(start, end):
        # ISO 'meta' is a full box (4 bytes of version and flags before its
        # children); QuickTime 'meta' is not. Tell them apart by what follows.
        if end - start >= 12 and data[start + 4:start + 8] in (b"hdlr", b"keys", b"ilst"):
            return start
        return start + 4

    def data_text(start, end):
        for atype, s, e in children(start, end):
            if atype == b"data" and e - s > 8:
                return data[s + 8:e].decode("utf-8", "ignore")  # skip type + locale
        return None

    tags = {}

    def read_meta(start, end):
        body = meta_body(start, end)
        keys = []
        ilst = None
        for atype, s, e in children(body, end):
            if atype == b"keys" and e - s >= 8:
                count = struct.unpack(">I", data[s + 4:s + 8])[0]
                pos = s + 8
                for _ in range(count):
                    if pos + 8 > e:
                        break
                    ksize = struct.unpack(">I", data[pos:pos + 4])[0]
                    if ksize < 8:
                        break
                    keys.append(data[pos + 8:pos + ksize].decode("utf-8", "ignore"))
                    pos += ksize
            elif atype == b"ilst":
                ilst = (s, e)
        if not ilst:
            return
        for atype, s, e in children(*ilst):
            text = data_text(s, e)
            if text is None:
                continue
            if atype == b"\xa9cmt":
                tags.setdefault("comment", text)
                continue
            index = struct.unpack(">I", atype)[0]
            if 1 <= index <= len(keys):
                tags.setdefault(keys[index - 1], text)

    for atype, s, e in children(0, len(data)):
        if atype == b"meta":
            read_meta(s, e)
        elif atype == b"udta":
            for btype, bs, be in children(s, e):
                if btype == b"meta":
                    read_meta(bs, be)

    if not tags:
        # Fallback: an embedded JSON object without a recognizable structure.
        idx = data.find(b'{"prompt"')
        if idx < 0:
            idx = data.find(b'{"workflow"')
        if idx >= 0:
            try:
                obj, _ = json.JSONDecoder().raw_decode(data[idx:].decode("utf-8", "ignore"))
                tags["comment"] = json.dumps(obj)
            except Exception:
                pass
    return tags


def _from_video(path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in MP4_LIKE:
        return None, None
    try:
        tags = _mp4_tags(path)
    except Exception:
        return None, None
    prompt, workflow = _loads(tags.get("prompt")), _loads(tags.get("workflow"))
    if prompt is not None or workflow is not None:
        return prompt, workflow
    obj = _loads(tags.get("comment"))
    if isinstance(obj, dict):
        return _loads(obj.get("prompt")), _loads(obj.get("workflow"))
    return None, None


def companion_png(path):
    """VideoHelperSuite saves 'name.png' next to 'name.mp4'. Return it if present."""
    if kind_of(path) != "video":
        return None
    candidate = os.path.splitext(path)[0] + ".png"
    return candidate if os.path.isfile(candidate) else None


def extract(path):
    """Return (prompt, workflow) for any supported file. Never raises."""
    try:
        kind = kind_of(path)
        if kind == "image":
            return _from_image(path)
        if kind == "video":
            comp = companion_png(path)
            if comp:
                prompt, workflow = _from_image(comp)
                if prompt is not None or workflow is not None:
                    return prompt, workflow
            return _from_video(path)
        if kind == "audio":
            return _from_audio(path)
    except Exception:
        pass
    return None, None


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

def _dedupe(values):
    seen, out = set(), []
    for v in values:
        key = v.strip() if isinstance(v, str) else v
        if key in seen or key in ("", None):
            continue
        seen.add(key)
        out.append(key)
    return out


def _is_ref(value):
    return (isinstance(value, list) and len(value) == 2
            and isinstance(value[0], (str, int)) and isinstance(value[1], int))


SUMMARY_VERSION = 6  # 6: "sources" (files loaded by Load Image / Load Video nodes)

# Inputs whose value is never the main diffusion model, ignored for family detection
# unless nothing else matched.
SECONDARY_MODEL_KEYS = ("vae", "clip", "text_encoder", "t5", "llm", "upscale", "lora", "rife",
                        "ckpt_name_vfi", "control", "ipadapter", "clip_vision", "sam", "detector")
PRIMARY_MODEL_KEYS = ("unet_name", "ckpt_name", "model_name", "diffusion_model", "model_path", "gguf_name", "model")

# Model families, written the way their creators write them. First match wins.
FAMILY_RULES = [
    (r"minimax[ ._-]?h3", "MiniMax H3"),
    (r"chatterbox", "Chatterbox"),
    (r"seedvr[ ._-]?2", "SeedVR2"),
    (r"seedvr", "SeedVR"),
    (r"wan[ ._-]?2[ ._-]?2|wan22", "Wan 2.2"),
    (r"wan[ ._-]?2[ ._-]?1|wan21", "Wan 2.1"),
    (r"(^|[^a-z])wan", "Wan"),
    (r"flux[ ._-]?2|flux2", "FLUX.2"),
    (r"kontext", "FLUX.1 Kontext"),
    (r"flux", "FLUX.1"),
    (r"qwen[ ._-]?image[ ._-]?edit", "Qwen Image Edit"),
    (r"qwen[ ._-]?image[ ._-]?2[ ._-]?1", "Qwen Image 2.1"),
    (r"qwen[ ._-]?image", "Qwen Image"),
    (r"z[ ._-]?image[ ._-]?turbo", "Z-Image-Turbo"),
    (r"z[ ._-]?image", "Z-Image"),
    (r"hunyuan[ ._-]?video|hunyuanvideo|hyvideo", "HunyuanVideo"),
    (r"hunyuan[ ._-]?3d", "Hunyuan3D"),
    (r"hunyuan[ ._-]?image", "HunyuanImage"),
    (r"ltx[ ._-]?2", "LTX-2"),
    (r"ltx", "LTX-Video"),
    (r"hidream", "HiDream"),
    (r"chroma", "Chroma"),
    (r"omnigen", "OmniGen"),
    (r"lumina", "Lumina"),
    (r"cosmos", "Cosmos"),
    (r"mochi", "Mochi"),
    (r"sd[ ._-]?3[ ._-]?5|sd35", "SD 3.5"),
    (r"sd[ ._-]?3", "SD3"),
    (r"illustrious", "Illustrious"),
    (r"pony", "Pony"),
    (r"sdxl|sd_xl", "SDXL"),
    (r"sd[ ._-]?1[ ._-]?5|v1-5", "SD 1.5"),
]

# Node class names that betray a family when no file name does.
CLASS_RULES = [
    (r"minimaxh3", "MiniMax H3"),
    (r"chatterbox", "Chatterbox"),
    (r"seedvr2", "SeedVR2"),
    (r"flux2", "FLUX.2"),
    (r"kontext", "FLUX.1 Kontext"),
    (r"flux", "FLUX.1"),
    (r"qwenimage.*edit|textencodeqwenimageedit", "Qwen Image Edit"),
    (r"qwenimage21", "Qwen Image 2.1"),
    (r"qwenimage", "Qwen Image"),
    (r"zimage", "Z-Image"),
    (r"wan22", "Wan 2.2"),
    (r"wan", "Wan"),
    (r"hunyuanvideo", "HunyuanVideo"),
    (r"hunyuan3d", "Hunyuan3D"),
    (r"ltxv", "LTX-Video"),
    (r"hidream", "HiDream"),
    (r"sd3", "SD3"),
    (r"sdxl", "SDXL"),
]


def _match_family(names, rules):
    import re
    for name in names:
        low = name.lower()
        for pattern, label in rules:
            if re.search(pattern, low):
                return label
    return None


def _is_save_node(class_type):
    c = class_type.lower()
    return "save" in c or "videocombine" in c


def used_nodes(prompt, filename=None, workflow=None):
    """Nodes that actually contributed to this file, with their distance to it.

    Starts from the save node that wrote the file (its filename_prefix matches
    the file name), or every save node when that can't be told, and walks the
    links backwards. Nodes on branches that don't lead there are left out.
    Bypassed and muted nodes are never in the executed graph; the workflow is
    checked too, as a safety. Returns {node_id: longest distance to the output}.
    """
    nodes = {str(k): v for k, v in prompt.items() if isinstance(v, dict)}
    if isinstance(workflow, dict):
        off = {str(n.get("id")) for n in workflow.get("nodes", []) or [] if n.get("mode") in (2, 4)}
        nodes = {k: v for k, v in nodes.items() if k not in off}
    outputs = [k for k, n in nodes.items() if _is_save_node(str(n.get("class_type", "")))]
    if filename and outputs:
        stem = os.path.splitext(os.path.basename(filename))[0].lower()
        matched = []
        for k in outputs:
            prefix = (nodes[k].get("inputs") or {}).get("filename_prefix")
            if isinstance(prefix, str) and prefix.strip():
                base = re.split(r"[\\/]", prefix.strip())[-1].lower()
                if base and "%" not in base and stem.startswith(base):
                    matched.append(k)
        if matched:
            outputs = matched
    if not outputs:
        referenced = {str(v[0]) for n in nodes.values() for v in (n.get("inputs") or {}).values() if _is_ref(v)}
        outputs = [k for k in nodes if k not in referenced]
    dist = {}

    def visit(k, d, path):
        if k not in nodes or k in path or dist.get(k, -1) >= d:
            return
        dist[k] = d
        path.add(k)
        for v in (nodes[k].get("inputs") or {}).values():
            if _is_ref(v):
                visit(str(v[0]), d + 1, path)
        path.discard(k)

    for o in outputs:
        visit(o, 0, set())
    return dist


def detect_families(prompt, filename=None, workflow=None, dist=None):
    """Model families used for this file, in order of execution (first first)."""
    if not isinstance(prompt, dict):
        return []
    if dist is None:
        dist = used_nodes(prompt, filename, workflow)
    keys = list(dist) or [str(k) for k in prompt]
    order = {k: i for i, k in enumerate(prompt)}
    found = {}      # label -> (distance, order)
    other = []
    for k in keys:
        node = prompt.get(k) if k in prompt else prompt.get(int(k)) if k.isdigit() else None
        if not isinstance(node, dict):
            continue
        for key, value in (node.get("inputs") or {}).items():
            if not (isinstance(value, str) and value.lower().endswith(MODEL_EXTS)):
                continue
            lkey = key.lower()
            base = os.path.basename(value.replace("\\", "/"))
            if lkey in PRIMARY_MODEL_KEYS or (lkey.endswith("_name") and not any(x in lkey for x in SECONDARY_MODEL_KEYS)):
                label = _match_family([base], FAMILY_RULES) or _match_family([base], [(r"xl", "SDXL")])
                if label:
                    rank = (dist.get(k, 0), -order.get(k, 0))
                    if label not in found or rank > found[label]:
                        found[label] = rank
            elif not any(x in lkey for x in ("lora", "upscale", "rife", "vfi")):
                other.append(base)
    if not found:
        # No recognizable model file: fall back to node types, then to other files.
        for k in keys:
            node = prompt.get(k)
            if isinstance(node, dict):
                label = _match_family([str(node.get("class_type", ""))], CLASS_RULES)
                if label:
                    rank = (dist.get(k, 0), -order.get(k, 0))
                    if label not in found or rank > found[label]:
                        found[label] = rank
                    break
    if not found:
        label = _match_family(other, FAMILY_RULES)
        return [label] if label else []
    return [label for label, _ in sorted(found.items(), key=lambda x: x[1], reverse=True)]


def detect_family(prompt, filename=None, workflow=None):
    families = detect_families(prompt, filename, workflow)
    return families[0] if families else None


def _json_prompts(obj, depth=0):
    """Prompt-like strings found anywhere in a JSON structure."""
    found = []
    if depth > 12:
        return found
    if isinstance(obj, dict):
        for key, value in obj.items():
            if (isinstance(value, str) and key.lower() in JSON_PROMPT_KEYS
                    and len(value.strip()) >= 12 and " " in value):
                found.append(value.strip())
            elif isinstance(value, (dict, list)):
                found.extend(_json_prompts(value, depth + 1))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(_json_prompts(value, depth + 1))
    return found


def summarize(prompt, filename=None, workflow=None):
    """Build a readable summary from an API-format prompt dict. Only the nodes
    that contributed to this file count (see used_nodes)."""
    summary = {"positive": [], "negative": [], "text": [], "seeds": [], "models": [], "loras": [],
               "family": None, "families": [], "sources": [], "v": SUMMARY_VERSION}
    if not isinstance(prompt, dict):
        return summary
    prompt = {str(k): v for k, v in prompt.items()}
    dist = used_nodes(prompt, filename, workflow)
    full_prompt = prompt
    if dist:
        # Used nodes only, earliest in the chain first (seeds and models in execution order).
        order = {k: i for i, k in enumerate(prompt)}
        prompt = {k: prompt[k] for k in sorted(dist, key=lambda k: (-dist[k], order.get(k, 0))) if k in prompt}

    def resolve_text(ref, role=None, depth=0, seen=None):
        """Follow a link back to its text. 'role' ('positive' / 'negative') keeps
        the search on the matching branch of nodes that carry both conditionings
        (PainterI2V, WanImageToVideo, ControlNet Apply, inpaint nodes and so on)."""
        if depth > 10:
            return None
        seen = seen or set()
        node_id = str(ref[0])
        if node_id in seen:
            return None
        seen.add(node_id)
        node = full_prompt.get(node_id)
        if not isinstance(node, dict):
            return None
        inputs = node.get("inputs", {}) or {}
        # Switch nodes: follow only the active branch.
        if isinstance(inputs.get("switch"), bool) and ("on_true" in inputs or "on_false" in inputs):
            branch = inputs.get("on_true" if inputs["switch"] else "on_false")
            if _is_ref(branch):
                return resolve_text(branch, role, depth + 1, seen)
            return branch if isinstance(branch, str) and branch.strip() else None
        # Encoders holding both prompts (TextEncodeQwenImage21 and similar).
        if role == "negative" and "negative_prompt" in inputs:
            value = inputs["negative_prompt"]
            if _is_ref(value):
                return resolve_text(value, role, depth + 1, seen)
            return value if isinstance(value, str) and value.strip() else None
        for key in TEXT_KEYS:
            value = inputs.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if _is_ref(value):
                found = resolve_text(value, role, depth + 1, seen)
                if found:
                    return found
        opposite = {"positive": "negative", "negative": "positive"}.get(role)
        if role and _is_ref(inputs.get(role)):
            return resolve_text(inputs[role], role, depth + 1, seen)
        for key, value in inputs.items():
            if key in TEXT_KEYS or key == opposite:
                continue
            if _is_ref(value):
                found = resolve_text(value, role, depth + 1, seen)
                if found:
                    return found
        return None

    def add_model(name, key):
        base = os.path.basename(name.replace("\\", "/"))
        if "lora" in key.lower():
            summary["loras"].append(base)
        else:
            summary["models"].append(base)

    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {}) or {}
        # A sampler with add_noise disabled (second pass of Wan 2.2, for example)
        # doesn't use its seed.
        noise_off = str(inputs.get("add_noise", "")).lower() in ("disable", "disabled", "false")
        is_loader = "load" in str(node.get("class_type", "")).lower()
        for key, value in inputs.items():
            lkey = key.lower()
            if is_loader and lkey in ("image", "video", "audio", "file") and isinstance(value, str):
                # Source file of image-to-image / video workflows ("photo.png [input]").
                src = re.sub(r"\s*\[[a-z]+\]$", "", value.strip())
                if os.path.splitext(src)[1].lower() in IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS:
                    base = os.path.basename(src.replace("\\", "/"))
                    if base not in summary["sources"]:
                        summary["sources"].append(base)
                continue
            if lkey in SEED_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool):
                if not noise_off:
                    summary["seeds"].append(int(value))
            elif isinstance(value, str) and value.lower().endswith(MODEL_EXTS):
                add_model(value, key)
            elif isinstance(value, dict):
                # rgthree Power Lora Loader style: {"on": true, "lora": "x.safetensors", ...}
                lora = value.get("lora")
                if isinstance(lora, str) and lora.lower().endswith(MODEL_EXTS) and value.get("on", True):
                    summary["loras"].append(os.path.basename(lora.replace("\\", "/")))
            elif lkey in ("positive", "negative") and _is_ref(value):
                text = resolve_text(value, lkey)
                if text:
                    summary[lkey].append(text)

    if not summary["positive"]:
        for node in prompt.values():
            if not isinstance(node, dict):
                continue
            if "textencode" in str(node.get("class_type", "")).lower():
                text = None
                inputs = node.get("inputs", {}) or {}
                for key in TEXT_KEYS:
                    value = inputs.get(key)
                    if isinstance(value, str) and value.strip():
                        text = value
                        break
                    if _is_ref(value):
                        text = resolve_text(value)
                        if text:
                            break
                if text:
                    summary["positive"].append(text)

    # Last resort for workflows without text-encoder nodes (MiniMax H3, TTS,
    # API nodes...): long text fields of the nodes themselves. Text-to-speech
    # nodes give the spoken text, shown as "Text".
    if not summary["positive"]:
        for node in prompt.values():
            if not isinstance(node, dict):
                continue
            cls = str(node.get("class_type", ""))
            spoken = bool(re.search(r"tts|speech|voice", cls, re.I))
            for key, value in (node.get("inputs") or {}).items():
                if isinstance(value, str) and value.lstrip().startswith(("{", "[")) and len(value) > 40:
                    # Project data stored as JSON (Easy-Media's MultiTrack Editor and
                    # similar): prompts are inside, under keys like "user_prompt".
                    summary["positive"].extend(_json_prompts(_loads(value)))
                    continue
                if key.lower() not in FALLBACK_TEXT_KEYS or not isinstance(value, str):
                    continue
                value = value.strip()
                if len(value) < 12 or " " not in value or value.lower().endswith(MODEL_EXTS):
                    continue
                if spoken:
                    if key.lower() != "reference_text":
                        summary["text"].append(value)
                else:
                    summary["positive"].append(value)

    for key in ("positive", "negative", "text", "seeds", "models", "loras"):
        summary[key] = _dedupe(summary[key])
    summary["families"] = detect_families(full_prompt, filename, workflow, dist)
    summary["family"] = summary["families"][0] if summary["families"] else None
    return summary


def workflow_id(workflow):
    """The UUID ComfyUI gives each workflow; all runs of one workflow share it."""
    if isinstance(workflow, dict) and isinstance(workflow.get("id"), str) and workflow["id"].strip():
        return workflow["id"].strip()
    return None


def workflow_title(workflow):
    if isinstance(workflow, dict):
        extra = workflow.get("extra") or {}
        for key in ("title", "name"):
            if isinstance(extra.get(key), str) and extra[key].strip():
                return extra[key].strip()
    return None
