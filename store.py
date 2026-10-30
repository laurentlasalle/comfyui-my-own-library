"""
Library storage.

Layout of the library folder (portable: move the whole folder and update
the config file to point at it):

    library.json            items, categories, tag list
    files/YYYY-MM/<id>.ext  copies of your creations
    files/YYYY-MM/<id>.png  companion PNG of a video, when one existed
    meta/<id>.json          full "prompt" and "workflow" of the creation
    thumbs/<id>.jpg         thumbnail of a library item
    cache/<hash>.jpg        thumbnails of files still in the output folder
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime

from . import metadata as md
from . import similarity as sim
from . import dupes
from . import faces
from .version import __version__

THUMB_SIZE = 512
THUMB_VERSION = 2  # 2: video thumbnails skip black first frames


def _say(text):
    print("[My Own Library] " + text, flush=True)
SHARED_FIELDS = ("title", "category", "tags", "favorite")
LIBRARY_VERSION = 1


def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _iso_from_ts(ts):
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _safe_join(root, rel):
    """Join rel to root and refuse anything that escapes root."""
    root = os.path.realpath(root)
    full = os.path.realpath(os.path.join(root, rel))
    if full != root and not full.startswith(root + os.sep):
        raise ValueError("Path outside of allowed folder")
    return full


def _ffmpeg():
    return md.ffmpeg_exe()


def brightness(path):
    """Average brightness of an image, 0 (black) to 255."""
    from PIL import Image
    with Image.open(path) as img:
        small = img.convert("L").resize((32, 32))
        data = list(small.getdata())
    return sum(data) / len(data)


DARK = 24  # below this average brightness, a frame is considered black


def _video_frame(src, dest):
    """A representative frame of a video, as an image path: the companion PNG
    or a frame near the start, unless it is (nearly) black, in which case
    frames further in are tried. Returns (path, temp_path_to_delete)."""
    candidates = []
    comp = md.companion_png(src)
    if comp:
        candidates.append(("file", comp))
    candidates += [("seek", 0.5), ("seek", 0)]
    exe = _ffmpeg()
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    tmp = dest + ".frame.png"
    best, best_light, later_added = None, -1, False
    i = 0
    while i < len(candidates):
        how, where = candidates[i]
        i += 1
        path = where if how == "file" else None
        if how == "seek":
            if not exe:
                continue
            out = "%s.%d.png" % (tmp, i)
            try:
                subprocess.run([exe, "-y", "-loglevel", "error", "-ss", str(where), "-i", src, "-frames:v", "1", out],
                               timeout=30, check=True, creationflags=flags,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                continue
            if not os.path.isfile(out):
                continue
            path = out
        try:
            light = brightness(path)
        except Exception:
            continue
        if light > best_light:
            if best and best != comp:
                try:
                    os.remove(best)
                except OSError:
                    pass
            best, best_light = path, light
        elif path != comp:
            try:
                os.remove(path)
            except OSError:
                pass
        if best_light >= DARK:
            break
        if not later_added and exe:
            # Dark start: look further into the video.
            later_added = True
            from .similarity import _duration
            duration = _duration(src) or 0
            for t in (1, 2, 4):
                if not duration or t < duration:
                    candidates.append(("seek", t))
            for frac in (0.1, 0.25, 0.5):
                if duration:
                    candidates.append(("seek", round(duration * frac, 2)))
    if not best:
        return None, None
    return best, (None if best == comp else best)


def make_thumbnail(src, dest, kind):
    """Create a JPEG thumbnail. Returns (ok, width, height) of the source image."""
    from PIL import Image, ImageOps

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if kind == "audio":
        return _waveform(src, dest)
    if kind == "video":
        frame, temp = _video_frame(src, dest)
        if not frame:
            return False, None, None
        try:
            return make_thumbnail(frame, dest, "image")
        finally:
            if temp:
                try:
                    os.remove(temp)
                except OSError:
                    pass
    with Image.open(src) as img:
        width, height = img.size
        img.seek(0)
        img = ImageOps.exif_transpose(img)
        img.thumbnail((THUMB_SIZE, THUMB_SIZE))
        if img.mode not in ("RGB", "L"):
            background = Image.new("RGB", img.size, (24, 24, 24))
            rgba = img.convert("RGBA")
            background.paste(rgba, mask=rgba.split()[-1])
            img = background
        img.convert("RGB").save(dest, "JPEG", quality=84)
    return True, width, height


def _waveform(src, dest):
    """Thumbnail of an audio file: its waveform, drawn by ffmpeg."""
    from PIL import Image
    exe = _ffmpeg()
    if not exe:
        return False, None, None
    tmp = dest + ".wave.png"
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    try:
        subprocess.run(
            [exe, "-y", "-loglevel", "error", "-i", src, "-filter_complex",
             "aformat=channel_layouts=mono,showwavespic=s=1024x420:colors=#f0cf98:scale=sqrt",
             "-frames:v", "1", tmp],
            timeout=60, check=True, creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with Image.open(tmp) as wave:
            wave = wave.convert("RGBA")
            canvas = Image.new("RGB", (THUMB_SIZE, THUMB_SIZE), (29, 29, 29))
            wave.thumbnail((THUMB_SIZE - 40, THUMB_SIZE))
            canvas.paste(wave, ((THUMB_SIZE - wave.width) // 2, (THUMB_SIZE - wave.height) // 2), wave)
            canvas.save(dest, "JPEG", quality=84)
        return True, None, None
    except Exception:
        return False, None, None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


class Library:
    def __init__(self, library_dir, roots):
        """
        library_dir: where copies and data live.
        roots: {"output": path, "temp": path, "input": path} folders files may be added from.
        """
        self.dir = os.path.abspath(library_dir)
        self.roots = {k: os.path.abspath(v) for k, v in roots.items() if v}
        self.lock = threading.RLock()
        self._pair_cache = {}
        for sub in ("files", "meta", "thumbs", "cache"):
            os.makedirs(os.path.join(self.dir, sub), exist_ok=True)
        self.db_path = os.path.join(self.dir, "library.json")
        self.data = self._load()
        self._families_path = os.path.join(self.dir, "cache", "families.json")
        self._families = self._load_families()
        self._refresh_summaries()
        # Similarity signatures of creations added before this feature: computed
        # in the background, so opening the library is never slowed down.
        threading.Thread(target=self._backfill_signatures, daemon=True).start()

    # ------------------------------------------------------------------ io
    def _load(self):
        if os.path.isfile(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data.setdefault("categories", [])
                data.setdefault("items", {})
                data.setdefault("version", LIBRARY_VERSION)
                data.setdefault("output_seen", time.time())
                if not isinstance(data.get("dismissed_suggestions"), dict):
                    data["dismissed_suggestions"] = {}
                return data
            except Exception:
                backup = self.db_path + ".broken-%d" % int(time.time())
                shutil.copy2(self.db_path, backup)
        # output_seen starts now, so files generated before installation don't count as new.
        return {"version": LIBRARY_VERSION, "categories": [], "items": {}, "output_seen": time.time(),
                "dismissed_suggestions": {}}

    def _backfill_signatures(self):
        """Similarity signatures and duplicate fingerprints of creations added
        before these features, computed once; then the video thumbnail check."""
        todo = [i["id"] for i in self.data["items"].values()
                if i.get("sig_v") != sim.SIG_VERSION or i.get("hash_v") != dupes.HASH_VERSION]
        if todo:
            _say("Analyzing %d creation%s for similarity and duplicates, in the background"
                 % (len(todo), "s" if len(todo) > 1 else ""))
        t0 = time.time()
        for n, item_id in enumerate(todo, 1):
            item = self.get(item_id)
            if not item:
                continue
            path = self.item_path(item)
            update = {}
            if item.get("sig_v") != sim.SIG_VERSION:
                try:
                    thumb = os.path.join(self.dir, "thumbs", item_id + ".jpg")
                    update["sig"] = sim.signature(path, item["kind"], thumb)
                except Exception:
                    update["sig"] = None
                update["sig_v"] = sim.SIG_VERSION
            if item.get("hash_v") != dupes.HASH_VERSION:
                update.update(dupes.fingerprints(path, item["kind"]))
            with self.lock:
                if item_id in self.data["items"]:
                    item.update(update)
                if n % 20 == 0 or n == len(todo):
                    self._save()
        if todo:
            _say("Similarity and duplicates analysis done: %d creation%s in %.0f s"
                 % (len(todo), "s" if len(todo) > 1 else "", time.time() - t0))
        self._check_video_thumbnails()
        self._compute_focus()

    def _compute_focus(self):
        """Point of interest (face) of thumbnails made before this feature, once."""
        todo = [i["id"] for i in self.data["items"].values()
                if i.get("focus_v") != faces.FOCUS_VERSION and i.get("kind") in ("image", "video")]
        if not todo:
            return
        _say("Looking for faces in %d thumbnail%s, in the background%s" % (
            len(todo), "s" if len(todo) > 1 else "",
            "" if faces.opencv_available() else " (OpenCV not found: portrait framing only)"))
        found = 0
        for n, item_id in enumerate(todo, 1):
            thumb = os.path.join(self.dir, "thumbs", item_id + ".jpg")
            point = faces.focus_point(thumb) if os.path.isfile(thumb) else None
            with self.lock:
                item = self.data["items"].get(item_id)
                if item:
                    item["focus"] = point
                    item["focus_v"] = faces.FOCUS_VERSION
                if n % 50 == 0 or n == len(todo):
                    self._save()
            if point and point.get("face"):
                found += 1
        _say("Faces found in %d of %d thumbnails" % (found, len(todo)))
    def _check_video_thumbnails(self):
        """Redo the automatic thumbnails of videos that start in black, once.
        Thumbnails chosen by hand are never touched."""
        todo = [i["id"] for i in self.data["items"].values()
                if i.get("kind") == "video" and not i.get("thumb_custom") and i.get("thumb_v") != THUMB_VERSION]
        if not todo:
            return
        _say("Checking %d video thumbnail%s in the background" % (len(todo), "s" if len(todo) > 1 else ""))
        redone = 0
        for item_id in todo:
            item = self.get(item_id)
            if not item or item.get("thumb_custom"):
                continue
            thumb = os.path.join(self.dir, "thumbs", item_id + ".jpg")
            changed = False
            try:
                dark = not os.path.isfile(thumb) or brightness(thumb) < DARK
                if dark:
                    ok, _, _ = make_thumbnail(self.item_path(item), thumb, "video")
                    if ok and brightness(thumb) >= DARK:
                        changed = True
                        redone += 1
                        _say("  new thumbnail (first frames too dark): %s" % item.get("title", item_id))
            except Exception:
                pass
            with self.lock:
                if item_id in self.data["items"] and not item.get("thumb_custom"):
                    item["thumb_v"] = THUMB_VERSION
                    if changed:
                        item["modified"] = _now_iso()  # the window reloads the thumbnail
                        item.pop("focus_v", None)      # its face is looked for again
        with self.lock:
            self._save()
        _say("Video thumbnails checked: %d too dark, redone" % redone)

    # ------------------------------------------------------------ thumbnails
    def set_thumbnail(self, item_id, image_bytes, at=None):
        """Use an image (a frame chosen in the window) as the thumbnail."""
        import io
        from PIL import Image
        item = self.get(item_id)
        if not item:
            raise KeyError(item_id)
        tmp = os.path.join(self.dir, "thumbs", item_id + ".new.png")
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.convert("RGB").save(tmp)
        try:
            ok, _, _ = make_thumbnail(tmp, os.path.join(self.dir, "thumbs", item_id + ".jpg"), "image")
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        if not ok:
            raise ValueError("Could not make the thumbnail")
        point = faces.focus_point(os.path.join(self.dir, "thumbs", item_id + ".jpg"))
        with self.lock:
            item["focus"] = point
            item["focus_v"] = faces.FOCUS_VERSION
            item["thumb_custom"] = {"time": at}
            item["modified"] = _now_iso()
            self._save()
            return dict(item)

    def reset_thumbnail(self, item_id):
        """Back to the automatic thumbnail."""
        item = self.get(item_id)
        if not item:
            raise KeyError(item_id)
        ok, _, _ = make_thumbnail(self.item_path(item), os.path.join(self.dir, "thumbs", item_id + ".jpg"), item["kind"])
        point = faces.focus_point(os.path.join(self.dir, "thumbs", item_id + ".jpg")) if ok else None
        with self.lock:
            item["focus"] = point
            item["focus_v"] = faces.FOCUS_VERSION
            item.pop("thumb_custom", None)
            item["thumb_v"] = THUMB_VERSION
            item["modified"] = _now_iso()
            self._save()
            return dict(item)

    def _refresh_summaries(self):
        """Bring items added by an older version up to date: summary (prompt
        tracing, seeds, model family) and workflow id. Items whose metadata
        could not be read at the time are read again from their library copy."""
        changed = False
        with self.lock:
            for item in self.data["items"].values():
                if (item.get("summary") or {}).get("v", 1) >= md.SUMMARY_VERSION and "workflow_id" in item:
                    continue
                try:
                    meta = self.meta(item["id"])
                    if meta.get("prompt") is None and meta.get("workflow") is None:
                        prompt, workflow = md.extract(self.item_path(item))
                        if prompt is not None or workflow is not None:
                            meta = {"prompt": prompt, "workflow": workflow}
                            _atomic_write_json(os.path.join(self.dir, "meta", item["id"] + ".json"), meta)
                    item["summary"] = md.summarize(meta.get("prompt"), (item.get("source") or {}).get("name"),
                                                   meta.get("workflow"))
                    item["has_prompt"] = meta.get("prompt") is not None
                    item["has_workflow"] = meta.get("workflow") is not None
                    item["workflow_id"] = md.workflow_id(meta.get("workflow"))
                    item.setdefault("work_id", None)
                    changed = True
                except Exception:
                    pass
            if changed:
                self._save()

    # Families of files still in the output folder, cached by path, size and date.
    def _load_families(self):
        try:
            with open(self._families_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def file_families(self, files):
        """Add a 'families' key to each listed output file (reads metadata once per file)."""
        changed = False
        for f in files:
            key = "v%s|%s|%s|%s|%s" % (md.SUMMARY_VERSION, f["root"], f["rel"], f["size"], f["mtime"])
            if key not in self._families:
                try:
                    path = self.root_path(f["root"], f["rel"])
                    prompt, workflow = md.extract(path)
                    self._families[key] = md.detect_families(prompt, path, workflow)
                except Exception:
                    self._families[key] = None
                changed = True
            f["families"] = self._families[key] or []
        if changed:
            try:
                _atomic_write_json(self._families_path, self._families)
            except Exception:
                pass
        return files

    def _save(self):
        if getattr(self, "closed", False):
            return  # this folder is no longer the library (moved or switched)
        _atomic_write_json(self.db_path, self.data)

    # ------------------------------------------------------------- queries
    def snapshot(self):
        with self.lock:
            items = sorted(self.data["items"].values(), key=lambda i: i.get("added", ""), reverse=True)
            # Similarity signatures stay on the server; the window doesn't need them.
            items = [{k: v for k, v in i.items() if k not in ("sig", "sig_v", "sha", "chash", "hash_v")}
                     for i in items]
            return {
                "library_dir": self.dir,
                "version": __version__,
                "categories": list(self.data["categories"]),
                "items": items,
                "duplicates": self.duplicates(),
            }

    def get(self, item_id):
        with self.lock:
            return self.data["items"].get(item_id)

    def source_index(self):
        """Map 'root|rel|size' to item id, to flag output files already in the library."""
        with self.lock:
            index = {}
            for item in self.data["items"].values():
                # Output files skipped or merged as duplicates of this creation
                # count as in the library too.
                for src in item.get("also", []):
                    index["%s|%s|%s" % (src.get("root"), src.get("rel"), src.get("size"))] = item["id"]
            for item in self.data["items"].values():
                src = item.get("source") or {}
                index["%s|%s|%s" % (src.get("root"), src.get("rel"), src.get("size"))] = item["id"]
            return index

    def _find_duplicate(self, fp):
        with self.lock:
            for item in self.data["items"].values():
                if fp.get("sha") and item.get("sha") == fp["sha"]:
                    return item
                if fp.get("chash") and item.get("chash") == fp["chash"]:
                    return item
        return None

    def item_path(self, item, part="main"):
        rel = item.get("file") if part == "main" else item.get("companion")
        if not rel:
            return None
        return _safe_join(self.dir, rel)

    def meta(self, item_id):
        path = os.path.join(self.dir, "meta", item_id + ".json")
        if not os.path.isfile(path):
            return {"prompt": None, "workflow": None}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # -------------------------------------------------------------- output
    def list_root(self, root="output"):
        base = self.roots.get(root)
        if not base or not os.path.isdir(base):
            return []
        index = self.source_index()
        lib_real = os.path.realpath(self.dir)
        files = []
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".")
                           and os.path.realpath(os.path.join(dirpath, d)) != lib_real]
            names = set(filenames)
            for name in filenames:
                kind = md.kind_of(name)
                if not kind:
                    continue
                stem, ext = os.path.splitext(name)
                # Hide the companion PNG of a video saved by VideoHelperSuite.
                if ext.lower() == ".png" and any((stem + v) in names for v in md.VIDEO_EXTS):
                    continue
                full = os.path.join(dirpath, name)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                rel = os.path.relpath(full, base).replace("\\", "/")
                files.append({
                    "root": root,
                    "rel": rel,
                    "name": name,
                    "kind": kind,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                    "created": _iso_from_ts(st.st_mtime),
                    "in_library": index.get("%s|%s|%s" % (root, rel, st.st_size)),
                })
        files.sort(key=lambda f: f["mtime"], reverse=True)
        return files

    # ------------------------------------------------------------ new files
    def output_seen(self):
        with self.lock:
            return float(self.data.get("output_seen") or 0)

    def mark_output_seen(self):
        """Record a visit of the Output view. Returns the previous visit time."""
        with self.lock:
            previous = float(self.data.get("output_seen") or 0)
            self.data["output_seen"] = time.time()
            self._save()
            return previous

    def count_new(self):
        """Output files created since the last visit and not yet in the library."""
        since = self.output_seen()
        files = self.list_root("output")
        try:
            # Segments of combined videos don't count: only the final video does.
            from . import parts
            parts.annotate(self.roots["output"], files)
        except Exception:
            pass
        return sum(1 for f in files if f["mtime"] > since and not f["in_library"] and not f.get("part"))

    def root_path(self, root, rel):
        base = self.roots.get(root)
        if not base:
            raise ValueError("Unknown folder: %s" % root)
        return _safe_join(base, rel)

    def cache_thumbnail(self, root, rel):
        """Thumbnail of a file in output/temp, cached by path, size and date."""
        full = self.root_path(root, rel)
        st = os.stat(full)
        key = hashlib.sha1(("%s|%s|%s|%s" % (root, rel, st.st_size, st.st_mtime)).encode()).hexdigest()
        dest = os.path.join(self.dir, "cache", key + ".jpg")
        if os.path.isfile(dest):
            return dest
        ok, _, _ = make_thumbnail(full, dest, md.kind_of(full))
        return dest if ok else None

    def inspect(self, root, rel):
        full = self.root_path(root, rel)
        prompt, workflow = md.extract(full)
        st = os.stat(full)
        return {
            "root": root, "rel": rel, "name": os.path.basename(full),
            "kind": md.kind_of(full), "size": st.st_size,
            "created": _iso_from_ts(st.st_mtime),
            "summary": md.summarize(prompt, full, workflow),
            "has_workflow": workflow is not None, "has_prompt": prompt is not None,
            "in_library": self.source_index().get("%s|%s|%s" % (root, rel, st.st_size)),
        }

    # ----------------------------------------------------------- mutations
    def add(self, root, rel, category="", tags=None, title=None, allow_duplicates=False):
        """Copy a file into the library. Returns (item, status): status is True
        when added, False when this file was already in, "duplicate" when an
        identical creation is already in (the file is then linked to it)."""
        full = self.root_path(root, rel)
        if not os.path.isfile(full):
            raise FileNotFoundError(rel)
        kind = md.kind_of(full)
        if not kind:
            raise ValueError("Unsupported file type: %s" % rel)
        st = os.stat(full)
        key = "%s|%s|%s" % (root, rel, st.st_size)
        if allow_duplicates:
            # Added on purpose: this file no longer stands for another creation.
            with self.lock:
                for item in self.data["items"].values():
                    if item.get("also"):
                        item["also"] = [a for a in item["also"] if (a.get("root"), a.get("rel")) != (root, rel)]
        existing = self.source_index().get(key)
        if existing:
            return self.get(existing), False

        fp = dupes.fingerprints(full, kind)
        if not allow_duplicates:
            twin = self._find_duplicate(fp)
            if twin:
                with self.lock:
                    twin.setdefault("also", []).append(
                        {"root": root, "rel": rel, "size": st.st_size, "name": os.path.basename(full)})
                    self._save()
                return twin, "duplicate"

        item_id = uuid.uuid4().hex[:12]
        ext = os.path.splitext(full)[1].lower()
        month = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m")
        rel_main = "files/%s/%s%s" % (month, item_id, ext)
        dest = _safe_join(self.dir, rel_main)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(full, dest)

        rel_comp = None
        comp = md.companion_png(full)
        if comp:
            rel_comp = "files/%s/%s.png" % (month, item_id)
            shutil.copy2(comp, _safe_join(self.dir, rel_comp))

        prompt, workflow = md.extract(full)
        _atomic_write_json(os.path.join(self.dir, "meta", item_id + ".json"),
                           {"prompt": prompt, "workflow": workflow})

        thumb = os.path.join(self.dir, "thumbs", item_id + ".jpg")
        try:
            has_thumb, width, height = make_thumbnail(dest, thumb, kind)
        except Exception:
            has_thumb, width, height = False, None, None

        item = {
            "id": item_id,
            "title": (title or os.path.splitext(os.path.basename(full))[0]).strip(),
            "category": category or "",
            "tags": self._clean_tags(tags or []),
            "notes": "",
            "favorite": False,
            "kind": kind,
            "ext": ext,
            "file": rel_main,
            "companion": rel_comp,
            "size": st.st_size,
            "width": width,
            "height": height,
            "has_thumb": has_thumb,
            "created": _iso_from_ts(st.st_mtime),
            "added": _now_iso(),
            "modified": _now_iso(),
            "source": {"root": root, "rel": rel, "size": st.st_size, "name": os.path.basename(full)},
            "summary": md.summarize(prompt, full, workflow),
            "has_workflow": workflow is not None,
            "has_prompt": prompt is not None,
            "workflow_id": md.workflow_id(workflow),
            "work_id": None,
            "sig": sim.signature(dest, kind, thumb),
            "sig_v": sim.SIG_VERSION,
            "thumb_v": THUMB_VERSION,
            "focus": faces.focus_point(thumb) if has_thumb else None,
            "focus_v": faces.FOCUS_VERSION,
            **fp,
        }
        with self.lock:
            if item["category"] and item["category"] not in self.data["categories"]:
                self.data["categories"].append(item["category"])
            self.data["items"][item_id] = item
            self._save()
        return item, True

    @staticmethod
    def _clean_tags(tags):
        out, seen = [], set()
        for tag in tags:
            if not isinstance(tag, str):
                continue
            tag = " ".join(tag.strip().strip(",").split())
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                out.append(tag)
        return out

    def update(self, item_id, fields):
        allowed = {"title", "category", "tags", "notes", "favorite", "family_override"}
        with self.lock:
            item = self.data["items"].get(item_id)
            if not item:
                raise KeyError(item_id)
            for key, value in fields.items():
                if key not in allowed:
                    continue
                if key == "tags":
                    value = self._clean_tags(value if isinstance(value, list) else [])
                elif key == "favorite":
                    value = bool(value)
                elif key == "family_override":
                    value = " ".join(str(value or "").split())
                elif key == "title":
                    value = str(value).strip() or item["title"]
                else:
                    value = str(value or "")
                item[key] = value
            if item.get("category") and item["category"] not in self.data["categories"]:
                self.data["categories"].append(item["category"])
            item["modified"] = _now_iso()
            # Title, category, tags and favorite belong to the whole work.
            if item.get("work_id"):
                for other in self._members(item["work_id"]):
                    if other is item:
                        continue
                    for key in SHARED_FIELDS:
                        if key in fields:
                            other[key] = item[key]
                    other["modified"] = item["modified"]
            self._save()
            return item

    def remove(self, item_id):
        with self.lock:
            item = self.data["items"].pop(item_id, None)
            if not item:
                raise KeyError(item_id)
            if item.get("work_id"):
                self._dissolve_if_single(item["work_id"])
            self._save()
        freed = 0
        for path in (self.item_path(item, "main"), self.item_path(item, "companion"),
                     os.path.join(self.dir, "meta", item_id + ".json"),
                     os.path.join(self.dir, "thumbs", item_id + ".jpg")):
            if path and os.path.isfile(path):
                try:
                    freed += os.path.getsize(path)
                    os.remove(path)
                except OSError:
                    pass
        return freed

    def update_many(self, ids, category=None, add_tags=None):
        """Bulk edit: move to a category and/or add tags (shared with versions)."""
        with self.lock:
            for item_id in ids:
                item = self.data["items"].get(item_id)
                if not item:
                    continue
                fields = {}
                if category is not None:
                    fields["category"] = category
                if add_tags:
                    fields["tags"] = list(item.get("tags", [])) + list(add_tags)
                if fields:
                    self.update(item_id, fields)

    def category(self, action, name="", new_name="", order=None):
        with self.lock:
            cats = self.data["categories"]
            name = (name or "").strip()
            new_name = (new_name or "").strip()
            if action == "create":
                if not name:
                    raise ValueError("Empty name")
                if name.lower() not in (c.lower() for c in cats):
                    cats.append(name)
            elif action == "rename":
                if name not in cats or not new_name:
                    raise ValueError("Unknown category or empty name")
                if new_name.lower() in (c.lower() for c in cats if c != name):
                    raise ValueError("A category with that name already exists")
                cats[cats.index(name)] = new_name
                for item in self.data["items"].values():
                    if item.get("category") == name:
                        item["category"] = new_name
            elif action == "delete":
                if name in cats:
                    cats.remove(name)
                for item in self.data["items"].values():
                    if item.get("category") == name:
                        item["category"] = ""
            elif action == "reorder":
                if isinstance(order, list) and sorted(order) == sorted(cats):
                    self.data["categories"] = list(order)
            else:
                raise ValueError("Unknown action")
            self._save()
            return list(self.data["categories"])

    # ------------------------------------------------------------ output cleanup
    def delete_from_output(self, root, rel):
        """Permanently delete an output file that is safely in the library.
        Returns the number of bytes freed. Refuses anything else."""
        if root != "output":
            raise ValueError("Only files of the output folder can be deleted")
        full = self.root_path(root, rel)
        if not os.path.isfile(full):
            raise FileNotFoundError(rel)
        size = os.path.getsize(full)
        item_id = self.source_index().get("%s|%s|%s" % (root, rel, size))
        item = self.get(item_id) if item_id else None
        if not item:
            raise ValueError("Not in the library: %s" % rel)
        copy = self.item_path(item)
        src = item.get("source") or {}
        if (src.get("root"), src.get("rel")) == (root, rel):
            if not copy or not os.path.isfile(copy) or os.path.getsize(copy) != size:
                raise ValueError("The library copy of %s is missing or incomplete, nothing deleted" % rel)
        else:
            # A duplicate of this creation: check it really has the same content.
            if not copy or not os.path.isfile(copy):
                raise ValueError("The library copy of %s is missing, nothing deleted" % rel)
            fp = dupes.fingerprints(full, item["kind"])
            same = (fp["sha"] and fp["sha"] == item.get("sha")) or (fp["chash"] and fp["chash"] == item.get("chash"))
            if not same:
                raise ValueError("%s no longer matches its library copy, nothing deleted" % rel)
        freed = 0
        comp = md.companion_png(full)
        os.remove(full)
        freed += size
        if comp and (not item.get("companion") or os.path.isfile(self.item_path(item, "companion"))):
            try:
                freed += os.path.getsize(comp)
                os.remove(comp)
            except OSError:
                pass
        return freed

    # ---------------------------------------------------------------- duplicates
    def duplicates(self):
        """Groups of identical creations (same file, or same content), oldest first."""
        with self.lock:
            groups = {}
            owner = {}
            for item in self.data["items"].values():
                keys = [k for k in (item.get("chash") and "c:" + item["chash"],
                                    item.get("sha") and "s:" + item["sha"]) if k]
                gid = next((owner[k] for k in keys if k in owner), None)
                if gid is None:
                    gid = item["id"]
                    groups[gid] = []
                groups[gid].append(item)
                for k in keys:
                    owner.setdefault(k, gid)
            out = []
            for members in groups.values():
                if len(members) > 1:
                    members.sort(key=lambda m: (m.get("created", ""), m.get("added", "")))
                    out.append([m["id"] for m in members])
            return out

    def merge_duplicates(self, ids):
        """Keep one creation of a group of identical ones; the others leave the
        library (their output files stay linked to the one kept). Returns the
        id kept."""
        with self.lock:
            group = [self.data["items"][i] for i in ids if i in self.data["items"]]
            if len(group) < 2:
                raise ValueError("Nothing to merge")
            stems = {os.path.splitext((m.get("source") or {}).get("name", ""))[0] for m in group}

            def custom_title(m):
                return bool(m.get("title")) and m["title"] not in stems
            # Keep a version of a work if there is one, else the first added.
            keep = (next((m for m in group if m.get("work_id")), None)
                    or min(group, key=lambda m: m.get("added", "")))
            others = [m for m in group if m is not keep]
            fields = {}
            tags = list(keep.get("tags", []))
            for m in others:
                tags += [t for t in m.get("tags", []) if t.lower() not in (x.lower() for x in tags)]
            if tags != keep.get("tags", []):
                fields["tags"] = tags
            notes = []
            for m in [keep] + others:
                n = (m.get("notes") or "").strip()
                if n and n not in notes:
                    notes.append(n)
            if "\n\n".join(notes) != (keep.get("notes") or "").strip():
                fields["notes"] = "\n\n".join(notes)
            if not keep.get("favorite") and any(m.get("favorite") for m in others):
                fields["favorite"] = True
            if not keep.get("category"):
                cat = next((m["category"] for m in others if m.get("category")), "")
                if cat:
                    fields["category"] = cat
            if not keep.get("work_id") and not custom_title(keep):
                named = next((m for m in others if custom_title(m)), None)
                if named:
                    fields["title"] = named["title"]
            # The oldest date is the real time of creation.
            keep["created"] = min(m.get("created", "") for m in group) or keep.get("created")
            also = {(a.get("root"), a.get("rel")): a for a in keep.get("also", [])}
            for m in others:
                src = m.get("source") or {}
                for a in [src] + m.get("also", []):
                    if a.get("rel"):
                        also.setdefault((a.get("root"), a.get("rel")), {k: a.get(k) for k in ("root", "rel", "size", "name")})
            mine = keep.get("source") or {}
            also.pop((mine.get("root"), mine.get("rel")), None)
            keep["also"] = list(also.values())
            if fields:
                self.update(keep["id"], fields)
            self._save()
        for m in others:
            self.remove(m["id"])
        return keep["id"]

    # ------------------------------------------------------------------ versions
    def _members(self, work_id):
        return [i for i in self.data["items"].values() if i.get("work_id") == work_id]

    @staticmethod
    def _ordered(members):
        """Versions in their order: the one set by hand if any, else by creation."""
        return sorted(members, key=lambda m: (m.get("work_pos") is None, m.get("work_pos") or 0,
                                              m.get("created", ""), m.get("added", "")))

    def set_order(self, work_id, ids):
        """Put the versions of a work in this order (all of them, by id)."""
        with self.lock:
            members = self._members(work_id)
            if not members:
                raise KeyError(work_id)
            if sorted(ids) != sorted(m["id"] for m in members):
                raise ValueError("The list doesn't match the versions of this work")
            for pos, item_id in enumerate(ids):
                self.data["items"][item_id]["work_pos"] = pos
            self._save()

    def sort_by_date(self, work_id):
        """Forget the order set by hand: versions follow their creation dates again."""
        with self.lock:
            members = self._members(work_id)
            if not members:
                raise KeyError(work_id)
            for m in members:
                m.pop("work_pos", None)
            self._save()

    def _leave_work(self, item):
        item["work_id"] = None
        item.pop("work_cover", None)
        item.pop("work_pos", None)
        solo = item.pop("solo", None)
        if solo:
            for k, v in solo.items():
                if v is not None:
                    item[k] = v
        item["modified"] = _now_iso()

    def _dissolve_if_single(self, work_id):
        members = self._members(work_id)
        if len(members) == 1:
            # The last version keeps the work's fields: they are what you saw.
            members[0].pop("solo", None)
            self._leave_work(members[0])

    def group(self, ids):
        """Group items as versions of one work. Shared fields come from the work
        already present in the selection, otherwise from the newest item."""
        with self.lock:
            items = [self.data["items"][i] for i in ids if i in self.data["items"]]
            if len(items) < 2:
                raise ValueError("Select at least two creations")
            existing = [i["work_id"] for i in items if i.get("work_id")]
            work_id = existing[0] if existing else uuid.uuid4().hex[:12]
            members = {i["id"]: i for i in items}
            for wid in set(existing):
                for m in self._members(wid):
                    members[m["id"]] = m
            members = list(members.values())
            # Each work keeps its own order of versions; the works and the loose
            # creations are then interleaved by creation date.
            sequences, seen_works = [], set()
            for m in sorted(members, key=lambda m: (m.get("created", ""), m.get("added", ""))):
                wid = m.get("work_id")
                if wid and wid in existing:
                    if wid not in seen_works:
                        seen_works.add(wid)
                        sequences.append(self._ordered([x for x in members if x.get("work_id") == wid]))
                else:
                    sequences.append([m])
            manual = any(m.get("work_pos") is not None for m in members)
            order = []
            while sequences:
                first = min(sequences, key=lambda seq: (seq[0].get("created", ""), seq[0].get("added", "")))
                order.append(first.pop(0))
                if not first:
                    sequences.remove(first)
            # A title typed by hand wins over one taken from a file name; then the
            # work already present in the selection; then the newest creation.
            stems = {os.path.splitext((m.get("source") or {}).get("name", ""))[0] for m in members}

            def custom_title(m):
                return bool(m.get("title")) and m["title"] not in stems
            in_work = [m for m in members if m.get("work_id") == work_id]
            named = sorted([m for m in members if custom_title(m)], key=lambda m: m.get("modified", ""), reverse=True)
            primary = (next((m for m in in_work if custom_title(m)), None) or (named[0] if named else None)
                       or (in_work[0] if in_work else max(members, key=lambda m: m.get("created", ""))))
            tags = []
            for m in members:
                for t in m.get("tags", []):
                    if t.lower() not in (x.lower() for x in tags):
                        tags.append(t)
            category = primary.get("category") or next((m["category"] for m in members if m.get("category")), "")
            favorite = any(m.get("favorite") for m in members)
            cover = next((m["id"] for m in members if m.get("work_cover")), None)
            for m in members:
                # Remember a creation's own fields, to restore them if it leaves the work.
                if not m.get("work_id") and "solo" not in m:
                    m["solo"] = {k: m.get(k) for k in SHARED_FIELDS}
                m["work_id"] = work_id
                m["title"] = primary["title"]
                m["category"] = category
                m["tags"] = list(tags)
                m["favorite"] = favorite
                m["work_cover"] = m["id"] == cover
                m["modified"] = _now_iso()
            for pos, m in enumerate(order):
                if manual:
                    m["work_pos"] = pos
                else:
                    m.pop("work_pos", None)
            self._save()
            return work_id

    def ungroup(self, item_id):
        with self.lock:
            item = self.data["items"].get(item_id)
            if not item or not item.get("work_id"):
                raise KeyError(item_id)
            work_id = item["work_id"]
            self._leave_work(item)
            self._dissolve_if_single(work_id)
            self._save()

    def set_cover(self, item_id):
        with self.lock:
            item = self.data["items"].get(item_id)
            if not item or not item.get("work_id"):
                raise KeyError(item_id)
            for m in self._members(item["work_id"]):
                m["work_cover"] = m["id"] == item_id
            self._save()

    def signatures_pending(self):
        """Creations whose similarity signature isn't computed yet."""
        with self.lock:
            return sum(1 for i in self.data["items"].values() if i.get("sig_v") != sim.SIG_VERSION)

    def _compare(self, a, b):
        """Similarity of two creations, cached while their signatures don't change."""
        key = (a["id"], b["id"]) if a["id"] < b["id"] else (b["id"], a["id"])
        stamp = (a.get("sig_v"), b.get("sig_v"))
        hit = self._pair_cache.get(key)
        if hit and hit[0] == stamp:
            return hit[1]
        parts = sim.compare(a.get("sig"), b.get("sig"))
        self._pair_cache[key] = (stamp, parts)
        return parts

    def suggestions(self, level="normal"):
        """Creations that look (or sound) alike and are related, not all in one
        work yet. Related means: the same workflow, or the same source file
        (Load Image / Load Video of image-to-image workflows). At the Loose
        level, creations without any link are also suggested when they look
        almost identical.

        Groups are tight: a creation joins a group only if it matches every
        member of it (complete linkage). Creations without a signature yet are
        left out. Each creation's score is its lowest similarity to the others."""
        import heapq
        with self.lock:
            items = [dict(i) for i in self.data["items"].values() if i.get("sig")]
            dismissed_all = {k: set(v) for k, v in self.data["dismissed_suggestions"].items()}
        # Identical creations are duplicates, not versions: keep one of each.
        seen_content, unique = set(), []
        for it in sorted(items, key=lambda i: (not i.get("work_id"), i.get("added", ""))):
            key = it.get("chash") or it.get("sha")
            if key and key in seen_content:
                continue
            seen_content.add(key)
            unique.append(it)
        items = unique
        by_id = {it["id"]: it for it in items}

        def own_dismissed(it):
            return not it.get("work_id") and it["id"] in dismissed_all.get(it.get("workflow_id") or "", set())

        def cross_dismissed(it):
            return not it.get("work_id") and (it["id"] in dismissed_all.get("*", set()) or own_dismissed(it))

        def sources(it):
            return set((it.get("summary") or {}).get("sources") or [])

        # Related pairs: same workflow or same source file.
        buckets = {}
        for it in items:
            if it.get("workflow_id"):
                buckets.setdefault("wf:" + it["workflow_id"], []).append(it)
            for src in sources(it):
                buckets.setdefault("src:" + src, []).append(it)
        edges = {}  # (id, id) -> similarity, both directions

        def add_edge(a, b, value):
            edges[(a["id"], b["id"])] = edges[(b["id"], a["id"])] = value

        done = set()
        for members in buckets.values():
            for x in range(len(members)):
                for y in range(x + 1, len(members)):
                    a, b = members[x], members[y]
                    pair = (a["id"], b["id"]) if a["id"] < b["id"] else (b["id"], a["id"])
                    if pair in done:
                        continue
                    done.add(pair)
                    if a.get("work_id") and a.get("work_id") == b.get("work_id"):
                        continue
                    same_wf = a.get("workflow_id") and a.get("workflow_id") == b.get("workflow_id")
                    if (same_wf and (own_dismissed(a) or own_dismissed(b))) or \
                            (not same_wf and (cross_dismissed(a) or cross_dismissed(b))):
                        continue
                    parts = self._compare(a, b)
                    if sim.matches(parts, a["kind"], level):
                        add_edge(a, b, parts[0])
        # Loose: almost identical, whatever their origin.
        if level == "loose":
            for a_id, b_id, value in self._lookalikes(items):
                a, b = by_id.get(a_id), by_id.get(b_id)
                if not a or not b or (a_id, b_id) in edges:
                    continue
                if a.get("work_id") and a.get("work_id") == b.get("work_id"):
                    continue
                if cross_dismissed(a) or cross_dismissed(b):
                    continue
                add_edge(a, b, value)

        # Complete-linkage clustering over the matching pairs, starting with one
        # cluster per existing work and one per loose creation.
        involved = {a for a, _ in edges}
        cluster_of, members = {}, {}
        for it in items:
            if it["id"] not in involved:
                continue
            cid = "w:" + it["work_id"] if it.get("work_id") else it["id"]
            cluster_of[it["id"]] = cid
            members.setdefault(cid, [])
        for it in items:  # whole works, even members without a match of their own
            if it.get("work_id") and ("w:" + it["work_id"]) in members:
                cluster_of[it["id"]] = "w:" + it["work_id"]
            if it["id"] in cluster_of:
                members[cluster_of[it["id"]]].append(it)
        link = {}
        for (a, b), value in edges.items():
            if a > b:
                continue
            ca, cb = cluster_of[a], cluster_of[b]
            if ca == cb:
                continue
            key = (ca, cb) if ca < cb else (cb, ca)
            entry = link.setdefault(key, [1.0, 0])
            entry[0] = min(entry[0], value)
            entry[1] += 1
        link = {k: v[0] for k, v in link.items() if v[1] == len(members[k[0]]) * len(members[k[1]])}
        heap = [(-v, k) for k, v in link.items()]
        heapq.heapify(heap)
        while heap:
            neg, (ca, cb) = heapq.heappop(heap)
            if link.get((ca, cb)) != -neg:
                continue
            for k in list(members):
                if k in (ca, cb):
                    continue
                ka = (ca, k) if ca < k else (k, ca)
                kb = (cb, k) if cb < k else (k, cb)
                va, vb = link.pop(ka, None), link.pop(kb, None)
                if va is not None and vb is not None:
                    link[ka] = min(va, vb)
                    heapq.heappush(heap, (-link[ka], ka))
            link.pop((ca, cb), None)
            members[ca].extend(members.pop(cb))

        out = []
        for group in members.values():
            if len(group) < 2:
                continue
            works = {m.get("work_id") for m in group}
            if len(works) == 1 and None not in works:
                continue  # already one work
            group.sort(key=lambda m: m.get("created", ""))
            scores = {}
            for m in group:
                values = [edges[(m["id"], o["id"])] for o in group if o is not m and (m["id"], o["id"]) in edges]
                if values:
                    scores[m["id"]] = round(min(values) * 100)
            wfs = {m.get("workflow_id") for m in group}
            if len(wfs) == 1 and None not in wfs:
                reason, key = "workflow", next(iter(wfs))
            else:
                common = set.intersection(*(sources(m) for m in group))
                reason, key = ("source" if common else "lookalike"), "*"
            out.append({"workflow_id": key, "reason": reason, "ids": [m["id"] for m in group], "scores": scores})
        with self.lock:
            added = {i: self.data["items"][i].get("added", "") for g in out for i in g["ids"] if i in self.data["items"]}
        out.sort(key=lambda g: max(added.get(i, "") for i in g["ids"]), reverse=True)
        return out

    def _lookalikes(self, items):
        """Almost identical pairs across the library, cached until the set of
        creations (or their signatures) changes."""
        key = hash(tuple(sorted((i["id"], i.get("sig_v")) for i in items)))
        cached = getattr(self, "_lookalike_cache", None)
        if cached and cached[0] == key:
            return cached[1]
        try:
            pairs = sim.lookalike_pairs([(i["id"], i["kind"], i.get("sig")) for i in items])
        except Exception as e:
            _say("Could not compare creations across workflows: %s" % e)
            pairs = []
        self._lookalike_cache = (key, pairs)
        return pairs

    def dismiss_suggestion(self, workflow_id, ids=None):
        """Stop suggesting these creations of a workflow (all of them by default)."""
        with self.lock:
            if not ids:
                ids = [i["id"] for i in self.data["items"].values() if i.get("workflow_id") == workflow_id]
            done = set(self.data["dismissed_suggestions"].get(workflow_id, []))
            self.data["dismissed_suggestions"][workflow_id] = sorted(done | set(ids))
            self._save()
