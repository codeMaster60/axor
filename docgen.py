"""Axor documents + calendar dates: detect 'write my assignment' style requests, build a .docx with the standard library,
and understand day words such as 'tomorrow', '18th' or 'november 18'."""
import re, io, zipfile
from datetime import date, timedelta
from xml.sax.saxutils import escape

DOC_NOUN = r"(assignment|essay|report|letter|cover letter|resume|r[ée]sum[ée]|cv\b|abstract|article|case study|lab (report|record)|project report|term paper|thesis|proposal|speech|statement of purpose|sop\b|seminar|synopsis|literature review|document|worksheet|notes on|summary of|write-?up|blog post|press release|email to|application)"
DOC_VERB = r"(write|draft|prepare|create|generate|make|compose|give me|do my|help me (write|with)|need|i want|produce|complete)"
NOT_DOC = r"\b(image|photo|picture|pic|logo|poster|wallpaper|video|song|remind|reminder|alarm|timer|calendar|meeting|note to self|add (a )?note|open|play)\b"
def is_doc_request(raw):
    t = raw.lower().strip()
    if len(t.split()) < 3 or re.search(NOT_DOC, t) and not re.search(r"\b(assignment|essay|report|letter|resume|cover letter)\b", t): return False
    if re.search(r"\b(assignment|essay|term paper|lab report|project report|cover letter|resume|statement of purpose|literature review|case study)\b", t) and re.search(DOC_VERB + r"|\b(on|about|for|of)\b", t): return True
    return bool(re.search(DOC_VERB + r".{0,40}\b" + DOC_NOUN, t))

DOC_PROMPT = ("Write the complete document the person asked for, ready to submit. Output Markdown only. First line: '# ' followed by a clear title. "
 "Use '## ' section headings, short paragraphs and bullet points where they help. Match any word count, level or format they gave; otherwise aim for 500 to 800 words. "
 "No preface, no closing remarks, no questions. Never invent references, statistics, quotes or personal details: leave a [placeholder] for anything you do not know "
 "(name, roll number, course, date). Only list a References section if you cite well-known real sources.")

def doc_title(md):
    m = re.search(r"^\s*#\s+(.+)$", md, re.M)
    return (m.group(1).strip() if m else "Axor document")[:80]

# ---------- .docx writer ----------
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
def _runs(text, size=None, bold=False):
    out = []
    for part in re.split(r"(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`)", text):
        if not part: continue
        b, i = bold, False
        if part.startswith("**") and part.endswith("**") and len(part) > 4: part, b = part[2:-2], True
        elif part.startswith("`") and part.endswith("`") and len(part) > 2: part = part[1:-1]
        elif part.startswith("*") and part.endswith("*") and len(part) > 2: part, i = part[1:-1], True
        part = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", part)
        rp = ("<w:b/>" if b else "") + ("<w:i/>" if i else "") + (f'<w:sz w:val="{size}"/>' if size else "")
        out.append(f'<w:r><w:rPr>{rp}</w:rPr><w:t xml:space="preserve">{escape(part)}</w:t></w:r>')
    return "".join(out)
def _p(text, size=None, bold=False, before=0, after=120, indent=0, keep=False):
    ppr = f'<w:pPr>{"<w:keepNext/>" if keep else ""}<w:spacing w:before="{before}" w:after="{after}" w:line="300" w:lineRule="auto"/>' + (f'<w:ind w:left="{indent}" w:hanging="260"/>' if indent else "") + "</w:pPr>"
    return f"<w:p>{ppr}{_runs(text, size, bold)}</w:p>"
def _table(rows):
    cells = lambda r, hd: "".join(f'<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/></w:tcPr><w:p>{_runs(c.strip(), None, hd)}</w:p></w:tc>' for c in r)
    b = "".join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="999999"/>' for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
    return f'<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblBorders>{b}</w:tblBorders></w:tblPr>' + "".join(f"<w:tr>{cells(r, i == 0)}</w:tr>" for i, r in enumerate(rows)) + "</w:tbl>" + _p("", after=60)
