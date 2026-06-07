"""Minimal HTML dashboard for CABS belief store (no extra deps)."""

from __future__ import annotations

import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_html(run_dir: Path) -> str:
    store = run_dir / "belief_store"
    beliefs = _load_json(store / "beliefs.json").get("beliefs", [])
    contradictions = _load_json(store / "contradictions.json").get("contradictions", [])
    questions = _load_json(store / "research_questions.json").get("research_questions", [])

    timeline = []
    for gen_dir in sorted(run_dir.glob("gen_*"), key=lambda p: int(p.name.split("_")[1])):
        report_path = gen_dir / "cabs_report.json"
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            timeline.append(report)

    def section(title: str, items: list) -> str:
        if not items:
            return f"<h2>{title}</h2><p><em>None yet</em></p>"
        rows = "".join(f"<li><pre>{json.dumps(i, indent=2)}</pre></li>" for i in items)
        return f"<h2>{title} ({len(items)})</h2><ul>{rows}</ul>"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>CABS Dashboard - {run_dir.name}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0; }}
h1 {{ color: #38bdf8; }}
h2 {{ color: #a5b4fc; margin-top: 2rem; }}
pre {{ background: #1e293b; padding: 1rem; border-radius: 8px; overflow-x: auto; font-size: 12px; }}
.muted {{ color: #94a3b8; }}
</style></head><body>
<h1>SIA-CABS Dashboard</h1>
<p class="muted">Run: {run_dir}</p>
{section("Beliefs", beliefs)}
{section("Contradictions", contradictions)}
{section("Research Questions", questions)}
<h2>Generation Reports ({len(timeline)})</h2>
<ul>{"".join(f"<li><pre>{json.dumps(t, indent=2)}</pre></li>" for t in timeline) or "<li><em>None</em></li>"}</ul>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a minimal CABS HTML dashboard")
    parser.add_argument("--run-dir", default="runs/run_showcase", help="Path to run directory")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    html = build_html(run_dir)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if urlparse(self.path).path in ("/", "/index.html"):
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            return

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"CABS dashboard: {url}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
