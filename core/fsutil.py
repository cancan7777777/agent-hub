"""fsutil - 文件系统基础能力：内容指纹（带 stat 缓存）、Junction、备份、安全删除。"""
from __future__ import annotations
import _winapi, datetime, hashlib, json, os, shutil, subprocess, time, zipfile

USERPROFILE = os.path.expanduser("~")
_CACHE_FILE = None
_MEM: dict = {}          # path -> fingerprint dict
_TTL: dict = {}          # path -> (monotonic, result) 进程内瞬时缓存
TTL_SEC = 2.5


def set_cache_file(p: str):
    global _CACHE_FILE, _MEM
    _CACHE_FILE = p
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as fh:
                _MEM = json.load(fh)
        except Exception:
            _MEM = {}


def _flush():
    if not _CACHE_FILE:
        return
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        tmp = _CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(_MEM, fh)
        os.replace(tmp, _CACHE_FILE)
    except Exception:
        pass


def expand(p: str) -> str:
    return os.path.abspath(os.path.expandvars(p))


def _iter_stats(path: str):
    """(相对路径, mtime_ns, size) 三元组，尽量走 scandir 缓存的目录项信息。"""
    stack = [(path, "")]
    while stack:
        cur, rel = stack.pop()
        try:
            with os.scandir(cur) as it:
                for de in it:
                    r = rel + de.name
                    try:
                        if de.is_symlink():
                            yield (r, 0, 0)
                            continue
                        if de.is_dir(follow_symlinks=False):
                            stack.append((de.path, r + "/"))
                        elif de.is_file(follow_symlinks=False):
                            st = de.stat(follow_symlinks=False)
                            yield (r, st.st_mtime_ns, st.st_size)
                    except OSError:
                        yield (r, 0, 0)
        except OSError:
            return


def dir_sig(path: str) -> str:
    """廉价签名：只含相对路径 + mtime + 体积，不读文件内容。"""
    h = hashlib.sha256()
    for rel, mt, sz in sorted(_iter_stats(path)):
        h.update(rel.encode("utf-8", "replace"))
        h.update(b"|"); h.update(str(mt).encode()); h.update(b"|"); h.update(str(sz).encode())
    return h.hexdigest()[:20]


def dir_fingerprint(path: str, max_files: int = 5000) -> dict:
    """内容指纹。签名未变则复用磁盘缓存，签名变了才重新读内容。"""
    path = expand(path)
    # 多个 agent 目录经联接指向同一真源，按真实路径归并，指纹只算一次
    try:
        real = os.path.realpath(path)
    except OSError:
        real = path
    key = path.lower()
    rkey = "REAL::" + real.lower()
    now = time.monotonic()
    for kk in (key, rkey):
        hit = _TTL.get(kk)
        if hit and (now - hit[0]) < TTL_SEC:
            _TTL[key] = (now, hit[1])
            return dict(hit[1])
    try:
        pairs = sorted(_iter_stats(path))
    except OSError:
        return {"hash": "ERR", "files": 0, "bytes": 0, "listing": ""}
    n = len(pairs)
    total = sum(p[2] for p in pairs)
    if n > max_files:
        return {"hash": "TOO_LARGE", "files": n, "bytes": total, "listing": ""}
    stat_sig = hashlib.sha256()
    for rel, mt, sz in pairs:
        stat_sig.update(rel.encode("utf-8", "replace"))
        stat_sig.update(str(mt).encode()); stat_sig.update(str(sz).encode())
    sig = stat_sig.hexdigest()[:20]
    cached = _MEM.get(key) or _MEM.get(rkey)
    if cached and cached.get("sig") == sig:
        res = {"hash": cached["hash"], "files": cached["files"],
               "bytes": cached["bytes"], "listing": cached.get("listing", "")}
        _TTL[key] = _TTL[rkey] = (now, res)
        _MEM.setdefault(key, cached)
        return dict(res)
    h = hashlib.sha256()
    for rel, _mt, _sz in pairs:
        try:
            with open(os.path.join(path, rel.replace("/", os.sep)), "rb") as fh:
                while True:
                    blk = fh.read(1 << 16)
                    if not blk:
                        break
                    h.update(blk)
        except OSError:
            h.update(b"<unreadable>")
    out = {"hash": h.hexdigest()[:16], "files": n, "bytes": total,
           "listing": hashlib.sha256("\n".join(r for r, _, _ in pairs).encode("utf-8", "replace")).hexdigest()[:12]}
    out["sig"] = sig
    _MEM[key] = _MEM[rkey] = out
    _flush()
    _TTL[key] = _TTL[rkey] = (now, out)
    return dict(out)


