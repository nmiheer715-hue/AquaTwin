"""CONCEPT_NOTE.md -> docs/AquaTwin_Concept_Note.pdf (A4, via Edge headless). Prints the page count."""
import os, re, subprocess, markdown
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
md = open(os.path.join(ROOT, "CONCEPT_NOTE.md"), encoding="utf-8").read()
body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
css = """
@page { size: A4; margin: 15mm 16mm 14mm 16mm; }
body { font-family: 'Segoe UI', Inter, Arial, sans-serif; font-size: 10pt; line-height: 1.38; color: #111; }
h1 { font-size: 17pt; margin: 0 0 4pt; color: #0b3d4a; }
h2 { font-size: 12.5pt; margin: 10pt 0 3pt; color: #0b3d4a; border-bottom: 1px solid #cfdde2; padding-bottom: 1pt; }
p { margin: 3pt 0; } ul, ol { margin: 2pt 0 4pt 16pt; padding: 0; } li { margin: 1pt 0; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0; font-size: 8.8pt; }
th, td { border: 1px solid #c9d6db; padding: 2.5pt 4pt; vertical-align: top; text-align: left; }
th { background: #eaf3f5; }
pre { font-size: 7.3pt; line-height: 1.25; background: #f4f8f9; border: 1px solid #d5e2e6; padding: 5pt; white-space: pre; overflow: hidden; margin: 4pt 0; }
code { font-family: Consolas, monospace; } hr { border: 0; border-top: 1px solid #cfdde2; margin: 5pt 0; }
a { color: #0b6e85; text-decoration: none; }
"""
html = f"<!doctype html><html><head><meta charset='utf-8'><title>AquaTwin concept note</title><style>{css}</style></head><body>{body}</body></html>"
src = os.path.join(HERE, "concept_note.html"); open(src, "w", encoding="utf-8").write(html)
pdf = os.path.join(HERE, "AquaTwin_Concept_Note.pdf")
edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", "file:///" + src.replace("\\", "/")], check=True, capture_output=True, timeout=120)
pages = len(re.findall(rb"/Type\s*/Page[^s]", open(pdf, "rb").read()))
print(f"{pdf}: {pages} pages")
