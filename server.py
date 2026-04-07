import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from habitflow_app import HabitFlowApp


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = HabitFlowApp()


class LocalHabitFlowHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/"):
            self.respond(app.handle("GET", self.path, self.headers))
            return
        return super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        self.respond(app.handle("POST", self.path, self.headers, body))

    def do_DELETE(self):
        self.respond(app.handle("DELETE", self.path, self.headers))

    def respond(self, response):
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        for key, value in response.headers or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(response.body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    os.chdir(BASE_DIR)
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), LocalHabitFlowHandler)
    print(f"HabitFlow server running at http://{host}:{port}")
    server.serve_forever()
