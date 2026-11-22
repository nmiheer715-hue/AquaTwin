"""Turn a full-document dashboard into a page body for publishing as an
Artifact (the host adds <!doctype>, <html>, <head> and <body>).

    python -m aquatwin.to_artifact in.html out.html
"""
import re
import sys


def convert(src, dst):
    h = open(src, encoding="utf-8").read()
    h = re.sub(r"<!doctype html>\s*", "", h, flags=re.I)
    h = re.sub(r"<html[^>]*>\s*<head>\s*", "", h, flags=re.I)
    h = re.sub(r'<meta charset="utf-8">\s*', "", h, flags=re.I)
    h = re.sub(r'<meta name="viewport"[^>]*>\s*', "", h, flags=re.I)
    h = re.sub(r"</head>\s*<body>", "", h, flags=re.I)
    h = re.sub(r"</body>\s*</html>\s*$", "", h, flags=re.I)
    i = h.find("<title>")
    h = h[i:] if i > 0 else h                       # title first, within the first 8 KB
    h = h.replace("</title>", '</title>\n<meta name="claude:viewport-fit-sides" content="cover">', 1)
    open(dst, "w", encoding="utf-8").write(h)


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
