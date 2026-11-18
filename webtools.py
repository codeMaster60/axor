"""Axor web tools (all free, no API keys): Wikipedia / Wikimedia Commons lookups, web search, image requests.
Everything here needs the internet and fails soft: callers catch exceptions and show a friendly message.
Tests replace `http_get` so no network is needed."""
import re, json, html, random, threading, urllib.request, urllib.parse

UA = "Axor/1.0 (student capstone voice assistant; local app) python-urllib"


def http_get(url, timeout=6, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def jget(url, timeout=6): return json.loads(http_get(url, timeout))
def qs(**kw): return urllib.parse.urlencode(kw)
def domain(u): return re.sub(r"^www\.", "", urllib.parse.urlparse(u).netloc)
def strip_tags(s): return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


# ------------------------------------------------------------------ Wikipedia / Commons
WIKI = "https://en.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"


def wiki_search(q, n=3):
    d = jget(WIKI + "?" + qs(action="query", format="json", generator="search", gsrsearch=q, gsrlimit=n, prop="extracts|pageimages|info",
                             exintro=1, explaintext=1, exsentences=4, exlimit=n, piprop="thumbnail", pithumbsize=900, inprop="url", redirects=1))
    pages = sorted((d.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    return [{"title": p["title"], "url": p.get("fullurl") or "https://en.wikipedia.org/wiki/" + urllib.parse.quote(p["title"].replace(" ", "_")),
             "snippet": (p.get("extract") or "").strip(), "image": (p.get("thumbnail") or {}).get("source"), "source": "Wikipedia"} for p in pages]


def commons_images(q, n=6):
    d = jget(COMMONS + "?" + qs(action="query", format="json", generator="search", gsrsearch=q + " filetype:bitmap", gsrnamespace=6, gsrlimit=n * 2,
                                prop="imageinfo", iiprop="url|extmetadata|size|mime", iiurlwidth=900))
    pages = sorted((d.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]; meta = ii.get("extmetadata") or {}
        if ii.get("mime") not in ("image/jpeg", "image/png", "image/webp"): continue
        if min(ii.get("width", 0), ii.get("height", 0)) < 300: continue
        credit = strip_tags((meta.get("Artist") or {}).get("value")); lic = (meta.get("LicenseShortName") or {}).get("value", "")
        out.append({"title": re.sub(r"\.\w+$", "", re.sub(r"^File:", "", p["title"])).replace("_", " "), "image": ii.get("thumburl") or ii.get("url"),
                    "page": ii.get("descriptionurl"), "credit": ", ".join(x for x in (credit[:60], lic) if x) or "Wikimedia Commons"})
    return out[:n]


def ddg_search(q, n=4):
    t = http_get("https://html.duckduckgo.com/html/?" + qs(q=q), timeout=6)
    out = []
    for block in re.split(r'<div class="[^"]*result results_links', t)[1:]:
        if "result--ad" in block[:200]: continue
        a = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not a: continue
        href = html.unescape(a.group(1)); m = re.search(r"uddg=([^&]+)", href)
        url = urllib.parse.unquote(m.group(1)) if m else href
        if url.startswith("//"): url = "https:" + url
        if not url.startswith("http"): continue
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        out.append({"title": strip_tags(a.group(2)), "url": url, "snippet": strip_tags(sn.group(1)) if sn else "", "source": domain(url)})
        if len(out) >= n: break
    return out


def build_sources(q, want=6):
    """Wikipedia + web results in parallel. Returns a list of {title,url,snippet,source}; never raises."""
    res = {"w": [], "d": []}
    def run(k, f):
        try: res[k] = f()
        except Exception: res[k] = []
    news = bool(re.search(r"\b(news|latest|today|breaking|recent|this week|2026)\b", q, re.I)); res["n"] = []
    ts = [threading.Thread(target=run, args=("w", lambda: wiki_search(q, 3))), threading.Thread(target=run, args=("d", lambda: ddg_search(q, 5)))]
    if news: ts.append(threading.Thread(target=run, args=("n", lambda: ddg_search(q + " news", 4))))
    [t.start() for t in ts]; [t.join(5) for t in ts]
    seen, out = set(), []
    for s in res["w"][:2] + res["d"] + res["n"] + res["w"][2:]:
        u = s["url"].split("#")[0]
        if u in seen or not s.get("snippet"): continue
        seen.add(u); out.append(s)
    return out[:want]


EXPLICIT = re.compile(r"\b(sources?|cite|citations?|references?|according to|with links?|where (?:did|does) (?:this|that) come from)\b", re.I)
LOOKUP = re.compile(r"^(who (?:is|was|are|were|won|invented|founded)|when (?:is|was|did|does|will)|where (?:is|was|are)|what (?:is|was|are) the (?:capital|population|price|score|latest|height|age|net worth|release date|weather)|what happened|which (?:country|city|company|team|player)|how (?:many|much|old|tall|far) (?:is|are|was|were|did|does)|latest|news|what'?s the latest|tell me about|history of|define|definition of|who'?s)\b|"
                    r"\b(details|information|info|profile|bio|background|biography|achievements) (about|on|of|for)\b|\b(latest news|breaking|current price|stock price|live score|score of|election results?|net worth|release date|population of|capital of|founder of|ceo of|prime minister|president of)\b", re.I)
NOT_FACT = re.compile(r"\b(write|compose|draft|translate|rewrite|summari[sz]e|python|java|javascript|code|function|poem|story|joke|essay|email|letter|my |your |you |remind|open|play|solve|calculate)\b", re.I)
SMALLTALK = re.compile(r"^(hi|hello|hey|thanks|thank you|ok|okay|yes|no|good|bye|how are you|how'?s (?:life|it going|everything)|what'?s up|who are you|what can you do|what do you do|all good|are you there)\b", re.I)


STOP = {"the", "a", "an", "is", "are", "was", "were", "am", "be", "do", "does", "did", "can", "could", "will", "would", "should", "i", "me", "we", "us", "it", "this", "that", "to", "for", "of", "in", "on", "at", "with", "and", "or", "but", "not", "no", "yes", "please", "thanks", "thank", "ok", "okay", "hi", "hello", "hey", "bye", "good", "morning", "evening", "night", "open", "close", "play", "set", "turn", "start", "stop", "tell", "show", "give", "make", "take", "send", "call", "text", "what", "why", "how", "when", "where", "who", "which", "my", "your", "more", "again", "next", "previous", "back", "continue", "go", "help", "explain", "solve", "run", "new", "like", "love", "want", "need", "yeah", "yep", "nope", "sure", "cool", "nice", "great", "fine", "right", "wrong", "maybe", "just", "so", "too", "very", "now", "then", "here", "there", "also"}


def wants_sources(q):
    """Sources only when the person asks for them, or the question is a factual or current-events lookup. Chit-chat, advice, maths, code and writing never get them."""
    ql = q.lower().strip().rstrip("?!. ")
    if EXPLICIT.search(ql): return True
    if SMALLTALK.match(ql) or NOT_FACT.search(ql) or len(ql.split()) < 2: return False
    if LOOKUP.search(ql): return True
    # a bare name or topic such as "malaika arora" or "taj mahal" is a lookup
    w = ql.split()
    return 2 <= len(w) <= 4 and all(re.fullmatch(r"[a-z][a-z'.\-]*", x) for x in w) and not any(x in STOP for x in w)


def sources_block(sources):
    return "\n".join(f"[{i}] {s['title']} ({domain(s['url'])}): {s['snippet'][:420]}" for i, s in enumerate(sources, 1))


def finish_with_sources(answer, sources):
    """Turn [n] into links and add a Sources list. Only sources the answer actually cites are listed (else the top 3 as 'related')."""
    cited = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", answer) if 1 <= int(n) <= len(sources)})
    body = re.sub(r"\[(\d{1,2})\](?!\()", lambda m: f"[{m.group(1)}]({mdu(sources[int(m.group(1)) - 1]['url'])})" if 1 <= int(m.group(1)) <= len(sources) else m.group(0), answer)
    use = cited or list(range(1, min(3, len(sources)) + 1)); head = "**Sources**" if cited else "**Sources searched**"
    lines = [f"{i}. [{_md_safe(sources[i - 1]['title'])}]({mdu(sources[i - 1]['url'])}) · {domain(sources[i - 1]['url'])}" for i in use]
    return body + "\n\n" + head + "\n" + "\n".join(lines)


# ------------------------------------------------------------------ image requests
_NOUN = r"(?:images?|pictures?|photos?|pics?|photographs?)"
_GEN_NOUN = r"(?:images?|pictures?|photos?|illustrations?|drawings?|paintings?|posters?|logos?|wallpapers?|sketch(?:es)?|art(?:work)?|cartoons?|portraits?)"
GEN_RE = re.compile(r"^(?:please\s+)?(?:can|could|would)?\s*(?:(?:you|u)\s+)?(?:please\s+)?(?:generate|create|draw|make|design|paint|imagine|render|produce)\s+(?:me\s+)?(?:an?\s+|the\s+|some\s+)?" + _GEN_NOUN + r"\s*(?:of|for|showing|with|about)?\s*(.+)$", re.I)
PHOTO_RES = [
    re.compile(r"^(?:please\s+)?(?:can|could|would)?\s*(?:(?:you|u)\s+)?(?:please\s+)?(?:give|show|find|get|fetch|send|bring|display|pull up|search)\s+(?:me\s+)?(?:an?\s+|the\s+|some\s+|few\s+|a few\s+|more\s+)?" + _NOUN + r"\s*(?:of|for)\s+(.+)$", re.I),
    re.compile(r"^(?:i\s+(?:want|need|would like)\s+(?:to see\s+)?)(?:an?\s+|the\s+|some\s+)?" + _NOUN + r"\s*(?:of|for)\s+(.+)$", re.I),
    re.compile(r"^(?:an?\s+|the\s+)?" + _NOUN + r"\s+of\s+(.+)$", re.I),
    re.compile(r"^what\s+does\s+(.+?)\s+look\s+like$", re.I),
    re.compile(r"^show\s+me\s+(?:what\s+)?(.+?)\s+(?:looks?\s+like)$", re.I),
]
_FILLER = re.compile(r"\s*(?:please|for me|thanks|thank you)\s*$", re.I)


_N2 = r"(?:images?|pictures?|photos?|pics?|photographs?)"
PRON_RE = re.compile(r"^(?:please\s+)?(?:(?:can|could|would|will)\s+)?(?:(?:you|u)\s+)?(?:please\s+)?(?:(?:show|give|send|find|get|share|display|bring)\s+(?:me\s+)?)?(?:(?:her|his|their|its|that|this|the|some|a few|more|another|same)\s+)*" + _N2 + r"(?:\s+(?:of\s+)?(?:her|him|them|it|that|this))?$", re.I)
NAME_RE = re.compile(r"^(?:please\s+)?(?:(?:can|could|would|will)\s+)?(?:(?:you|u)\s+)?(?:(?:show|give|send|find|get|share|display)\s+(?:me\s+)?)?(?:(?:some|a few|more|latest|recent|best|new|old)\s+)?([\w'.\-]+(?:\s+[\w'.\-]+){0,4}?)\s+" + _N2 + r"$", re.I)
_BADSUBJ = {"my", "your", "our", "the", "these", "those", "some", "any", "all", "her", "his", "their", "its", "more", "another", "same", "that", "this", "a", "an", "profile", "screen", "phone"}


def topic_from(text):
    t = re.sub(r"[?!.]+$", "", (text or "").strip())
    t = re.sub(r"^(?:who (?:is|was|are)|what (?:is|was)|tell me about|about|info(?:rmation)? (?:on|about)|details (?:about|on|of))\s+", "", t, flags=re.I)
    return t.strip()


def image_intent(raw, ctx=None):
    """Returns (mode, subject, count) or None. mode is 'photo' (real photos) or 'generate' (new artwork)."""
    t = re.sub(r"\s+", " ", raw.strip().rstrip("?.!")).strip()
    t = re.sub(r"^(?:hey |hi |ok |okay )?axor[, ]*", "", t, flags=re.I)
    m = GEN_RE.match(t)
    if m: return "generate", _FILLER.sub("", m.group(1)).strip(), 1
    for rx in PHOTO_RES:
        m = rx.match(t)
        if m:
            plural = bool(re.search(r"\b(images|pictures|photos|pics|photographs)\b", t[:60], re.I))
            return "photo", _FILLER.sub("", m.group(1)).strip(), 6 if plural else 3
    if PRON_RE.match(t):
        subj = ctx() if callable(ctx) else ctx
        if subj: return "photo", subj, 6 if re.search(r"(images|pictures|photos|pics)\b", t, re.I) else 3
        return None
    m = NAME_RE.match(t)
    if m:
        subj = _FILLER.sub("", m.group(1)).strip()
        if subj and subj.split()[0].lower() not in _BADSUBJ and subj.lower() not in _BADSUBJ: return "photo", subj, 6 if re.search(r"(images|pictures|photos|pics)\b", t, re.I) else 3
    return None


PERSON = re.compile(r"\b(born\b|is an? (?:[\w\-]+ ){0,4}(?:singer|actor|actress|politician|composer|musician|footballer|cricketer|player|businessman|businesswoman|entrepreneur|"
                    r"writer|author|poet|director|filmmaker|scientist|president|prime minister|rapper|comedian|athlete|artist|dancer|model|activist|journalist|physicist|"
                    r"mathematician|engineer|chef|boxer|wrestler|golfer|swimmer|sprinter|chess player|youtuber|influencer|billionaire))", re.I)


def is_real_person(subject):
    try: hits = wiki_search(subject, 1)
    except Exception: return False
    if not hits: return False
    h = hits[0]; words = [w for w in re.findall(r"\w+", subject.lower()) if len(w) > 2]
    return bool(words) and all(w in h["title"].lower() for w in words[:3]) and bool(PERSON.search(h["snippet"][:400]))


def mdu(u): return (u or "").replace("(", "%28").replace(")", "%29").replace(" ", "%20")
def _md_safe(s): return re.sub(r'["\]\[()|]', "", s or "").strip()


def gen_url(prompt, seed=None):
    return "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt) + "?" + qs(width=1024, height=768, model="flux", enhance="true", nologo="true", seed=seed or random.randint(1, 999999))


def photo_answer(subject, n):
    imgs, seen = [], set()
    hits = []
    try: hits = wiki_search(subject, 2)
    except Exception: pass
    if hits and hits[0].get("image"): imgs.append({"title": hits[0]["title"], "image": hits[0]["image"], "page": hits[0]["url"], "credit": "Wikipedia"})
    try:
        for c in commons_images(subject, n):
            imgs.append(c)
    except Exception: pass
    out = []
    for i in imgs:
        key = re.sub(r"\W+", "", i["image"].split("/")[-1].lower())[-40:]
        if key in seen: continue
        seen.add(key); out.append(i)
    out = out[:n]
    search = "https://www.google.com/search?tbm=isch&q=" + urllib.parse.quote(subject)
    if not out: return f"I couldn't find freely licensed pictures of **{subject}**. You can try [an image search]({search})."
    name = hits[0]["title"] if hits and len(subject.split()) <= 4 else subject
    lines = [f"Photos of **{_md_safe(name)}**, from Wikipedia and Wikimedia Commons."] + [""]
    lines += [f'![{_md_safe(i["title"])}]({mdu(i["image"])} "{_md_safe(i["credit"])}|{mdu(i.get("page") or "")}")' for i in out]
    lines += ["", f"Click a picture to enlarge or save it. Credits link to the source. [More images]({search})"]
    return "\n".join(lines)


def generate_answer(subject):
    if is_real_person(subject):
        return "I don't generate pictures of real people, so here are real photos instead.\n\n" + photo_answer(subject, 3)
    u = gen_url(subject)
    return f'Here is a generated image of **{_md_safe(subject)}**.\n\n![{_md_safe(subject)}]({u} "AI-generated with Pollinations|gen:{_md_safe(subject)}")\n\nIt is made by an AI, so details can look odd. Use Regenerate for another take.'


def image_flow(mode, subject, n):
    if not subject: return "Tell me what to look for, for example: show me photos of the Taj Mahal."
    try: return generate_answer(subject) if mode == "generate" else photo_answer(subject, n)
    except Exception as e: return f"I couldn't fetch images right now ({type(e).__name__}). Check your connection and try again."


# ------------------------------------------------------------------ chat titles
_LEAD = re.compile(r"^(?:hey |hi |ok |okay |please |can you |could you |would you |can u |will you |tell me |i want to |i need to |i want |i need |let'?s |show me |give me )+", re.I)


def smart_title(text, limit=38):
    t = re.sub(r"\s+", " ", (text or "").strip()); t = _LEAD.sub("", t).strip(" ?!.,")
    t = re.sub(r"^(what|who|how|why|when|where) (is|are|was|were|do|does|did) ", lambda m: m.group(1).capitalize() + " " + m.group(2) + " ", t, flags=re.I)
    if not t: return "New chat"
    t = t[0].upper() + t[1:]
    if len(t) > limit: t = t[:limit].rsplit(" ", 1)[0].rstrip(",;:-") + "..."
    return t


def clean_ai_title(s):
    s = (s or "").strip().splitlines()[0] if (s or "").strip() else ""
    s = re.sub(r'^(title|chat title)\s*:\s*', "", s, flags=re.I).strip(" \"'`*#.")
    return s[:48] if 2 <= len(s) <= 60 else ""