def forget(path: str):
    k = expand(path).lower()
    _MEM.pop(k, None)
    _TTL.pop(k, None)
    _flush()


def invalidate_tree():
    """写操作后清空 TTL，强制重算。"""
    _TTL.clear()


def newest_mtime(path: str) -> float:
    best = 0.0
    try:
        for root, dirs, files in os.walk(path):
            for f in files:
                try:
                    best = max(best, os.path.getmtime(os.path.join(root, f)))
                except OSError:
                    pass
            break
        best = max(best, os.path.getmtime(path))
    except OSError:
        pass
    return best


def link_kind(path: str) -> str:
    if not os.path.lexists(path):
        return "missing"
    try:
        if os.path.islink(path):
            return "symlink"
        if os.path.isjunction(path):
            return "junction"
    except (OSError, AttributeError):
        pass
    return "real"


def read_target(path: str):
    try:
        return os.path.abspath(os.readlink(path))
    except OSError:
        return None


def make_junction(target: str, link: str) -> bool:
    target, link = expand(target), expand(link)
    try:
        if os.path.lexists(link):
            remove_path(link)
        _winapi.CreateJunction(target, link)
        forget(link)
        return True
    except OSError:
        try:
            r = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                               capture_output=True, text=True, timeout=15)
            return r.returncode == 0 and os.path.isjunction(link)
        except Exception:
            return False


def copy_tree(src: str, dst: str) -> bool:
    src, dst = expand(src), expand(dst)
    try:
        if os.path.lexists(dst):
            remove_path(dst)
        shutil.copytree(src, dst, symlinks=False,
                        ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
        forget(dst)
        return True
    except Exception:
        return False


def remove_path(path: str) -> bool:
    """联接只删链接本身；删实体目录时绝不跨重解析点。"""
    path = expand(path)
    kind = link_kind(path)
    try:
        if kind in ("junction", "symlink"):
            try:
                os.rmdir(path)
            except OSError:
                subprocess.run(["cmd", "/c", "rmdir", path], capture_output=True, timeout=15)
            forget(path)
            return not os.path.lexists(path)
        if os.path.isfile(path):
            os.remove(path)
            forget(path)
            return True
        if os.path.isdir(path):
            _safe_rmtree(path)
            forget(path)
            return not os.path.lexists(path)
    except Exception:
        return False
    return False


def _safe_rmtree(path: str):
    for name in os.listdir(path):
        child = os.path.join(path, name)
        if link_kind(child) in ("junction", "symlink"):
            if not remove_path(child):
                raise RuntimeError("无法移除联接: " + child)
            continue
        if os.path.isdir(child):
            _safe_rmtree(child)
        else:
            os.remove(child)
    os.rmdir(path)


def backup_tree(path: str, backups_dir: str, label: str):
    path, backups_dir = expand(path), expand(backups_dir)
    if not os.path.isdir(path) or link_kind(path) != "real":
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in label)
    zp = os.path.join(backups_dir, f"{stamp}-{safe}.zip")
    try:
        os.makedirs(backups_dir, exist_ok=True)
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            base = os.path.dirname(path)
            for root, dirs, files in os.walk(path):
                for f in files:
                    fp = os.path.join(root, f)
                    if link_kind(fp) in ("junction", "symlink"):
                        continue
                    try:
                        z.write(fp, os.path.relpath(fp, base))
                    except OSError:
                        pass
        return zp
    except Exception:
        return None
