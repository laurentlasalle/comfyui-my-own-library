"""
Steps of a workflow run: a workflow that saves several outputs (a first video,
the same video refined, frames taken from it, those frames upscaled, a sheet
made of them) writes them all during one run. Only the last one is the
result; the others are steps, like the segments of a combined video.

How a run is recognized, without guessing:
- every file ComfyUI saves carries the prompt of the run (the graph of nodes
  with all their values, seeds included), so the files of one run have an
  identical prompt;
- a file is matched to the node that saved it by its filename_prefix;
- a run needs at least two such nodes: a batch of images saved by one node is
  one output, not steps;
- the order comes from the graph: an output whose upstream nodes are all
  upstream of another output too (leaving aside the nodes only it uses, like
  its own Create Video) is a step before that one. The outputs that are a
  step before none are the results: usually one, one per branch when a
  workflow has independent branches. When the graph can't tell (a prefix that
  matches no node), the time of saving decides: ComfyUI runs a node only
  after the ones it depends on.

The prompts are read in the background (reading a video needs ffprobe), and
cached; a listing uses what is known and the rest appears at the next one.
"""

import hashlib
import json
import os
import re
import threading
import time

from . import metadata as md

GAP = 30 * 60           # seconds between two files that can't be the same run
_cache = {}             # (path, size, mtime) -> prompt hash or None
_prompts = {}           # prompt hash -> prompt
_lock = threading.Lock()
_pending = {"running": False, "todo": []}


# --------------------------------------------------------------------- prompts
def _prompt_hash(prompt):
    if not isinstance(prompt, dict) or not prompt:
        return None
    return hashlib.sha1(json.dumps(prompt, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def remember(key, prompt):
    """Record the prompt of a file (key: any hashable naming that version of it)."""
    h = _prompt_hash(prompt)
    with _lock:
        _cache[key] = h
        if h and h not in _prompts:
            _prompts[h] = prompt
    return h


def known(key):
    with _lock:
        return key in _cache, _cache.get(key)


def read_later(jobs):
    """jobs: [(key, path)]. Read their prompts in the background."""
    with _lock:
        todo = [j for j in jobs if j[0] not in _cache]
        if not todo:
            return
        _pending["todo"].extend(todo)
        if _pending["running"]:
            return
        _pending["running"] = True

    def work():
        while True:
            with _lock:
                if not _pending["todo"]:
                    _pending["running"] = False
                    return
                key, path = _pending["todo"].pop(0)
                if key in _cache:
                    continue
            try:
                prompt, _wf = md.extract(path)
            except Exception:
                prompt = None
            remember(key, prompt)

    threading.Thread(target=work, daemon=True).start()


# ------------------------------------------------------------------ the graph
_COUNTER = re.compile(r"[_\-. ]*\d+[_\-. ]*$")


def _save_nodes(prompt):
    """{node id: prefix} of the nodes that save files."""
    out = {}
    for nid, node in prompt.items():
        prefix = (node.get("inputs") or {}).get("filename_prefix") if isinstance(node, dict) else None
        if isinstance(prefix, str) and prefix.strip():
            out[str(nid)] = prefix.strip().replace("\\", "/").lower()
    return out


def _ancestors(prompt, nid):
    seen, stack = set(), [str(nid)]
    while stack:
        node = prompt.get(stack.pop()) or {}
        for value in (node.get("inputs") or {}).values():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], (str, int)):
                up = str(value[0])
                if up in prompt and up not in seen:
                    seen.add(up)
                    stack.append(up)
    return seen


def _node_of(rel, saves):
    """The save node whose prefix names this file (longest prefix wins)."""
    stem = os.path.splitext(rel.replace("\\", "/").lower())[0]
    name = stem.split("/")[-1]
    best = None
    for nid, prefix in saves.items():
        # A prefix may hold a folder ("h3looksheet/video_refine"); then the
        # whole path must start with it, otherwise only the file name.
        matches = stem.startswith(prefix) if "/" in prefix else name.startswith(prefix)
        if matches and (best is None or len(prefix) > len(saves[best])):
            best = nid
    return best


