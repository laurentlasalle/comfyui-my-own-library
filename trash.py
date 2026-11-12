"""
Sending files to the system's trash (Recycle Bin on Windows, Trash on macOS,
the freedesktop.org trash on Linux), so that a deletion can be undone from
there. Only the standard library is used: no package to install.

discard(path, immediately) is what the rest of the code calls: it deletes the
file for good when immediately is true (the "Delete immediately" setting),
otherwise it moves it to the trash. When the file can't go to the trash (a
network or removable drive without one, an unknown system), TrashError is
raised and the file is left where it is: nothing is ever deleted for good
behind the user's back.
"""

import os
import sys
import time
from urllib.parse import quote


class TrashError(OSError):
    pass


def trash_name():
    """The name users know the trash by on this system."""
    if sys.platform == "win32":
        return "Recycle Bin"
    return "Trash"


def discard(path, immediately=False):
    """Delete path for good, or move it to the trash. Returns its size."""
    size = os.path.getsize(path)
    if immediately:
        os.remove(path)
    else:
        send_to_trash(path)
    return size


def send_to_trash(path):
    path = os.path.abspath(path)
    if not os.path.lexists(path):
        raise FileNotFoundError(path)
    if sys.platform == "win32":
        _trash_windows(path)
    elif sys.platform == "darwin":
        _trash_macos(path)
    else:
        _trash_freedesktop(path)
    if os.path.lexists(path):
        raise TrashError("%s could not be moved to the %s" % (os.path.basename(path), trash_name()))


# --------------------------------------------------------------------- Windows
def _trash_windows(path):
    import ctypes
    from ctypes import wintypes

    # Only fixed drives have a Recycle Bin. On a network or removable drive,
    # Windows would silently delete the file for good instead: refuse.
    drive = os.path.splitdrive(path)[0]
    root = (drive + "\\") if drive and not drive.startswith("\\\\") else None
    DRIVE_FIXED = 3
    if root is None or ctypes.windll.kernel32.GetDriveTypeW(root) != DRIVE_FIXED:
        raise TrashError("%s is not on a local drive with a Recycle Bin. Turn on Delete immediately "
                         "in the settings to delete it for good" % os.path.basename(path))

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    FO_DELETE = 3
    FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 0x4, 0x10, 0x40, 0x400
    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = path + "\0"  # the list of files ends with an extra null character
    op.fFlags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if result or op.fAnyOperationsAborted:
        raise TrashError("%s could not be moved to the Recycle Bin (error %d)" % (os.path.basename(path), result))


# ----------------------------------------------------------------------- macOS
def _trash_macos(path):
    # NSFileManager's trashItemAtURL, through the Objective-C runtime (no
    # PyObjC needed). It is what the Finder does, including "Put Back".
    try:
        _trash_macos_objc(path)
        return
    except TrashError:
        raise
    except Exception:
        pass
    # Fallback: ask the Finder (macOS may ask once to allow ComfyUI to control it).
    import subprocess
    script = 'tell application "Finder" to delete POSIX file "%s"' % path.replace("\\", "\\\\").replace('"', '\\"')
    done = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise TrashError("%s could not be moved to the Trash: %s" % (os.path.basename(path), done.stderr.strip()))


def _trash_macos_objc(path):
    import ctypes
    import ctypes.util

    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    send = objc.objc_msgSend

    def msg(receiver, selector, restype, *args):
        # objc_msgSend must be called with the exact prototype of each method.
        send.restype = restype
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + [type(a) for a in args]
        return send(receiver, objc.sel_registerName(selector), *args)

    ns_string = msg(objc.objc_getClass(b"NSString"), b"stringWithUTF8String:", ctypes.c_void_p,
                    ctypes.c_char_p(path.encode("utf-8")))
    url = msg(objc.objc_getClass(b"NSURL"), b"fileURLWithPath:", ctypes.c_void_p, ctypes.c_void_p(ns_string))
    manager = msg(objc.objc_getClass(b"NSFileManager"), b"defaultManager", ctypes.c_void_p)
    error = ctypes.c_void_p()
    ok = msg(manager, b"trashItemAtURL:resultingItemURL:error:", ctypes.c_bool,
             ctypes.c_void_p(url), ctypes.c_void_p(None), ctypes.c_void_p(ctypes.addressof(error)))
    if not ok:
        raise TrashError("%s could not be moved to the Trash" % os.path.basename(path))


# ----------------------------------------------------------------------- Linux
def _trash_freedesktop(path):
    """The trash of the freedesktop.org specification, used by GNOME, KDE and
    the others: the home trash when the file is on the same drive as the home
    folder, otherwise the .Trash-<uid> folder at the top of the file's drive."""
    home_trash = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "Trash")
    dev = os.stat(path).st_dev
    if _same_device(home_trash, dev):
        trash_dir, shown_path = home_trash, path
    else:
        top = _mount_point(path)
        trash_dir = os.path.join(top, ".Trash-%d" % os.getuid())
        shown_path = os.path.relpath(path, top)  # relative to the top of the drive, as the specification says
    files_dir, info_dir = os.path.join(trash_dir, "files"), os.path.join(trash_dir, "info")
    try:
        os.makedirs(files_dir, mode=0o700, exist_ok=True)
        os.makedirs(info_dir, mode=0o700, exist_ok=True)
    except OSError as e:
        raise TrashError("No trash available for %s (%s)" % (os.path.basename(path), e))

    # A free name: the .trashinfo file is created first, exclusively, to reserve it.
    base = os.path.basename(path)
    stem, ext = os.path.splitext(base)
    for n in range(1000):
        name = base if n == 0 else "%s.%d%s" % (stem, n, ext)
        info_path = os.path.join(info_dir, name + ".trashinfo")
        try:
            fd = os.open(info_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("[Trash Info]\nPath=%s\nDeletionDate=%s\n"
                     % (quote(shown_path), time.strftime("%Y-%m-%dT%H:%M:%S")))
        try:
            os.rename(path, os.path.join(files_dir, name))
        except OSError as e:
            os.remove(info_path)
            raise TrashError("%s could not be moved to the Trash (%s)" % (base, e))
        return
    raise TrashError("No free name in the Trash for %s" % base)


def _same_device(folder, dev):
    probe = folder
    while not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return False
        probe = parent
    return os.stat(probe).st_dev == dev


def _mount_point(path):
    path = os.path.realpath(path)
    while not os.path.ismount(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path
