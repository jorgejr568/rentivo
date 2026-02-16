from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    do_HEAD = do_GET

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 2019), Handler).serve_forever()
