"""
Segments ("parts") of videos combined from several pieces, found in the
output folder, so they can be hidden and, once the final video is in the
library, deleted.

- Easy-Media projects: exact. A project folder holds project.json, which lists
  every segment's video (all generations) and its context latent; the final
  videos are in its out/ folder, named after the project.
- Other tools: a video whose duration equals the sum of the videos made just
  before it in the same folder (2 to 12 of them, within 20 minutes), and
  whose first frame matches the first part's. Computed in the background, as
  it needs to read the videos.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time

from . import metadata as md

_FLAGS = 0x08000000 if sys.platform == "win32" else 0
_durations = {}          # (path, size, mtime) -> seconds or None
_generic = {"key": None, "groups": [], "running": False}
_lock = threading.Lock()


def _duration(path, size, mtime):
    key = (path, size, mtime)
    if key in _durations:
        return _durations[key]
    from .similarity import _duration as probe
    try:
        d = probe(path)
    except Exception:
        d = None
    _durations[key] = d
    return d


# ------------------------------------------------------------------ Easy-Media
def easy_media_groups(base, files):
    """[{final_rels: [...], parts: [{rel, index, count}], extra: [rel of latents], project}]"""
    by_rel = {f["rel"]: f for f in files}
    groups = []
    # Folders holding videos and a project.json (no second walk of the output folder).
    dirs = {os.path.dirname(f["rel"]) for f in files if f["kind"] == "video"}
    # A project whose segments are already gone still has its final in out/.
    dirs |= {os.path.dirname(d) for d in dirs if os.path.basename(d) == "out"}
    dirs = sorted(dirs)
    for rel_dir_ in dirs:
        dirpath = os.path.join(base, rel_dir_)
        if not os.path.isfile(os.path.join(dirpath, "project.json")):
            continue
        try:
            with open(os.path.join(dirpath, "project.json"), "r", encoding="utf-8") as fh:
                proj = json.load(fh)
        except Exception:
            continue
        segments = proj.get("segments") if isinstance(proj, dict) else None
        if not isinstance(segments, dict) or not segments:
            continue
        rel_dir = os.path.relpath(dirpath, base).replace("\\", "/")
        rel = (lambda name: name if rel_dir == "." else rel_dir + "/" + name)
        count = len(segments)
        parts, extra = [], []
        for key, seg in sorted(segments.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 0):
            for gen in ((seg or {}).get("generations") or {}).values():
                video = (gen or {}).get("video")
                if isinstance(video, str) and rel(video) in by_rel:
                    parts.append({"rel": rel(video), "index": int(key) + 1 if str(key).isdigit() else None, "count": count})
                latent = (gen or {}).get("context_latent")
                if isinstance(latent, str) and os.path.isfile(os.path.join(dirpath, latent)):
                    extra.append(rel(latent))
        name = str(proj.get("project_name") or os.path.basename(dirpath))
        finals = [r for r in by_rel if r.startswith(rel("out/")) and os.path.basename(r).lower().startswith(name.lower())
                  and by_rel[r]["kind"] == "video"]
        if parts or extra:
            groups.append({"kind": "easy-media", "project": name, "finals": sorted(finals, key=lambda r: by_rel[r]["mtime"]),
                           "parts": parts, "extra": extra})
    return groups


# --------------------------------------------------------------------- generic
def _generic_groups(base, files, skip):
    videos = [f for f in files if f["kind"] == "video" and f["rel"] not in skip]
    by_dir = {}
    for f in videos:
        by_dir.setdefault(os.path.dirname(f["rel"]), []).append(f)
    groups = []
    for _d, vids in by_dir.items():
        if len(vids) < 3:
            continue
        vids.sort(key=lambda f: f["mtime"])
        used = set()
        for i in range(len(vids) - 1, 1, -1):
            final = vids[i]
            if final["rel"] in used:
                continue
            fd = _duration(os.path.join(base, final["rel"]), final["size"], final["mtime"])
            if not fd:
                continue
            total, chosen = 0.0, []
            for j in range(i - 1, max(-1, i - 13), -1):
                part = vids[j]
                if part["rel"] in used or final["mtime"] - part["mtime"] > 20 * 60:
                    break
                pdur = _duration(os.path.join(base, part["rel"]), part["size"], part["mtime"])
                if not pdur or pdur >= fd:
                    break
                total += pdur
                chosen.insert(0, part)
                if len(chosen) >= 2 and abs(total - fd) <= 0.25 + 0.05 * len(chosen):
                    if _same_start(os.path.join(base, chosen[0]["rel"]), os.path.join(base, final["rel"])):
                        n = len(chosen)
                        groups.append({"kind": "generic", "project": None, "finals": [final["rel"]],
                                       "parts": [{"rel": c["rel"], "index": k + 1, "count": n} for k, c in enumerate(chosen)],
                                       "extra": []})
                        used.update(c["rel"] for c in chosen)
                        used.add(final["rel"])
                    break
                if total > fd + 1:
                    break
    return groups


def _first_frame_sig(path):
    from io import BytesIO
    from PIL import Image
    from .similarity import _image_sig
    exe = md.ffmpeg_exe()
    if not exe:
        return None
    out = subprocess.run([exe, "-v", "error", "-ss", "0.05", "-i", path, "-frames:v", "1", "-vf", "scale=128:-2",
                          "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, timeout=30, creationflags=_FLAGS).stdout
    if not out:
        return None
    with Image.open(BytesIO(out)) as img:
        return _image_sig(img)


def _same_start(part_path, final_path):
    from .similarity import _image_score
    try:
        a, b = _first_frame_sig(part_path), _first_frame_sig(final_path)
        return bool(a and b and _image_score(a, b) >= 0.85)
    except Exception:
        return False


# ------------------------------------------------------------------------ all
def groups(base, files):
    """Groups of parts found in a listing of the output folder. Easy-Media at
    once; the generic detection comes from the last background run (started
    here when the listing changed)."""
    em = easy_media_groups(base, files)
    skip = {p["rel"] for g in em for p in g["parts"]} | {r for g in em for r in g["finals"]}
    key = hash(tuple(sorted((f["rel"], f["size"], f["mtime"]) for f in files if f["kind"] == "video")))
    with _lock:
        gen = list(_generic["groups"])
        if _generic["key"] != key and not _generic["running"]:
            _generic["running"] = True

            def work():
                t0 = time.time()
                try:
                    found = _generic_groups(base, files, skip)
                except Exception:
                    found = []
                with _lock:
                    _generic.update({"key": key, "groups": found, "running": False})
                if found:
                    print("[My Own Library] Combined videos found in output: %d (in %.0f s)" % (len(found), time.time() - t0), flush=True)

            threading.Thread(target=work, daemon=True).start()
    gen = [g for g in gen if not any(p["rel"] in skip for p in g["parts"])]
    return em + gen


def annotate(base, files):
    """Add "part" ({index, count, project}) to segment files and "parts" (count)
    to final videos. Returns the groups."""
    found = groups(base, files)
    by_rel = {f["rel"]: f for f in files}
    for g in found:
        for p in g["parts"]:
            f = by_rel.get(p["rel"])
            if f:
                f["part"] = {"index": p["index"], "count": p["count"], "project": g["project"]}
        for r in g["finals"]:
            if r in by_rel:
                by_rel[r]["parts"] = len({p["index"] for p in g["parts"]}) or len(g["parts"])
    return found


# ------------------------------------------------------------- in the library
# Segments that were added to the library before (or without) being hidden:
# recognized by the path they came from (Easy-Media) or by their lengths.
_lib_generic = {"key": None, "groups": [], "running": False}
_EM_PART = re.compile(r"^(?P<proj>.+)/video_(?P<seg>\d+)_(?P<gen>\d+)\.[a-z0-9]+$", re.I)
_EM_FINAL = re.compile(r"^(?P<proj>.+)/out/[^/]+$", re.I)


def _ts(iso):
    from datetime import datetime
    try:
        return datetime.fromisoformat(iso).timestamp()
    except Exception:
        return 0.0


def library_groups(lib_dir, items, output_base):
    """[{kind, project, finals: [item ids], parts: [{id, index, count}]}] among
    the library's items (dicts with id, kind, source, file, created, sig)."""
    projects = {}
    for it in items:
        src = it.get("source") or {}
        if src.get("root") != "output" or it.get("kind") != "video":
            continue
        rel = src.get("rel") or ""
        m = _EM_PART.match(rel)
        if m:
            projects.setdefault(m.group("proj"), {"parts": [], "finals": []})["parts"].append((it, int(m.group("seg"))))
            continue
        m = _EM_FINAL.match(rel)
        if m and os.path.basename(rel).lower().startswith(os.path.basename(m.group("proj")).lower()):
            projects.setdefault(m.group("proj"), {"parts": [], "finals": []})["finals"].append(it)
    groups, used = [], set()
    for proj, g in projects.items():
        if not g["parts"]:
            continue
        count = None
        pj = os.path.join(output_base, proj, "project.json")
        if os.path.isfile(pj):
            try:
                with open(pj, "r", encoding="utf-8") as fh:
                    count = len((json.load(fh) or {}).get("segments") or {}) or None
            except Exception:
                pass
        if not g["finals"] and count is None:
            continue  # no proof it's a project: leave these videos alone
        count = count or max(seg for _it, seg in g["parts"]) + 1
        groups.append({"kind": "easy-media", "project": os.path.basename(proj),
                       "finals": [f["id"] for f in sorted(g["finals"], key=lambda f: f.get("created", ""))],
                       "parts": [{"id": it["id"], "index": seg + 1, "count": count} for it, seg in g["parts"]]})
        used.update(it["id"] for it, _s in g["parts"])
        used.update(f["id"] for f in g["finals"])

    # Generic: from the cache of the last background run.
    key = hash(tuple(sorted((i["id"], i.get("file")) for i in items if i.get("kind") == "video")))
    with _lock:
        gen = list(_lib_generic["groups"])
        if _lib_generic["key"] != key and not _lib_generic["running"]:
            _lib_generic["running"] = True
            todo = [dict(i) for i in items if i.get("kind") == "video" and i["id"] not in used]

            def work():
                try:
                    found = _library_generic(lib_dir, todo)
                except Exception:
                    found = []
                with _lock:
                    _lib_generic.update({"key": key, "groups": found, "running": False})

            threading.Thread(target=work, daemon=True).start()
    present = {i["id"] for i in items}
    gen = [g for g in gen if all(p["id"] in present and p["id"] not in used for p in g["parts"])
           and all(f in present for f in g["finals"])]
    return groups + gen