def make_docx(md):
    body, lines, i = [], md.replace("\r", "").split("\n"), 0
    while i < len(lines):
        ln = lines[i].rstrip(); s = ln.strip()
        if not s: i += 1; continue
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i]): rows.append(lines[i].strip().strip("|").split("|"))
                i += 1
            body.append(_table(rows)); continue
        m = re.match(r"^(#{1,4})\s+(.*)", s)
        if m:
            lvl = len(m.group(1)); body.append(_p(m.group(2), {1: 40, 2: 30, 3: 26, 4: 24}[lvl], True, 240 if lvl > 1 else 0, 120, keep=True))
        elif re.match(r"^[-*+]\s+", s): body.append(_p("•  " + re.sub(r"^[-*+]\s+", "", s), indent=540, after=60))
        elif re.match(r"^\d+[.)]\s+", s): body.append(_p(s, indent=540, after=60))
        elif re.match(r"^(-{3,}|\*{3,})$", s): body.append(_p("", after=60))
        else: body.append(_p(re.sub(r"^>\s?", "", s)))
        i += 1
    doc = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{"".join(body)}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>'
    styles = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault></w:docDefaults></w:styles>'
    ct = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'
    rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
    drels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct); z.writestr("_rels/.rels", rels); z.writestr("word/document.xml", doc); z.writestr("word/styles.xml", styles); z.writestr("word/_rels/document.xml.rels", drels)
    return buf.getvalue()

# ---------- day words ----------
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
def parse_day(t, today=None):
    """Returns (first_day, number_of_days, label)."""
    today = today or date.today(); t = t.lower()
    if re.search(r"day after tomorrow", t): d = today + timedelta(days=2); return d, 1, "on " + d.strftime("%a %d %b")
    if "tomorrow" in t: return today + timedelta(days=1), 1, "tomorrow"
    if "yesterday" in t: return today - timedelta(days=1), 1, "yesterday"
    if re.search(r"this week|next 7 days|coming week|week ahead", t): return today, 7, "in the next 7 days"
    if "next week" in t: d = today + timedelta(days=7 - today.weekday()); return d, 7, "next week"
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s/-]*(?:of\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b(?:[\s,]*(\d{4}))?", t) or None
    mm = None if m else re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:[\s,]*(\d{4}))?", t)
    try:
        if m: d = date(int(m.group(3) or today.year), MONTHS[m.group(2)], int(m.group(1))); return d, 1, "on " + d.strftime("%a %d %b %Y")
        if mm: d = date(int(mm.group(3) or today.year), MONTHS[mm.group(1)], int(mm.group(2))); return d, 1, "on " + d.strftime("%a %d %b %Y")
        m = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", t)
        if m:
            y = int(m.group(3) or today.year); y += 2000 if y < 100 else 0; d = date(y, int(m.group(2)), int(m.group(1))); return d, 1, "on " + d.strftime("%a %d %b %Y")
        m = re.search(r"\b(?:on |date |number |the )(\d{1,2})(?:st|nd|rd|th)?\b", t)
        if m: d = today.replace(day=int(m.group(1))); return d, 1, "on " + d.strftime("%a %d %b")
    except ValueError: pass
    for i, w in enumerate(DAYS):
        if re.search(r"\b" + w + r"\b", t): d = today + timedelta(days=(i - today.weekday()) % 7); return d, 1, "on " + d.strftime("%A %d %b")
    return today, 1, "today"

# ---------- adding calendar events from plain words ----------
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
_DATE_TXT = re.compile(r"\b(?:on |for |by |this )?(?:the )?(?:\d{1,2}(?:st|nd|rd|th)?[\s/-]*(?:of\s+)?" + _MON + r"\.?(?:,?\s*\d{4})?|" + _MON + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?|\d{1,2}/\d{1,2}(?:/\d{2,4})?|day after tomorrow|tomorrow|today|tonight|next week|(?:on |this |next )?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|on (?:the )?\d{1,2}(?:st|nd|rd|th))\b", re.I)
_TIME = re.compile(r"\b(?:at |by |around )?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)|\bat (\d{1,2})(?::(\d{2}))?\b|\b(noon|midnight)\b", re.I)
_ADDV = re.compile(r"\b(add|put|create|schedule|set up|set|book|make|save|log|note down|remember)\b", re.I)
_NOUN = re.compile(r"\b(event|task|meeting|call|appointment|birthday|anniversary|exam|class|lecture|deadline|submission|interview|party|presentation|review|viva|test|trip|flight|reminder|assignment due|due)\b", re.I)
_QUESTION = re.compile(r"^\s*(what|what's|whats|show|list|check|any|do i|tell me|who|when|how)\b", re.I)
_REQ = re.compile(r"^\W*(?:can|could|would|will) you\b|^\W*please\b|^\W*kindly\b|^\W*i (?:want|would like|need) you\b|^\W*(?:add|set|create|put|make|remind)\b", re.I)
def polish(base):
    """Turn a chatty sentence into a short calendar title, e.g. "It is my girlfriend's birthday ... I have to wish her" -> "My girlfriend's birthday: wish her"."""
    t = re.split(r"\badded\b", base, 1, flags=re.I)[0]
    sents = [x.strip(" ,;:-") for x in re.split(r"(?<=[.?!])\s+|[.?!]\s*$", t) if x.strip(" ,;:-.?!")]
    facts = [x for x in sents if not _REQ.search(x)]
    m = re.search(r"\b(?:i (?:have|need|want|must|should) to|remind me to|reminder to|to remember to|remember to)\s+([^.?!]+)", t, re.I)
    action = re.sub(r"\s+", " ", m.group(1)).strip(" ,;:-") if m else ""
    subj = ""
    if facts:
        subj = re.sub(r"^(?:on\s*,?\s*)?(?:(?:it|this|today|there)\s*(?:is|'s|was)\s+)", "", facts[0], flags=re.I).strip(" ,;:-")
        if re.search(r"\bi (?:have|need|want|must|should) to\b", subj, re.I): subj = ""
    if subj and action and action.lower() not in subj.lower(): out = f"{subj}: {action}"
    else: out = subj or action
    out = out.strip(" ,;:-.?!").replace(".:", ":")
    return (out[:1].upper() + out[1:])[:90] if out else ""
