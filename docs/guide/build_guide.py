"""Build the UniTask feature guide: guide.html (+ PDF via headless Edge/Chrome).

Run:  python docs/guide/build_guide.py
Screenshots come from docs/guide/shots (made by capture.js through Playwright).
"""

import base64
import html
import subprocess
import sys
from datetime import date
from pathlib import Path

from content import ANSWERS, DEMO_SCRIPT, INTRO, NOVEL, SECTIONS, STACK

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]


def img(name: str, caption: str = "", cls: str = "") -> str:
    path = SHOTS / f"{name}.png"
    if not path.exists():
        return f'<div class="missing">[screenshot {name} not captured]</div>'
    data = base64.b64encode(path.read_bytes()).decode()
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return f'<figure class="{cls}"><img src="data:image/png;base64,{data}" alt="{html.escape(caption or name)}">{cap}</figure>'


def md(text: str) -> str:
    """Tiny formatter: **bold** and `code`, already-trusted content."""
    out = html.escape(text)
    parts = out.split("**")
    out = "".join(f"<strong>{p}</strong>" if i % 2 else p for i, p in enumerate(parts))
    parts = out.split("`")
    return "".join(f"<code>{p}</code>" if i % 2 else p for i, p in enumerate(parts))


def section(n: int, s: dict) -> str:
    rows = []
    for label, key in (("What it shows", "shows"), ("How it helps the student", "helps"), ("Show it in the demo", "demo")):
        if s.get(key):
            items = s[key] if isinstance(s[key], list) else [s[key]]
            bullets = "".join(f"<li>{md(i)}</li>" for i in items)
            rows.append(f'<div class="block"><h4>{label}</h4><ul>{bullets}</ul></div>')
    figures = "".join(img(name, cap, cls) for name, cap, cls in s.get("images", []))
    novel = f'<p class="novel"><span>New idea</span>{md(s["novel"])}</p>' if s.get("novel") else ""
    return f"""
<section class="screen{' phone-section' if any(c == 'phone' for _, _, c in s.get('images', [])) else ''}">
  <h2><span class="num">{n:02d}</span>{html.escape(s['title'])}</h2>
  <p class="lede">{md(s['lede'])}</p>
  {figures}
  {novel}
  <div class="blocks">{''.join(rows)}</div>
</section>"""


CSS = """
@page { size: A4; margin: 14mm 13mm 16mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, sans-serif; color: #1c1b18; font-size: 10.2pt; line-height: 1.45; margin: 0; }
h1, h2, h3 { font-family: Georgia, 'Times New Roman', serif; font-weight: 400; letter-spacing: -0.01em; margin: 0; }
.cover { height: 265mm; display: flex; flex-direction: column; justify-content: space-between; padding: 18mm 4mm 6mm; page-break-after: always; }
.cover .brand { font-family: Georgia, serif; font-size: 22pt; }
.cover h1 { font-size: 40pt; line-height: 1.05; max-width: 15ch; margin-top: 10mm; }
.cover h1 em { color: #c2410c; }
.cover .sub { font-size: 13pt; color: #47443e; margin-top: 6mm; max-width: 52ch; }
.cover .meta { font-size: 9pt; color: #858074; border-top: 1px solid #c9c4b8; padding-top: 3mm; }
.cover figure { margin: 8mm 0 0; }
.kicker { font-family: Consolas, monospace; font-size: 8pt; letter-spacing: 0.1em; text-transform: uppercase; color: #858074; }
.page { page-break-before: always; }
h2 { font-size: 20pt; margin: 0 0 3mm; display: flex; align-items: baseline; gap: 4mm; }
h2 .num { font-family: Consolas, monospace; font-size: 10pt; color: #c2410c; }
h3 { font-size: 14pt; margin: 6mm 0 2mm; }
h4 { font-family: 'Segoe UI', sans-serif; font-size: 8.5pt; text-transform: uppercase; letter-spacing: 0.06em; color: #858074; margin: 0 0 1.5mm; font-weight: 600; }
.lede { font-size: 11pt; color: #2e2c28; margin: 0 0 3mm; }
.screen { page-break-before: always; }
.screen.cont { page-break-before: auto; margin-top: 8mm; }
figure { margin: 0 0 3mm; break-inside: avoid; }
figure img { width: 100%; max-height: 112mm; object-fit: cover; object-position: top left; border: 1px solid #dfdbd1; border-radius: 6px; display: block; }
figure.half img { max-height: 58mm; }
figure.short img { max-height: 88mm; }
figure.phone { width: 34%; float: left; margin-right: 6mm; }
figure.phone img { max-height: 150mm; object-fit: contain; }
.screen::after { content: ''; display: block; clear: both; }
.screen.phone-section .blocks { grid-template-columns: 1fr; }
figure.half { display: inline-block; width: 49%; vertical-align: top; margin-right: 1%; }
figure.small img { width: 70%; }
figcaption { font-size: 8.3pt; color: #858074; margin-top: 1mm; }
.blocks { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4mm; break-inside: avoid; }
.block { border-top: 2px solid #1c1b18; padding-top: 2mm; }
.block ul { margin: 0; padding-left: 4mm; }
.block li { margin-bottom: 1.2mm; }
.novel { background: #f6e4da; border-left: 3px solid #c2410c; padding: 2.5mm 3.5mm; margin: 0 0 3mm; break-inside: avoid; }
.novel span { font-family: Consolas, monospace; font-size: 7.5pt; text-transform: uppercase; letter-spacing: 0.08em; color: #c2410c; margin-right: 2.5mm; }
table { width: 100%; border-collapse: collapse; font-size: 9.2pt; margin: 2mm 0 4mm; }
th { text-align: left; border-bottom: 1.5px solid #1c1b18; padding: 1.5mm 2mm 1.5mm 0; font-size: 8.5pt; }
td { border-bottom: 1px solid #dfdbd1; padding: 1.8mm 2mm 1.8mm 0; vertical-align: top; }
td:first-child { font-weight: 600; width: 30%; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; }
.card { border: 1px solid #dfdbd1; border-radius: 6px; padding: 3mm 4mm; break-inside: avoid; }
.card h3 { margin-top: 0; font-size: 12pt; }
ol.script li { margin-bottom: 1.6mm; }
code { font-family: Consolas, monospace; font-size: 0.92em; background: #ebe8e0; padding: 0 1mm; border-radius: 2px; }
.missing { padding: 6mm; border: 1px dashed #c9c4b8; color: #858074; text-align: center; margin-bottom: 3mm; }
.toc { columns: 2; column-gap: 8mm; padding-left: 5mm; }
.toc li { margin-bottom: 1.2mm; }
"""


