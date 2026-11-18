"""Offline math for Axor (SymPy). Works with no internet.
solve_text(question) -> {"md": markdown+LaTeX answer, "say": plain speakable text} or None if it is not a math request."""
import re
try:
    import sympy as sp
    from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application, convert_xor
    OK = True
    _G = {}
    exec("from sympy import *", _G)      # SymPy names only; user text is whitelisted word-by-word below
    _G["__builtins__"] = {}
except Exception:
    OK = False

NAMES = {"sin": "sin", "cos": "cos", "tan": "tan", "cot": "cot", "sec": "sec", "csc": "csc", "asin": "asin", "acos": "acos", "atan": "atan",
         "sinh": "sinh", "cosh": "cosh", "tanh": "tanh", "exp": "exp", "log": "log", "ln": "log", "sqrt": "sqrt", "abs": "Abs", "pi": "pi", "oo": "oo", "inf": "oo", "e": "E"}
SAFE = re.compile(r"^[0-9a-zA-Z_+\-*/^().,=\s<>]*$")

def _parse(s):
    s = s.strip().replace("²", "**2").replace("³", "**3").replace("−", "-").replace("×", "*").replace("÷", "/").replace("π", "pi")
    if not SAFE.match(s) or "__" in s: raise ValueError("unsupported characters")
    loc = {}
    for w in set(re.findall(r"[A-Za-z_]+", s)):
        if w in NAMES: loc[w] = getattr(sp, NAMES[w])
        elif len(w) == 1: loc[w] = sp.Symbol(w)
        else:
            # allow implicit products such as "xy" or "sinx"; reject real words
            m = re.fullmatch(r"(sin|cos|tan|cot|sec|csc|exp|log|ln|sqrt)([a-z])", w)
            if m: s = re.sub(r"\b" + w + r"\b", f"{m.group(1)}({m.group(2)})", s)
            elif re.fullmatch(r"[a-z]{2,3}", w): s = re.sub(r"\b" + w + r"\b", "*".join(w), s); [loc.setdefault(c, sp.Symbol(c)) for c in w]
            else: raise ValueError("unknown word " + w)
    tr = standard_transformations + (implicit_multiplication_application, convert_xor)
    return parse_expr(s, local_dict=loc, global_dict=dict(_G), transformations=tr, evaluate=True)

def _var(expr, hint=None):
    if hint: return sp.Symbol(hint)
    fs = sorted(expr.free_symbols, key=lambda v: v.name)
    return sp.Symbol("x") if sp.Symbol("x") in fs or not fs else fs[0]

def _plain(e): return str(e).replace("**", " to the power ").replace("*", " times ").replace("sqrt", "square root of ").replace("I", "i")
L = sp.latex if OK else None

def solve_text(q):
    if not OK: return None
    t = q.strip().rstrip("?.!")
    t = re.sub(r"^(?:please\s+)?(?:can you\s+|could you\s+)?", "", t, flags=re.I)
    low = t.lower()
    try:
        m = re.match(r"(?:differentiate|derivative of|find the derivative of|diff|d/d(\w)\s*(?:of)?)\s*(.+?)(?:\s+with respect to\s+(\w))?$", t, re.I)
        if m:
            e = _parse(m.group(2)); v = _var(e, m.group(3) or m.group(1)); r = sp.simplify(sp.diff(e, v))
            return {"md": f"**Derivative**\n\n$$\\frac{{d}}{{d{v}}}\\left({L(e)}\\right) = {L(r)}$$", "say": f"The derivative is {_plain(r)}."}
        m = re.match(r"(?:integrate|integral of|find the integral of|antiderivative of)\s*(.+?)(?:\s+from\s+(.+?)\s+to\s+(.+?))?(?:\s+d([a-z]))?$", t, re.I)
        if m:
            e = _parse(m.group(1)); v = _var(e, m.group(4))
            if m.group(2):
                a, b = _parse(m.group(2)), _parse(m.group(3)); r = sp.simplify(sp.integrate(e, (v, a, b)))
                return {"md": f"**Definite integral**\n\n$$\\int_{{{L(a)}}}^{{{L(b)}}} {L(e)}\\,d{v} = {L(r)}$$" + (f"\n\nApproximately {sp.N(r, 8)}" if not r.is_Integer and r.is_number else ""), "say": f"The value is {_plain(r)}."}
            r = sp.integrate(e, v)
            return {"md": f"**Integral**\n\n$$\\int {L(e)}\\,d{v} = {L(r)} + C$$", "say": f"The integral is {_plain(r)} plus C."}
        m = re.match(r"limit of\s+(.+?)\s+as\s+([a-z])\s*(?:tends to|approaches|->|→|=)\s*(.+)$", t, re.I)
        if m:
            e = _parse(m.group(1)); v = sp.Symbol(m.group(2)); a = _parse(m.group(3)); r = sp.limit(e, v, a)
            return {"md": f"**Limit**\n\n$$\\lim_{{{v}\\to {L(a)}}} {L(e)} = {L(r)}$$", "say": f"The limit is {_plain(r)}."}
        m = re.match(r"(simplify|factor|factorise|factorize|expand)\s+(.+)$", t, re.I)
        if m:
            e = _parse(m.group(2)); f = {"simplify": sp.simplify, "factor": sp.factor, "factorise": sp.factor, "factorize": sp.factor, "expand": sp.expand}[m.group(1).lower()]; r = f(e)
            return {"md": f"**{m.group(1).capitalize()}**\n\n$${L(e)} = {L(r)}$$", "say": f"The result is {_plain(r)}."}
        m = re.match(r"(?:solve|find the roots of|roots of|find x in|find x for)\s+(.+?)(?:\s+for\s+([a-z]))?$", t, re.I)
        if m:
            body = m.group(1)
            if "=" in body:
                l, r_ = body.split("=", 1); eq = sp.Eq(_parse(l), _parse(r_)); fs = eq.free_symbols
            else:
                ex = _parse(body); eq = sp.Eq(ex, 0); fs = ex.free_symbols
            v = _var(eq.lhs - eq.rhs, m.group(2)); sols = sp.solve(eq, v)
            if not sols: return {"md": f"No solution found for ${L(eq)}$.", "say": "I found no solution."}
            lst = ", ".join(f"{v} = {L(s)}" for s in sols); num = ""
            real = [s for s in sols if s.is_number and s.is_real and not s.is_Rational]
            if real: num = "\n\nApproximately: " + ", ".join(f"${v} \\approx {sp.N(s, 6)}$" for s in real)
            return {"md": f"**Solve**\n\n$${L(eq)}$$\n\n$${lst}$${num}", "say": "The solutions are " + ", ".join(f"{v} equals {_plain(s)}" for s in sols) + "."}
    except Exception:
        return None
    return None