def is_event_request(raw):
    t = raw.lower()
    if _QUESTION.search(t) or not _ADDV.search(t): return False
    has_cal = bool(re.search(r"\bcalendar\b", t))
    if not (has_cal or _NOUN.search(t)): return False
    return has_cal or bool(_DATE_TXT.search(t) or _TIME.search(t))
def parse_event(raw, now=None):
    """-> dict(title, start, end, all_day, repeat) or None when no date or time was given."""
    from datetime import datetime
    now = now or datetime.now(); t = raw.lower()
    tm = _TIME.search(t); dm = _DATE_TXT.search(t)
    if not tm and not dm: return None
    day = parse_day(t, now.date())[0] if dm else None
    start_t = None
    if tm:
        if tm.group(6): h, mi = (12, 0) if tm.group(6) == "noon" else (0, 0)
        else:
            h = int(tm.group(1) or tm.group(4)); mi = int(tm.group(2) or tm.group(5) or 0); ap = (tm.group(3) or "").replace(".", "")
            if ap == "pm" and h < 12: h += 12
            if ap == "am" and h == 12: h = 0
        start_t = (h % 24, mi)
    if day is None: day = now.date(); 
    if start_t:
        start = datetime(day.year, day.month, day.day, *start_t)
        if not dm and start <= now: start += timedelta(days=1)
    else: start = datetime(day.year, day.month, day.day)
    dur = 60; m = re.search(r"\bfor (\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)\b", t)
    if m: n = float(m.group(1)); dur = int(n * 60) if m.group(2).startswith("h") else int(n)
    title = raw
    title = re.sub(r"\bfor \d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?)\b", " ", title, flags=re.I)
    title = _DATE_TXT.sub(" ", title); title = _TIME.sub(" ", title)
    title = re.sub(r"\b(?:to|in|on|into)\s+(?:my\s+|the\s+)?(?:google\s+)?calendar\b|\bgoogle calendar\b|\bcalendar\b", " ", title, flags=re.I)
    title = _ADDV.sub(" ", title, count=1)
    title = re.sub(r"^\W*(?:an?|the|this|my|new)\b\s*", "", title.strip(), flags=re.I)
    title = re.sub(r"^(?:event|task|reminder|entry)\s*(?:called|named|for|to|about|:|-)?\s*", "", title.strip(), flags=re.I)
    title = re.sub(r"\s+", " ", re.sub(r"\b(?:on|at|by|for|to|in|of)\s*$", "", title.strip(" ,.-:;"), flags=re.I)).strip(" ,.-:;")
    title = re.sub(r"[,;]?\s*(?:and\s+|please\s+|can you\s+|also\s+)*(?:add|put|save|set)\s+(?:it|this|that)\b.*$", "", title, flags=re.I)
    title = re.sub(r"^(?:remind me to|reminder to|remind me|i have (?:an?\s+|the\s+)?)\s*", "", title.strip(), flags=re.I)
    title = re.sub(r"[,;]?\s+(?:and\s+)?(?:it|this|that)\s*$", "", title.strip(" ,;"), flags=re.I)
    title = re.sub(r"\bplease\b", " ", title, flags=re.I); title = re.sub(r"\s+", " ", title).strip(" ,.-:;")
    if len(title) > 45 or re.search(r"[.?!]|\b(?:can|could) you\b|\bplease\b|\bi have to\b", title, re.I):
        base = _TIME.sub(" ", _DATE_TXT.sub(" ", raw)); title = polish(base) or title[:60]
    title = (title[:1].upper() + title[1:]) if title else "Event"
    return {"title": title, "notes": raw.strip()[:500], "remind": bool(re.search(r"\bremind", t)), "start": start, "end": start + timedelta(minutes=dur), "all_day": start_t is None, "repeat": bool(re.search(r"birthday|anniversary", t))}
