"""
HTTP routes of My Own Library. All routes live under /my_own_library/ and are
also reachable under /api/my_own_library/ (ComfyUI mirrors custom routes).

The library itself is only opened on the first request, so nothing happens
at ComfyUI startup besides registering the routes.
"""

import asyncio
import json
import logging
import os
import threading

from aiohttp import web

import folder_paths
from server import PromptServer

from .store import Library

log = logging.getLogger("my_own_library")
PREFIX = "/my_own_library"

_library = None
_library_lock = threading.Lock()


# ------------------------------------------------------------------ progress
# The window sends long operations in small batches; each batch says where it
# stands in the whole job, so the terminal shows "37/240" and a summary at the end.
_jobs = {}


def _fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0


def _say(text):
    print("[My Own Library] " + text, flush=True)


class Job:
    def __init__(self, body, verb):
        info = body.get("job") or {}
        self.id = str(info.get("id") or "")
        self.start = int(info.get("start") or 0)
        self.total = int(info.get("total") or 0)
        self.last = bool(info.get("last", True))
        self.verb = verb
        state = _jobs.get(self.id) if self.id else None
        if state is None:
            import time
            state = {"t0": time.time(), "counts": {}, "freed": 0, "errors": 0, "verb": verb}
            if self.id:
                _jobs[self.id] = state
        self.state = state
        self.n = self.start

    def step(self, name, what, extra=""):
        """Log one file: what = added, skipped, already, removed, deleted, error."""
        self.n += 1
        self.state["counts"][what] = self.state["counts"].get(what, 0) + 1
        label = {"added": "Added", "skipped": "Skipped (identical to a library creation)",
                 "already": "Already in library", "removed": "Removed from output",
                 "deleted": "Deleted from output", "removed_lib": "Removed from library",
                 "error": "Error"}[what]
        total = self.total or "?"
        _say("%s %s/%s: %s%s" % (label, self.n, total, name, (" (%s)" % extra) if extra else ""))
        if what == "error":
            self.state["errors"] += 1

    def step_quiet(self, what):
        self.state["counts"][what] = self.state["counts"].get(what, 0) + 1

    def freed(self, n):
        self.state["freed"] += n

    def finish(self, cancelled=False):
        if not self.last and not cancelled:
            return
        import time
        _jobs.pop(self.id, None)
        c = self.state["counts"]
        parts = []
        for key, label in (("added", "added"), ("skipped", "skipped as duplicates"), ("already", "already in library"),
                           ("removed", "removed from output"), ("deleted", "deleted from output"),
                           ("removed_lib", "removed from library"), ("error", "errors")):
            if c.get(key):
                parts.append("%d %s" % (c[key], label))
        if self.state["freed"]:
            parts.append("%s freed" % _fmt_size(self.state["freed"]))
        _say("%s %s in %.1f s: %s" % (self.state.get("verb", self.verb), "cancelled" if cancelled else "done",
                                      time.time() - self.state["t0"], ", ".join(parts) or "nothing to do"))


def config_path():
    return os.path.join(folder_paths.get_user_directory(), "my_own_library.config.json")


def read_config():
    default_dir = os.path.join(folder_paths.get_user_directory(), "my_own_library")
    cfg = {"library_dir": default_dir}
    path = config_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            if isinstance(user_cfg.get("library_dir"), str) and user_cfg["library_dir"].strip():
                cfg["library_dir"] = os.path.expanduser(user_cfg["library_dir"].strip())
        except Exception as e:
            log.warning("[My Own Library] Could not read %s: %s", path, e)
    else:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"library_dir": default_dir}, f, indent=2)
        except Exception:
            pass
    return cfg


def library():
    global _library
    if _library is None:
        with _library_lock:
            if _library is None:
                cfg = read_config()
                _library = Library(cfg["library_dir"], {
                    "output": folder_paths.get_output_directory(),
                    "temp": folder_paths.get_temp_directory(),
                    "input": folder_paths.get_input_directory(),
                })
                log.info("[My Own Library] Library folder: %s", _library.dir)
    return _library


async def run(func, *args):
    return await asyncio.get_running_loop().run_in_executor(None, func, *args)


def error(message, status=400):
    return web.json_response({"error": str(message)}, status=status)


