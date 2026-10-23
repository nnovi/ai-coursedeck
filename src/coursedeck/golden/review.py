"""Local web UI to review golden annotations side by side with the PDF.

    python -m coursedeck.golden.review            # opens http://127.0.0.1:8765

Left: the PDF (browser viewer) or its text layer page by page. Right: the editable card;
fields changed relative to the first draft are highlighted. Saving validates the card
against LectureCard.
"""

import argparse
import json
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import unquote

import pymupdf
from pydantic import ValidationError

from coursedeck.dataset.manifest import ManifestRow, read_manifest
from coursedeck.golden import store
from coursedeck.schema import FIELD_GROUPS, Discipline, DocType, Term

GOLDEN_MANIFEST = Path("data/manifests/golden.csv")
UI_HTML = Path(__file__).with_name("review.html")


def doc_summary(row: ManifestRow) -> dict:
    rec = store.load(row.doc_id) or {}
    return {
        "doc_id": row.doc_id,
        "lang": row.lang,
        "n_pages": row.n_pages,
        "text_layer": row.text_layer,
        "layout": row.layout,
        "status": rec.get("status", "missing"),
    }


class Handler(BaseHTTPRequestHandler):
    rows: ClassVar[dict[str, ManifestRow]] = {}  # set once in main()

    def log_message(self, fmt: str, *args) -> None:  # keep the console quiet
        pass

    def _send(self, body: bytes, ctype: str, status: int = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = HTTPStatus.OK) -> None:
        self._send(json.dumps(data, ensure_ascii=False).encode(), "application/json", status)

    def _row(self, doc_id: str) -> ManifestRow | None:
        row = self.rows.get(doc_id)
        if row is None:
            self._json({"error": f"unknown doc_id {doc_id}"}, HTTPStatus.NOT_FOUND)
        return row

    def do_GET(self) -> None:
        parts = [unquote(p) for p in self.path.split("?")[0].strip("/").split("/")]
        if parts == [""]:
            return self._send(UI_HTML.read_bytes(), "text/html; charset=utf-8")
        if parts == ["api", "meta"]:
            return self._json({
                "groups": FIELD_GROUPS,
                "enums": {
                    "discipline": [e.value for e in Discipline],
                    "doc_type": [e.value for e in DocType],
                    "term": [e.value for e in Term],
                },
                "docs": [doc_summary(r) for r in self.rows.values()],
            })
        if len(parts) == 3 and parts[:2] == ["api", "doc"]:
            if row := self._row(parts[2]):
                return self._json({"manifest": row.__dict__, "record": store.load(row.doc_id)})
            return None
        if len(parts) == 3 and parts[:2] == ["api", "text"]:
            if row := self._row(parts[2]):
                with pymupdf.open(row.path) as doc:
                    return self._json([page.get_text() for page in doc])
            return None
        if len(parts) == 2 and parts[0] == "pdf":
            if row := self._row(parts[1].removesuffix(".pdf")):
                return self._send(row.path.read_bytes(), "application/pdf")
            return None
        return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parts = [unquote(p) for p in self.path.strip("/").split("/")]
        if not (len(parts) == 3 and parts[:2] == ["api", "doc"]):
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        if not (row := self._row(parts[2])):
            return None
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        try:
            rec = store.save(row.doc_id, body["card"], body.get("notes", ""), body["status"])
        except ValidationError as e:
            errors = [{"field": ".".join(map(str, err["loc"])), "msg": err["msg"]}
                      for err in e.errors()]
            return self._json({"errors": errors}, HTTPStatus.UNPROCESSABLE_ENTITY)
        except ValueError as e:
            return self._json({"errors": [{"field": "status", "msg": str(e)}]},
                              HTTPStatus.UNPROCESSABLE_ENTITY)
        return self._json({"record": rec, "summary": doc_summary(row)})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--manifest", type=Path, default=GOLDEN_MANIFEST)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    Handler.rows = {r.doc_id: r for r in read_manifest(args.manifest)}
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Reviewing {len(Handler.rows)} documents at {url} (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
