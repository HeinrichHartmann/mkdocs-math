"""Standalone HTTP server for on-demand PDF generation.

Run alongside `mkdocs serve` to provide draft PDFs via the header button.

Usage:
    python -m mkdocs_math.pdf_server [--port 8099] [--docs-dir docs]

The plugin reads MKDOCS_PDF_URL from the environment to render the button.
"""

import http.server
import logging
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

from .export import export_markdown, find_project_root

log = logging.getLogger("mkdocs_math.pdf_server")


class PDFHandler(http.server.BaseHTTPRequestHandler):
    docs_dir: Path
    project_dir: Path
    cache_dir: Path
    lock: threading.Lock

    def do_GET(self):
        path = unquote(urlparse(self.path).path)

        # Raw markdown serving: GET /raw/<src_path>
        if path.startswith("/raw/"):
            src_path = path[5:].lstrip("/")
            if not src_path.endswith(".md"):
                self.send_error(404)
                return
            src_file = (self.docs_dir / src_path).resolve()
            if not str(src_file).startswith(str(self.docs_dir.resolve())):
                self.send_error(403)
                return
            if not src_file.exists():
                self.send_error(404, f"Not found: {src_path}")
                return
            self._serve_raw(src_file)
            return

        src_path = path.lstrip("/")
        if not src_path or not src_path.endswith(".md"):
            self.send_error(404)
            return

        src_file = (self.docs_dir / src_path).resolve()

        # Path traversal guard
        if not str(src_file).startswith(str(self.docs_dir.resolve())):
            self.send_error(403)
            return
        if not src_file.exists():
            self.send_error(404, f"Not found: {src_path}")
            return

        # Mirror source directory structure to avoid name collisions
        cache_subdir = self.cache_dir / Path(src_path).parent
        cache_subdir.mkdir(parents=True, exist_ok=True)
        pdf_path = cache_subdir / f"{src_file.stem}.pdf"

        # Serve cached PDF if still fresh
        if pdf_path.exists() and pdf_path.stat().st_mtime > src_file.stat().st_mtime:
            self._serve_pdf(pdf_path)
            return

        # Generate (lock prevents duplicate work on concurrent requests)
        with self.lock:
            if pdf_path.exists() and pdf_path.stat().st_mtime > src_file.stat().st_mtime:
                self._serve_pdf(pdf_path)
                return
            try:
                ret = export_markdown(
                    src_file,
                    cache_subdir,
                    compile_to_pdf=True,
                    project_dir=self.project_dir,
                    with_url=False,
                    with_doi=False,
                )
                if ret != 0 or not pdf_path.exists():
                    self.send_error(500, "PDF generation failed")
                    return
            except Exception as e:
                log.error("PDF generation error: %s", e)
                self.send_error(500, str(e))
                return

        self._serve_pdf(pdf_path)

    def _serve_raw(self, src_file: Path):
        data = src_file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _serve_pdf(self, pdf_path: Path):
        data = pdf_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'inline; filename="{pdf_path.name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        log.info(format, *args)


def serve(port=8099, docs_dir=Path("docs"), project_dir=None):
    """Start the PDF server. Called by CLI or Makefile."""
    docs_dir = Path(docs_dir).resolve()
    project_dir = Path(project_dir).resolve() if project_dir else find_project_root(docs_dir).resolve()
    cache_dir = project_dir / "build" / "pdf"
    cache_dir.mkdir(parents=True, exist_ok=True)

    PDFHandler.docs_dir = docs_dir
    PDFHandler.project_dir = project_dir
    PDFHandler.cache_dir = cache_dir
    PDFHandler.lock = threading.Lock()

    server = http.server.HTTPServer(("127.0.0.1", port), PDFHandler)
    print(f"PDF server: http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="PDF generation server")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--docs-dir", type=Path, default=Path("docs"))
    parser.add_argument("--project-dir", type=Path, default=None)
    args = parser.parse_args()
    serve(args.port, args.docs_dir, args.project_dir)


if __name__ == "__main__":
    main()
