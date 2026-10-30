"""
Models known to ComfyUI's Browse Templates, read from the installed
comfyui-workflow-templates package(s): the model names of the Model Filter
(index.json, "models" of each template) and the exact model files each
template downloads (node "properties" -> "models").

Used for the suggestions of the Model field, and to recognize official model
files exactly. Read once, lazily; nothing happens if the package is missing.
"""

import importlib
import json
import os
import pkgutil
import threading

_lock = threading.Lock()
_cache = None


def _package_dirs():
    dirs = []
    for mod in pkgutil.iter_modules():
        if mod.name.startswith("comfyui_workflow_templates"):
            try:
                spec = importlib.util.find_spec(mod.name)
            except Exception:
                continue
            for loc in (spec.submodule_search_locations or []) if spec else []:
                dirs.append(loc)
    return dirs


def _load():
    labels, files = set(), {}
    for base in _package_dirs():
        for root, _dirs, names in os.walk(base):
            if "index.json" not in names:
                continue
            try:
                with open(os.path.join(root, "index.json"), "r", encoding="utf-8") as f:
                    index = json.load(f)
            except Exception:
                continue
            groups = index if isinstance(index, list) else index.get("templates", []) if isinstance(index, dict) else []
            for group in groups:
                for tpl in (group.get("templates") or []) if isinstance(group, dict) else []:
                    models = [m.strip() for m in tpl.get("models") or [] if isinstance(m, str) and m.strip()]
                    labels.update(models)
                    if len(models) != 1:
                        continue  # several models: files can't be told apart
                    path = os.path.join(root, (tpl.get("name") or "") + ".json")
                    for name in _template_files(path):
                        files.setdefault(name.lower(), set()).add(models[0])
    exact = {name: next(iter(ls)) for name, ls in files.items() if len(ls) == 1}
    return {"labels": sorted(labels, key=str.lower), "files": exact}


def _template_files(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            wf = json.load(f)
    except Exception:
        return []
    out = []
    graphs = [wf] + list(((wf.get("definitions") or {}).get("subgraphs") or [])) if isinstance(wf, dict) else []
    for g in graphs:
        for node in g.get("nodes") or []:
            for m in ((node.get("properties") or {}).get("models") or []):
                name = m.get("name") if isinstance(m, dict) else None
                if isinstance(name, str) and name:
                    out.append(os.path.basename(name.replace("\\", "/")))
    return out


def known():
    """{"labels": [...], "files": {file name (lower case): label}}."""
    global _cache
    with _lock:
        if _cache is None:
            try:
                _cache = _load()
            except Exception:
                _cache = {"labels": [], "files": {}}
        return _cache
