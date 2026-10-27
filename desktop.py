"""desktop - AgentHub 桌面壳：原生窗口 + 内嵌本地服务，不开浏览器。

打包：PyInstaller 把本文件与 core/、ui/ 一起打进 exe。
运行逻辑：
  1. 数据根固定在 %LOCALAPPDATA%\\AgentHub（可写），首次运行时把
     D:\\agent-hub\\data 迁移过来（仅当目标为空）。
  2. 在后台线程起 core.server 的 HubServer（只监听 127.0.0.1）。
  3. 用 pywebview(WebView2) 开一个原生窗口加载本机地址。
"""
from __future__ import annotations
import os
import shutil
import sys
import threading


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _base_dir() -> str:
    """exe 所在目录（资源、图标用它）。"""
    if _is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _data_root() -> str:
    """可写数据根：exe 模式放 %LOCALAPPDATA%\\AgentHub，源码模式就是项目根。"""
    if _is_frozen():
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "AgentHub")
    return _base_dir()


def _migrate_data(dst_data: str):
    """首次运行：把源码项目里的 data 迁到 %LOCALAPPDATA%，避免两套状态。"""
    if os.path.isdir(dst_data) and os.listdir(dst_data):
        return
    for cand in (r"D:\agent-hub\data", os.path.join(_base_dir(), "data")):
        if os.path.isdir(cand) and os.listdir(cand):
            os.makedirs(os.path.dirname(dst_data), exist_ok=True)
            try:
                shutil.copytree(cand, dst_data)
            except Exception:
                pass
            return


def _prepare():
    root = _data_root()
    os.environ["AGENTHUB_ROOT"] = root
    os.makedirs(root, exist_ok=True)
    data = os.path.join(root, "data")
    _migrate_data(data)
    os.makedirs(os.path.join(root, "logs"), exist_ok=True)
    if _is_frozen():
        os.environ["AGENTHUB_UI"] = os.path.join(sys._MEIPASS, "ui")  # noqa: SLF001
    else:
        os.environ.setdefault("AGENTHUB_UI", os.path.join(_base_dir(), "ui"))


def _start_server() -> int:
    """导入 core.server 并在后台线程起服务，返回实际端口。"""
    core_dir = os.path.join(_base_dir(), "core") if not _is_frozen() else sys._MEIPASS
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    import server as hub_server  # noqa: PLC0415  core/server.py

    port = hub_server.free_port(8765)
    srv = hub_server.HubServer(("127.0.0.1", port), hub_server.Handler)
    hub_server._PORT[0] = port
    hub_server.get_scan()  # 预热，窗口打开时首屏就是完整数据
    threading.Thread(
        target=srv.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True
    ).start()
    return port


def main():
    _prepare()
    port = _start_server()
    url = f"http://127.0.0.1:{port}/"

    import webview  # pywebview

    webview.create_window(
        "AI Agent Hub",
        url,
        width=1280,
        height=860,
        min_size=(960, 640),
        background_color="#f3f6fb",
    )
    webview.start(gui="edgechromium")


if __name__ == "__main__":
    main()