def build() -> Path:
    toc = "".join(f"<li>{html.escape(s['title'])}</li>" for s in SECTIONS)
    novel = "".join(f'<div class="card"><h3>{html.escape(t)}</h3><p>{md(d)}</p></div>' for t, d in NOVEL)
    stack = "".join(f"<tr><td>{html.escape(a)}</td><td>{md(b)}</td></tr>" for a, b in STACK)
    answers = "".join(f'<div class="card"><h3>{html.escape(q)}</h3><p>{md(a)}</p></div>' for q, a in ANSWERS)
    demo = "".join(f"<li>{md(step)}</li>" for step in DEMO_SCRIPT)
    screens = "".join(section(i, s) for i, s in enumerate(SECTIONS, start=3))
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>UniTask — Feature Guide</title><style>{CSS}</style></head><body>
<div class="cover">
  <div class="brand">UniTask <span class="kicker">academic assistant</span></div>
  <div>
    <h1>Know what to do <em>next</em> — and actually learn it.</h1>
    <p class="sub">{md(INTRO['tagline'])}</p>
    {img('01-today', 'The Today screen: one clear next action, the day, exams and what to study.')}
  </div>
  <div class="meta">Feature guide · every screen, what it does and how it helps the student · {date.today():%d %B %Y} · screenshots from the running app with synthetic demo data</div>
</div>

<div>
  <h2><span class="num">01</span>UniTask in one page</h2>
  <p class="lede">{md(INTRO['problem'])}</p>
  <div class="grid2">
    <div class="card"><h3>What a student gets</h3><ul>{''.join(f'<li>{md(x)}</li>' for x in INTRO['gets'])}</ul></div>
    <div class="card"><h3>The principles</h3><ul>{''.join(f'<li>{md(x)}</li>' for x in INTRO['principles'])}</ul></div>
  </div>
  <h3>Contents</h3>
  <ol class="toc" start="3">{toc}</ol>
</div>

<div class="page">
  <h2><span class="num">02</span>What is new here</h2>
  <p class="lede">The points to convey. Most student apps list deadlines or chat generically. UniTask decides, plans and teaches from the student's own material and record.</p>
  <div class="grid2">{novel}</div>
</div>
{screens}
<div class="page">
  <h2><span class="num">{len(SECTIONS) + 3:02d}</span>How it is built (AWS)</h2>
  <table><tr><th>Part</th><th>What runs it</th></tr>{stack}</table>
  <h3>Five-minute demo script</h3>
  <ol class="script">{demo}</ol>
</div>
<div class="page">
  <h2><span class="num">{len(SECTIONS) + 4:02d}</span>Honest answers to hard questions</h2>
  <div class="grid2">{answers}</div>
</div>
</body></html>"""
    out = HERE / "UniTask_Feature_Guide.html"
    out.write_text(doc, encoding="utf-8")
    return out


def to_pdf(html_path: Path) -> Path | None:
    pdf = html_path.with_suffix(".pdf")
    for browser in BROWSERS:
        if Path(browser).exists():
            subprocess.run(
                [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                 f"--print-to-pdf={pdf}", html_path.as_uri()],
                check=False, capture_output=True, timeout=180,
            )
            if pdf.exists():
                return pdf
    return None


if __name__ == "__main__":
    page = build()
    print("html:", page)
    if "--no-pdf" not in sys.argv:
        print("pdf:", to_pdf(page))