# ------------------------------------------------------------------------ runs
def find_runs(entries):
    """entries: [{key, rel, time, hash}] (key: anything identifying the file).
    Returns [{"results": [keys], "steps": [{key, index, count}]}]."""
    by_hash = {}
    for e in entries:
        if e.get("hash"):
            by_hash.setdefault(e["hash"], []).append(e)
    runs = []
    for h, group in by_hash.items():
        if len(group) < 2:
            continue
        prompt = _prompts.get(h) or {}
        saves = _save_nodes(prompt)
        for e in group:
            e["_node"] = _node_of(e["rel"], saves) or ("?" + _COUNTER.sub("", os.path.splitext(e["rel"].lower())[0]))
        group.sort(key=lambda e: e["time"])
        # Split into runs: a long gap, or an output saved again after another
        # one (the same prompt queued again later, its cache gone).
        clusters, current, last_node = [], [], None
        for e in group:
            seen_nodes = {x["_node"] for x in current}
            if current and (e["time"] - current[-1]["time"] > GAP
                            or (e["_node"] in seen_nodes and e["_node"] != last_node)):
                clusters.append(current)
                current = []
            current.append(e)
            last_node = e["_node"]
        if current:
            clusters.append(current)
        for c in clusters:
            run = _order(c, prompt)
            if run:
                runs.append(run)
    return runs


def _order(cluster, prompt):
    nodes = {}
    for e in cluster:
        nodes.setdefault(e["_node"], []).append(e)
    if len(nodes) < 2:
        return None
    first_time = {n: min(e["time"] for e in es) for n, es in nodes.items()}
    graph_ok = all(n in prompt for n in nodes)
    if graph_ok:
        anc = {n: _ancestors(prompt, n) for n in nodes}
        before = {}
        for x in nodes:
            others = set().union(*(anc[y] for y in nodes if y != x))
            shared = anc[x] & others  # leave aside the nodes only x uses
            # x comes before y when what x saved feeds y too, and y uses more
            # than x does (otherwise they are two outputs of the same thing).
            before[x] = {y for y in nodes if y != x and shared <= anc[y] and not anc[y] <= anc[x]}
        results = [n for n in nodes if not before[n]]
        order = sorted(nodes, key=lambda n: (len(anc[n]), first_time[n]))
    else:
        order = sorted(nodes, key=lambda n: first_time[n])
        results = [order[-1]]
    if not results or len(results) == len(nodes):
        return None  # independent outputs only: no steps
    steps_order = [n for n in order if n not in results] + [n for n in order if n in results]
    count = len(steps_order)
    out = {"results": [e["key"] for n in results for e in nodes[n]], "steps": []}
    for i, n in enumerate(steps_order):
        if n in results:
            continue
        for e in nodes[n]:
            out["steps"].append({"key": e["key"], "index": i + 1, "count": count})
    return out


# -------------------------------------------------------------- output folder
def annotate(base, files):
    """Add "step" ({index, count, result}) to the files of the output folder
    that are steps of a run. Files already recognized as segments are left
    alone. Returns the runs."""
    entries, jobs = [], []
    for f in files:
        if f.get("part") or f["kind"] not in ("image", "video", "audio"):
            continue
        key = (f["rel"], f["size"], f["mtime"])
        ok, h = known(key)
        if not ok:
            jobs.append((key, os.path.join(base, f["rel"])))
            continue
        if h:
            entries.append({"key": f["rel"], "rel": f["rel"], "time": f["mtime"], "hash": h})
    if jobs:
        read_later(jobs)
    runs = find_runs(entries)
    by_rel = {f["rel"]: f for f in files}
    for r in runs:
        for s in r["steps"]:
            f = by_rel.get(s["key"])
            if f:
                f["step"] = {"index": s["index"], "count": s["count"], "result": r["results"][0]}
    return runs


# --------------------------------------------------------------------- library
def library_runs(lib_dir, items):
    """Runs among the library's items (dicts with id, kind, source, created).
    Prompts come from the copies kept in meta/."""
    from datetime import datetime
    entries, jobs = [], []
    for it in items:
        if it.get("kind") not in ("image", "video", "audio") or not it.get("has_prompt"):
            continue
        key = ("item", it["id"])
        ok, h = known(key)
        if not ok:
            jobs.append((key, it["id"]))
            continue
        if h:
            try:
                t = datetime.fromisoformat(it.get("created", "")).timestamp()
            except Exception:
                t = 0.0
            rel = (it.get("source") or {}).get("rel") or it.get("file") or ""
            entries.append({"key": it["id"], "rel": rel, "time": t, "hash": h})
    if jobs:
        _read_meta_later(lib_dir, jobs)
    return find_runs(entries)


def _read_meta_later(lib_dir, jobs):
    def work():
        for key, item_id in jobs:
            try:
                with open(os.path.join(lib_dir, "meta", item_id + ".json"), "r", encoding="utf-8") as fh:
                    prompt = (json.load(fh) or {}).get("prompt")
            except Exception:
                prompt = None
            remember(key, prompt)
    with _lock:
        if _pending.get("meta_running"):
            return
        _pending["meta_running"] = True

    def run():
        try:
            work()
        finally:
            with _lock:
                _pending["meta_running"] = False

    threading.Thread(target=run, daemon=True).start()
