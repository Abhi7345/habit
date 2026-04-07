from http.server import BaseHTTPRequestHandler

from habitflow_app import HabitFlowApp


app = HabitFlowApp()


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.respond(app.handle("GET", self.path, self.headers))

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
