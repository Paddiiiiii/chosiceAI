"""
任务路由系统 - 统一启动入口
用法: python main.py
"""
import subprocess
import sys
import os
import signal
import socket
import time
import http.server
import socketserver
import urllib.request
import threading

# ─────────── 配置 ───────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")
ES_BAT = os.path.join(BASE_DIR, "soft", "elasticsearch-8.12.0", "bin", "elasticsearch.bat")

BACKEND_PORT = 8000
FRONTEND_PORT = 3010
ES_PORT = 9200

BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
ES_URL = f"http://127.0.0.1:{ES_PORT}"


# ─────────── 工具函数 ───────────

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def kill_port(port):
    """杀掉占用指定端口的进程"""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, encoding="gbk", errors="ignore"
        )
        for line in result.stdout.strip().split("\n"):
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = int(parts[-1])
                if pid > 0:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True)
                    print(f"  已释放端口 {port} (PID {pid})")
                    time.sleep(1)
                    return True
    except Exception as e:
        print(f"  释放端口失败: {e}")
    return False


def wait_for_service(url, name, timeout=60):
    """等待服务就绪"""
    for i in range(timeout // 2):
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2):
                return True
        except Exception:
            pass
        time.sleep(2)
        if i % 5 == 4:
            print(f"  等待 {name} 启动中... ({(i+1)*2}s)")
    return False


# ─────────── 前端服务 ───────────

class FrontendHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIST, **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._proxy()
        elif not os.path.exists(os.path.join(FRONTEND_DIST, self.path.lstrip("/"))) or self.path == "/":
            self.path = "/index.html"
            super().do_GET()
        else:
            super().do_GET()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def _proxy(self):
        url = BACKEND_URL + self.path
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "transfer-encoding")}
        req = urllib.request.Request(url, data=body, method=self.command, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() not in ("transfer-encoding",):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, format, *args):
        pass  # 静默日志，避免刷屏


def start_frontend():
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("0.0.0.0", FRONTEND_PORT), FrontendHandler)
    httpd.serve_forever()


# ─────────── 主流程 ───────────

def main():
    processes = []

    print("=" * 50)
    print("  任务路由系统 - 启动中")
    print("=" * 50)

    # ── 1. Elasticsearch ──
    print(f"\n[1/3] Elasticsearch (端口 {ES_PORT})")
    if is_port_in_use(ES_PORT):
        print("  ✓ 已在运行")
    elif os.path.exists(ES_BAT):
        print("  启动中...")
        p = subprocess.Popen(
            [ES_BAT],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        processes.append(p)
        if wait_for_service(ES_URL, "Elasticsearch"):
            print("  ✓ 启动成功")
        else:
            print("  ✗ 启动超时，BM25 检索可能不可用")
    else:
        print(f"  ✗ 未找到 ES，跳过 (BM25 检索不可用)")

    # ── 2. 后端 ──
    print(f"\n[2/3] 后端 API (端口 {BACKEND_PORT})")
    if is_port_in_use(BACKEND_PORT):
        print(f"  端口 {BACKEND_PORT} 被占用，正在释放...")
        kill_port(BACKEND_PORT)
        time.sleep(1)

    print("  启动中...")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", str(BACKEND_PORT)],
        cwd=BACKEND_DIR,
    )
    processes.append(backend_proc)

    if wait_for_service(f"{BACKEND_URL}/health", "后端", timeout=30):
        print("  ✓ 启动成功")
    else:
        print("  ✗ 后端启动失败!")
        return

    # ── 3. 前端 ──
    print(f"\n[3/3] 前端界面 (端口 {FRONTEND_PORT})")
    if not os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):
        print("  ✗ 前端未编译，请先运行: cd frontend && npm run build")
        return

    if is_port_in_use(FRONTEND_PORT):
        print(f"  端口 {FRONTEND_PORT} 被占用，正在释放...")
        kill_port(FRONTEND_PORT)
        time.sleep(1)

    frontend_thread = threading.Thread(target=start_frontend, daemon=True)
    frontend_thread.start()
    time.sleep(1)
    if is_port_in_use(FRONTEND_PORT):
        print("  ✓ 启动成功")
    else:
        print("  ✗ 前端启动失败!")

    # ── 完成 ──
    print("\n" + "=" * 50)
    print("  ✓ 所有服务已启动")
    print("=" * 50)
    print(f"\n  前端界面: http://localhost:{FRONTEND_PORT}")
    print(f"  API 文档: http://localhost:{BACKEND_PORT}/docs")
    print(f"\n  按 Ctrl+C 停止所有服务\n")

    # 等待退出
    try:
        backend_proc.wait()
    except KeyboardInterrupt:
        print("\n正在停止所有服务...")
        for p in processes:
            try:
                p.terminate()
            except Exception:
                pass
        print("已停止")


if __name__ == "__main__":
    main()
