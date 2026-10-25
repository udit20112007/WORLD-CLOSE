#!/usr/bin/env python3
"""Bundle site/index.html with the exchange list and summaries into one HTML
file. Charts in the bundle use invented price paths, so it is for previewing
the design only.

    python scripts/build_preview.py [site_data_dir] [output.html]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "site" / "data"
out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "preview.html"

files = {"exchanges.json": json.loads((data_dir / "exchanges.json").read_text(encoding="utf-8"))}
for ex in files["exchanges.json"]["exchanges"]:
    p = data_dir / ex["code"] / "summary.json"
    if p.exists():
        files[f"{ex['code']}/summary.json"] = json.loads(p.read_text(encoding="utf-8"))
payload = {"demo": True, "files": files}
blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
out.write_text(html.replace("<!--EMBED_DATA-->", f"<script>window.__WC_PREVIEW__={blob};</script>"), encoding="utf-8")
print(f"Wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
