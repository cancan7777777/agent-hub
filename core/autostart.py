"""autostart - 开机自启（当前用户，无需管理员权限）。

做法：把 pythonw.exe + server.py + 端口 直接写进
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run。
登录时由系统直接拉起，不经过中间脚本，也不弹控制台窗口。

只动当前用户的启动项，不注册系统服务，因此不需要管理员权限，
改完也不需要重启就能生效。
"""
from __future__ import annotations
import json, os, sys

import registry

VALUE_NAME = "AgentHub"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
DEFAULT_PORT = 8765
SCRIPT = os.path.join(registry.CORE, "server.py")
# 旧版经 wscript 中转的启动器，检测到就顺手清掉
LEGACY_HELPER = os.path.join(registry.DATA, "autostart.vbs")


def supported() -> bool:
    return os.name == "nt"


def pythonw_path() -> str:
    """取与当前解释器同目录的 pythonw.exe，保证版本一致且不弹控制台窗口。"""
    exe = sys.executable or ""
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.isfile(cand):
        return cand
    if exe.lower().endswith(".exe"):
        alt = exe[:-4] + "w.exe"
        if os.path.isfile(alt):
            return alt
    return exe or "pythonw.exe"


def command(port: int = DEFAULT_PORT) -> str:
    """启动项内容。--no-browser 让开机时只起服务，不弹浏览器。"""
    return '"%s" "%s" %d --no-browser' % (pythonw_path(), SCRIPT, int(port))


def _read_value():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, VALUE_NAME)[0]
    except OSError:
        return None


def _write_value(data: str):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_EXPAND_SZ, data)


def _delete_value():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, VALUE_NAME)
    except FileNotFoundError:
        pass


def _drop_legacy():
    try:
        if os.path.isfile(LEGACY_HELPER):
            os.remove(LEGACY_HELPER)
    except OSError:
        pass


def status(port: int = DEFAULT_PORT) -> dict:
    """是否已注册、注册指向哪里。界面首屏要显示真实状态，不能靠猜。"""
    out = dict(supported=supported(), enabled=False, value_name=VALUE_NAME,
               python=pythonw_path(), script=SCRIPT, port=int(port),
               command=None, expected=command(port), note="")
    if not out["supported"]:
        out["note"] = "开机自启仅在 Windows 下提供"
        return out
    try:
        cur = _read_value()
    except Exception as e:
        out["note"] = "读取启动项失败：" + str(e)
        return out
    out["command"] = cur
    if cur:
        # 认这条目是不是我们的：脚本路径一致即可，端口换了也算开着
        out["enabled"] = os.path.normcase(SCRIPT) in os.path.normcase(str(cur))
    if not os.path.isfile(out["python"]):
        out["note"] = "找不到 pythonw.exe，请先安装 Python 3.11 以上再开启"
    return out


def enable(port: int = DEFAULT_PORT) -> dict:
    if not supported():
        return dict(ok=False, error="开机自启仅在 Windows 下提供")
    py = pythonw_path()
    if not os.path.isfile(py):
        return dict(ok=False, error="找不到 pythonw.exe：" + py)
    if not os.path.isfile(SCRIPT):
        return dict(ok=False, error="找不到 server.py：" + SCRIPT)
    try:
        _write_value(command(port))
        _drop_legacy()
    except Exception as e:
        return dict(ok=False, error=str(e))
    return dict(ok=True, **status(port))


def disable() -> dict:
    if not supported():
        return dict(ok=False, error="开机自启仅在 Windows 下提供")
    try:
        _delete_value()
        _drop_legacy()
    except Exception as e:
        return dict(ok=False, error=str(e))
    return dict(ok=True, **status())


def set_enabled(on: bool, port: int = DEFAULT_PORT) -> dict:
    r = enable(port) if on else disable()
    if not r.get("ok"):
        r.setdefault("enabled", status(port)["enabled"])
    return r


if __name__ == "__main__":  # 命令行自检：python autostart.py
    print(json.dumps(status(), ensure_ascii=False, indent=2))