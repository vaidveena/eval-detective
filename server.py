"""Local-only UI server. Run: python3 server.py"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit
from detective import judge, samples

ROOT = Path(__file__).parent


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, code, data, content_type="application/json"):
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urlsplit(self.path).path
        files = {"/": ("index.html", "text/html; charset=utf-8"),
                 "/app.js": ("app.js", "text/javascript"),
                 "/style.css": ("style.css", "text/css")}
        if route == "/examples.json":
            return self.send(200, samples())
        if route in files:
            name, kind = files[route]
            return self.send(200, (ROOT / name).read_bytes(), kind)
        self.send(404, {"error": "Not found"})

    def do_POST(self):
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if host not in ("127.0.0.1:4173", "localhost:4173") or (origin and origin != "http://" + host):
            return self.send(403, {"error": "Only same-origin local requests are accepted."})
        if self.path != "/api/compare":
            return self.send(404, {"error": "Not found"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 210000:
                raise ValueError("Request is empty or too large.")
            case = json.loads(self.rfile.read(size))
            result = judge(case)
            self.send(200, result)
        except (ValueError, UnicodeDecodeError) as exc:
            self.send(400, {"error": str(exc)})
        except Exception:
            self.send(500, {"error": "Comparison failed; no verdict accepted."})


if __name__ == "__main__":
    print("Eval Detective: http://127.0.0.1:4173 (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", 4173), Handler).serve_forever()
