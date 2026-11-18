"""Axor document reader: pulls plain text out of many file types with the standard library only (works offline)."""
import os, re, io, json, zipfile, html, csv
from xml.etree import ElementTree as ET

CODE_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".py", ".js", ".mjs", ".html", ".htm", ".css", ".scss", ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb", ".php",
            ".swift", ".log", ".xml", ".yml", ".yaml", ".toml", ".sql", ".ts", ".tsx", ".jsx", ".sh", ".bat", ".ini", ".cfg", ".conf", ".env", ".tex", ".bib", ".r", ".m", ".ipynb", ".srt", ".vtt", ".rtf"}
OFFICE = {".docx", ".dotx", ".docm", ".pptx", ".potx", ".xlsx", ".xlsm", ".odt", ".ods", ".odp", ".epub", ".zip"}
SUPPORTED_LABEL = "Audio and video (MP3, MP4, WAV, M4A and more, transcribed from the sound), images (PNG, JPG, WebP, GIF), PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), OpenDocument (.odt .ods .odp), EPUB, RTF, CSV/TSV, JSON, Markdown, HTML/XML, plain text, source code in most languages, notebooks (.ipynb), subtitles, and ZIP files (with their readable contents). Up to 8 MB, or 60 MB for audio and video."


def _strip(x): return re.sub(r"\s+\n", "\n", re.sub(r"[ \t]+", " ", x)).strip()


def _xml_text(data, para_tags, text_tags):
    out, cur = [], []
    for ev, el in ET.iterparse(io.BytesIO(data), events=("end",)):
        t = el.tag.split("}")[-1]
        if t in text_tags and el.text: cur.append(el.text)
        elif t in ("tab",): cur.append("\t")
        elif t in ("br",): cur.append("\n")
        if t in para_tags: out.append("".join(cur)); cur = []
    if cur: out.append("".join(cur))
    return "\n".join(out)


def docx(path):
    z = zipfile.ZipFile(path); parts = []
    # tables come out in reading order because we walk document.xml linearly; each w:p ends a line
    parts.append(_xml_text(z.read("word/document.xml"), {"p"}, {"t"}))
    for n in z.namelist():
        if re.match(r"word/(footnotes|endnotes)\.xml$", n): parts.append(_xml_text(z.read(n), {"p"}, {"t"}))
    return "\n".join(p for p in parts if p.strip())


def pptx(path):
    z = zipfile.ZipFile(path); names = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)), key=lambda n: int(re.findall(r"\d+", n)[-1])); out = []
    for i, n in enumerate(names, 1):
        out.append(f"--- Slide {i} ---\n" + _xml_text(z.read(n), {"p"}, {"t"}))
        nn = f"ppt/notesSlides/notesSlide{re.findall(r'[0-9]+', n)[-1]}.xml"
        if nn in z.namelist():
            t = _xml_text(z.read(nn), {"p"}, {"t"}).strip()
            if t: out.append("Notes: " + t)
    return "\n".join(out)


def xlsx(path):
    z = zipfile.ZipFile(path); ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.iter():
            if si.tag.split("}")[-1] == "si": ss.append("".join(t.text or "" for t in si.iter() if t.tag.split("}")[-1] == "t"))
    names = {}
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml")); names = {i + 1: s.get("name") for i, s in enumerate(x for x in wb.iter() if x.tag.split("}")[-1] == "sheet")}
    except Exception: pass
    out = []
    for n in sorted((n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)), key=lambda n: int(re.findall(r"\d+", n)[-1])):
        idx = int(re.findall(r"\d+", n)[-1]); out.append(f"--- Sheet: {names.get(idx, idx)} ---")
        root = ET.fromstring(z.read(n))
        for row in (e for e in root.iter() if e.tag.split("}")[-1] == "row"):
            cells = []
            for c in row:
                v = next((x.text for x in c if x.tag.split("}")[-1] == "v"), None); t = c.get("t")
                if t == "s" and v is not None and v.isdigit() and int(v) < len(ss): v = ss[int(v)]
                elif t == "inlineStr": v = "".join(x.text or "" for x in c.iter() if x.tag.split("}")[-1] == "t")
                cells.append("" if v is None else str(v))
            if any(cells): out.append(" | ".join(cells))
        if len(out) > 4000: break
    return "\n".join(out)