def setup_routes():
    routes = PromptServer.instance.routes

    @routes.get(PREFIX + "/library")
    async def get_library(request):
        return web.json_response(await run(lambda: library().snapshot()))

    @routes.get(PREFIX + "/output")
    async def get_output(request):
        root = request.query.get("root", "output")
        kind = request.query.get("kind", "all")
        query = request.query.get("q", "").strip().lower()
        offset = max(0, int(request.query.get("offset", 0)))
        limit = min(1000, max(1, int(request.query.get("limit", 200))))
        try:
            files = await run(library().list_root, root)
        except Exception as e:
            return error(e)
        if kind in ("image", "video", "audio"):
            files = [f for f in files if f["kind"] == kind]
        if query:
            files = [f for f in files if query in f["rel"].lower()]
        not_added = sum(1 for f in files if not f["in_library"])
        since = request.query.get("since")
        if since:
            files = [f for f in files if f["mtime"] > float(since)]
        if request.query.get("hide_added") in ("1", "true"):
            files = [f for f in files if not f["in_library"]]
        if request.query.get("keys_only") in ("1", "true"):
            # Every matching file, without thumbnails or families: used to select
            # the whole folder, including files not displayed yet.
            return web.json_response({"files": [
                {k: f[k] for k in ("root", "rel", "name", "size", "in_library")} for f in files]})
        return web.json_response({
            "total": len(files), "not_added": not_added,
            "offset": offset, "files": await run(library().file_families, files[offset:offset + limit]),
        })

    @routes.get(PREFIX + "/badge")
    async def get_badge(request):
        lib = library()
        return web.json_response({"count": await run(lib.count_new), "seen": lib.output_seen()})

    @routes.post(PREFIX + "/seen")
    async def post_seen(request):
        lib = library()
        previous = await run(lib.mark_output_seen)
        return web.json_response({"previous": previous, "seen": lib.output_seen()})

    @routes.get(PREFIX + "/inspect")
    async def get_inspect(request):
        try:
            return web.json_response(await run(library().inspect,
                                               request.query.get("root", "output"),
                                               request.query["rel"]))
        except Exception as e:
            return error(e)

    @routes.get(PREFIX + "/source")
    async def get_source(request):
        try:
            path = library().root_path(request.query.get("root", "output"), request.query["rel"])
        except Exception as e:
            return error(e)
        if not os.path.isfile(path):
            return error("Not found", 404)
        return web.FileResponse(path)

    @routes.get(PREFIX + "/thumb")
    async def get_thumb(request):
        lib = library()
        item_id = request.query.get("id")
        try:
            if item_id:
                path = os.path.join(lib.dir, "thumbs", os.path.basename(item_id) + ".jpg")
                if not os.path.isfile(path):
                    item = lib.get(item_id)
                    if not item:
                        return error("Not found", 404)
                    from .store import make_thumbnail
                    ok, _, _ = await run(make_thumbnail, lib.item_path(item), path, item["kind"])
                    if not ok:
                        return error("No thumbnail", 404)
            else:
                path = await run(lib.cache_thumbnail, request.query.get("root", "output"), request.query["rel"])
                if not path:
                    return error("No thumbnail", 404)
        except Exception as e:
            return error(e, 404)
        return web.FileResponse(path, headers={"Cache-Control": "max-age=86400"})

    @routes.get(PREFIX + "/file")
    async def get_file(request):
        lib = library()
        item = lib.get(request.query.get("id", ""))
        if not item:
            return error("Not found", 404)
        path = lib.item_path(item, request.query.get("part", "main"))
        if not path or not os.path.isfile(path):
            return error("Missing file", 404)
        headers = {}
        if request.query.get("download"):
            safe = "".join(c for c in item["title"] if c not in '\\/:*?"<>|').strip() or item["id"]
            headers["Content-Disposition"] = 'attachment; filename="%s%s"' % (safe, item["ext"])
        return web.FileResponse(path, headers=headers)

    @routes.get(PREFIX + "/meta")
    async def get_meta(request):
        try:
            return web.json_response(await run(library().meta, os.path.basename(request.query["id"])))
        except Exception as e:
            return error(e, 404)

    @routes.post(PREFIX + "/add")
    async def post_add(request):
        body = await request.json()
        lib = library()
        added, existing, duplicates, errors = [], [], [], []
        removed, freed = [], 0
        job = Job(body, "Moving to library" if body.get("remove_after") else "Adding to library")
        import time
        for entry in body.get("files", []):
            name = entry.get("rel", "")
            t0 = time.time()
            try:
                item, created = await run(lib.add, entry.get("root", "output"), entry["rel"],
                                          body.get("category", ""), body.get("tags", []),
                                          entry.get("title"), bool(body.get("allow_duplicates")))
                if created == "duplicate":
                    duplicates.append({"root": entry.get("root", "output"), "rel": entry["rel"],
                                       "id": item["id"], "title": item.get("title")})
                    job.step(name, "skipped", 'same as "%s"' % item.get("title"))
                else:
                    (added if created else existing).append(item)
                    job.step(name, "added" if created else "already",
                             "%s, %.1f s" % (_fmt_size(item.get("size") or 0), time.time() - t0) if created else "")
            except Exception as e:
                errors.append({"rel": entry.get("rel"), "error": str(e)})
                job.step(name, "error", str(e))
                continue
            if body.get("remove_after") and entry.get("root", "output") == "output":
                try:
                    n = await run(lib.delete_from_output, "output", entry["rel"])
                    freed += n
                    job.freed(n)
                    job.step_quiet("removed")
                    _say("  removed from output: %s (%s)" % (name, _fmt_size(n)))
                    removed.append(entry["rel"])
                except Exception as e:
                    errors.append({"rel": entry.get("rel"), "error": "Added, but not removed from output: %s" % e})
                    _say("  not removed from output: %s (%s)" % (name, e))
        job.finish(bool(body.get("cancelled")))
        return web.json_response({"added": added, "existing": existing, "duplicates": duplicates, "errors": errors,
                                  "removed": removed, "freed": freed})

    @routes.post(PREFIX + "/duplicates/merge")
    async def post_duplicates_merge(request):
        body = await request.json()
        lib = library()
        groups = (await run(lib.duplicates)) if body.get("all") else [body.get("ids", [])]
        kept, errors = [], []
        for ids in groups:
            try:
                kept.append(await run(lib.merge_duplicates, ids))
            except Exception as e:
                errors.append(str(e))
        return web.json_response({"kept": kept, "errors": errors, **(await run(lib.snapshot))})

    @routes.post(PREFIX + "/job/cancel")
    async def post_job_cancel(request):
        """The window stopped a job between two batches: print its summary."""
        body = await request.json()
        if str((body.get("job") or {}).get("id") or "") in _jobs:
            Job(body, "Job").finish(cancelled=True)
        return web.json_response({"ok": True})

    @routes.post(PREFIX + "/output/delete")
    async def post_output_delete(request):
        body = await request.json()
        lib = library()
        deleted, errors, freed = [], [], 0
        job = Job(body, "Deleting from output")
        for entry in body.get("files", []):
            try:
                n = await run(lib.delete_from_output, entry.get("root", "output"), entry["rel"])
                freed += n
                job.freed(n)
                job.step(entry["rel"], "deleted", _fmt_size(n))
                deleted.append(entry["rel"])
            except Exception as e:
                errors.append({"rel": entry.get("rel"), "error": str(e)})
                job.step(entry.get("rel", ""), "error", str(e))
        job.finish(bool(body.get("cancelled")))
        return web.json_response({"deleted": deleted, "errors": errors, "freed": freed})

    @routes.get(PREFIX + "/versions/suggestions")
    async def get_suggestions(request):
        level = request.query.get("level", "normal")
        lib = library()
        return web.json_response({"suggestions": await run(lib.suggestions, level),
                                  "pending": lib.signatures_pending()})

    @routes.post(PREFIX + "/versions/{action}")
    async def post_versions(request):
        action = request.match_info["action"]
        body = await request.json()
        lib = library()
        try:
            if action == "group":
                work_id = await run(lib.group, body.get("ids", []))
                return web.json_response({"work_id": work_id, **(await run(lib.snapshot))})
            if action == "ungroup":
                await run(lib.ungroup, body.get("id", ""))
            elif action == "cover":
                await run(lib.set_cover, body.get("id", ""))
            elif action == "order":
                await run(lib.set_order, body.get("work_id", ""), body.get("ids", []))
            elif action == "sortbydate":
                await run(lib.sort_by_date, body.get("work_id", ""))
            elif action == "dismiss":
                await run(lib.dismiss_suggestion, body.get("workflow_id", ""), body.get("ids"))
            else:
                return error("Unknown action", 404)
        except KeyError:
            return error("Not found", 404)
        except Exception as e:
            return error(e)
        return web.json_response(await run(lib.snapshot))

    @routes.post(PREFIX + "/item/update")
    async def post_update(request):
        body = await request.json()
        try:
            item = await run(library().update, body.get("id", ""), body.get("fields", {}))
        except KeyError:
            return error("Not found", 404)
        except Exception as e:
            return error(e)
        return web.json_response({"item": item, "categories": library().snapshot()["categories"]})

    @routes.post(PREFIX + "/item/remove")
    async def post_remove(request):
        body = await request.json()
        try:
            await run(library().remove, body.get("id", ""))
        except KeyError:
            return error("Not found", 404)
        return web.json_response({"ok": True})

    @routes.post(PREFIX + "/items/remove")
    async def post_remove_many(request):
        body = await request.json()
        lib = library()
        removed, freed = 0, 0
        job = Job(body, "Removing from library")
        for item_id in body.get("ids", []):
            item = lib.get(item_id)
            name = (item or {}).get("title") or item_id
            try:
                n = await run(lib.remove, item_id)
                freed += n
                removed += 1
                job.freed(n)
                job.step(name, "removed_lib", _fmt_size(n))
            except KeyError:
                pass
        job.finish(bool(body.get("cancelled")))
        return web.json_response({"removed": removed, "freed": freed, **(await run(lib.snapshot))})

    @routes.post(PREFIX + "/items/update")
    async def post_update_many(request):
        body = await request.json()
        lib = library()
        try:
            await run(lib.update_many, body.get("ids", []), body.get("category"), body.get("add_tags"))
        except Exception as e:
            return error(e)
        return web.json_response(await run(lib.snapshot))

    @routes.post(PREFIX + "/category")
    async def post_category(request):
        body = await request.json()
        try:
            cats = await run(library().category, body.get("action"), body.get("name", ""),
                             body.get("new_name", ""), body.get("order"))
        except Exception as e:
            return error(e)
        return web.json_response({"categories": cats})