def _library_generic(lib_dir, videos):
    by_dir = {}
    for it in videos:
        src = it.get("source") or {}
        by_dir.setdefault((src.get("root"), os.path.dirname(src.get("rel") or "")), []).append(it)
    out = []
    for _d, vids in by_dir.items():
        if len(vids) < 3:
            continue
        vids.sort(key=lambda i: i.get("created", ""))
        dur = lambda i: (i.get("sig") or {}).get("dur") or 0
        used = set()
        for k in range(len(vids) - 1, 1, -1):
            final = vids[k]
            fd = dur(final)
            if not fd or final["id"] in used:
                continue
            total, chosen = 0.0, []
            for j in range(k - 1, max(-1, k - 13), -1):
                part = vids[j]
                pd = dur(part)
                if part["id"] in used or not pd or pd >= fd or _ts(final.get("created")) - _ts(part.get("created")) > 20 * 60:
                    break
                total += pd
                chosen.insert(0, part)
                if len(chosen) >= 2 and abs(total - fd) <= 0.25 + 0.05 * len(chosen):
                    if _same_start(os.path.join(lib_dir, chosen[0]["file"]), os.path.join(lib_dir, final["file"])):
                        n = len(chosen)
                        out.append({"kind": "generic", "project": None, "finals": [final["id"]],
                                    "parts": [{"id": c["id"], "index": x + 1, "count": n} for x, c in enumerate(chosen)]})
                        used.update(c["id"] for c in chosen)
                        used.add(final["id"])
                    break
                if total > fd + 1:
                    break
    return out