def odf(path):
    z = zipfile.ZipFile(path); return re.sub(r"<[^>]+>", " ", re.sub(r"</text:(p|h)>|</table:table-row>", "\n", z.read("content.xml").decode("utf8", "ignore")))


def epub(path):
    z = zipfile.ZipFile(path); out = []
    for n in sorted(x for x in z.namelist() if x.lower().endswith((".xhtml", ".html", ".htm"))):
        out.append(html_text(z.read(n).decode("utf8", "ignore")))
    return "\n\n".join(out)


def html_text(t):
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t); t = re.sub(r"(?i)<br\s*/?>|</(p|div|h\d|li|tr)>", "\n", t)
    return _strip(html.unescape(re.sub(r"<[^>]+>", " ", t)))


def rtf(t):
    t = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes.fromhex(m.group(1)).decode("cp1252", "ignore"), t)
    t = re.sub(r"\\par[d]?", "\n", t); t = re.sub(r"\\[a-z]+-?\d* ?", "", t); t = re.sub(r"[{}]", "", t); return _strip(t)


def ipynb(t):
    nb = json.loads(t); out = []
    for c in nb.get("cells", []):
        src = "".join(c.get("source", [])); out.append(("```python\n" + src + "\n```") if c.get("cell_type") == "code" else src)
    return "\n\n".join(out)


def legacy_binary(data):
    """Old .doc/.xls/.ppt: pull out readable runs. Rough, and we say so."""
    runs = re.findall(rb"[\x20-\x7e\xa0-\xff]{6,}", data); u16 = re.findall(rb"(?:[\x20-\x7e]\x00){6,}", data)
    txt = "\n".join(r.decode("latin-1") for r in runs[:3000]) + "\n" + "\n".join(r.decode("utf-16le", "ignore") for r in u16[:3000])
    return _strip(txt)


def read_text(path, name, pdf_fn=None):
    """Returns (text, note). note is a short caveat or ''."""
    ext = os.path.splitext(name)[1].lower(); data_head = open(path, "rb").read(8)
    try:
        if ext == ".pdf" and pdf_fn: return pdf_fn(path), ""
        if ext in (".docx", ".dotx", ".docm"): return docx(path), ""
        if ext in (".pptx", ".potx"): return pptx(path), ""
        if ext in (".xlsx", ".xlsm"): return xlsx(path), ""
        if ext in (".odt", ".ods", ".odp"): return odf(path), ""
        if ext == ".epub": return epub(path), ""
        if ext == ".zip":
            z = zipfile.ZipFile(path); infos = z.infolist(); out = ["Files in this archive:"] + [f"{i.filename} ({i.file_size} bytes)" for i in infos[:200]]; shown = 0
            for i in infos:
                e = os.path.splitext(i.filename)[1].lower()
                if i.is_dir() or shown >= 6 or i.file_size > 3_000_000 or e not in CODE_EXT | {".docx", ".pptx", ".xlsx", ".odt"}: continue
                tmp = path + ".part" + e
                try:
                    open(tmp, "wb").write(z.read(i)); t, _ = read_text(tmp, i.filename)
                finally:
                    os.path.exists(tmp) and os.remove(tmp)
                if t.strip(): out.append(f"\n=== {i.filename} ===\n{t[:4000]}"); shown += 1
            return "\n".join(out), ""
        if ext in (".doc", ".xls", ".ppt") or data_head.startswith(b"\xd0\xcf\x11\xe0"):
            return legacy_binary(open(path, "rb").read()), "This is an old Office format, so the text extraction is approximate. Saving it as .docx or .pdf gives better results."
        raw = open(path, "rb").read(); t = raw.decode("utf-8", "ignore")
        if ext in (".html", ".htm", ".xml") and ext != ".xml": return html_text(t), ""
        if ext == ".rtf" or t.startswith("{\\rtf"): return rtf(t), ""
        if ext == ".ipynb": return ipynb(t), ""
        if ext in CODE_EXT: return t, ""
        # unknown extension: accept if it looks like text
        if raw and sum(c < 9 or (13 < c < 32) for c in raw[:4000]) / max(1, len(raw[:4000])) < 0.02: return t, ""
    except zipfile.BadZipFile: return "", "That file looks damaged or isn't really in that format."
    except Exception as e: return "", f"I couldn't open it ({type(e).__name__})."
    return "", ""
