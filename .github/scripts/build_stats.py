"""Builds the profile's live cards (stats, languages, activity, pills) as SVGs.

Runs in GitHub Actions. Needs: pip install fonttools brotli
Env: GH_TOKEN (token), GH_USER (username). Set SAMPLE=1 to render with fake data.
"""
import base64, datetime as dt, html, io, json, math, os, random, re, urllib.request
from fontTools import subset
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "assets", "generated")
USER = os.environ.get("GH_USER", "Minhazul-Islam18")
TOKEN = os.environ.get("GH_TOKEN", "")
SAMPLE = os.environ.get("SAMPLE") == "1"

BG, LINE, FG, MUTED = "#282A36", "#44475A", "#F8F8F2", "#A4ABCB"
ACCENTS = ["#BD93F9", "#FF79C6", "#8BE9FD", "#50FA7B", "#FFB86C", "#F1FA8C"]
E = html.escape

# ------------------------------------------------------------------ fonts
FONT_FILES = {k: os.path.join(HERE, "fonts", f"{k}.woff2") for k in ("Fraunces500", "Jakarta400", "Jakarta600")}
_loaded = {}

def _font(name):
    if name not in _loaded:
        _loaded[name] = TTFont(FONT_FILES[name])
    return _loaded[name]

def text_width(name, text, size, word_spacing=0.0):
    f = _font(name)
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    w = sum(hmtx[cmap.get(ord(c), cmap[32])][0] for c in text) * size / upm
    return w + text.count(" ") * word_spacing

def font_face(name, text):
    f = TTFont(FONT_FILES[name])
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga"]
    s = subset.Subsetter(opts)
    s.populate(text=text + " 0123456789,.%·")
    s.subset(f)
    buf = io.BytesIO()
    f.flavor = "woff2"
    f.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"@font-face {{ font-family: '{name}'; src: url(data:font/woff2;base64,{b64}) format('woff2'); }}"

def styles(fr="", j4="", j6="", extra=""):
    faces = []
    if fr: faces.append(font_face("Fraunces500", fr))
    if j4: faces.append(font_face("Jakarta400", j4))
    if j6: faces.append(font_face("Jakarta600", j6))
    return f"""<style>
    {chr(10).join(faces)}
    .fr {{ font-family: 'Fraunces500', Georgia, serif; }}
    .j4 {{ font-family: 'Jakarta400', 'Segoe UI', Helvetica, Arial, sans-serif; word-spacing: 1.5px; }}
    .j6 {{ font-family: 'Jakarta600', 'Segoe UI', Helvetica, Arial, sans-serif; word-spacing: 1.5px; }}
    {extra}
    @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
  </style>"""

TRAIL_CSS = """.trail { stroke-dasharray: 90 910; animation: travel 16s linear infinite; }
    @keyframes travel { from { stroke-dashoffset: 1000; } to { stroke-dashoffset: 0; } }"""

def card(w, h, color="#BD93F9"):
    return (f'<rect x=".75" y=".75" width="{w-1.5}" height="{h-1.5}" rx="24" fill="{BG}" stroke="{LINE}" stroke-width="1.5"/>\n'
            f'  <rect class="trail" x=".75" y=".75" width="{w-1.5}" height="{h-1.5}" rx="24" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linecap="round" pathLength="1000"/>')

# ------------------------------------------------------------------ data
QUERY = """query($login: String!) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100, orderBy: {field: STARGAZERS, direction: DESC}) {
      nodes { stargazerCount languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } } }
    }
    pullRequests { totalCount }
    contributionsCollection {
      totalCommitContributions
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
  }
}"""

def fetch_github():
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json", "User-Agent": "profile-cards"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise SystemExit(f"GitHub API error: {payload['errors']}")
    return payload["data"]["user"]

def fetch_views():
    """Reads the live profile-view count from komarev (the same counter as before)."""
    try:
        req = urllib.request.Request(f"https://komarev.com/ghpvc/?username={USER}", headers={"User-Agent": "profile-cards"})
        with urllib.request.urlopen(req, timeout=20) as r:
            svg = r.read().decode("utf-8", "ignore")
        nums = re.findall(r">\s*([\d,]+)\s*<", svg)
        return int(nums[-1].replace(",", "")) if nums else None
    except Exception:
        return None

def sample_data():
    random.seed(7)
    today = dt.date.today()
    days = [{"date": (today - dt.timedelta(days=i)).isoformat(),
             "contributionCount": max(0, int(random.gauss(4, 3.5)))} for i in range(364, -1, -1)]
    weeks = [{"contributionDays": days[i:i + 7]} for i in range(0, len(days), 7)]
    langs = [("PHP", 520000), ("JavaScript", 310000), ("Blade", 120000), ("Vue", 90000), ("CSS", 60000), ("TypeScript", 40000), ("HTML", 20000)]
    return {
        "repositories": {"nodes": [{"stargazerCount": 12, "languages": {"edges": [{"size": s, "node": {"name": n}} for n, s in langs]}}]},
        "pullRequests": {"totalCount": 86},
        "contributionsCollection": {"totalCommitContributions": 1043,
                                    "contributionCalendar": {"totalContributions": sum(d["contributionCount"] for d in days), "weeks": weeks}},
    }, 1284

# ------------------------------------------------------------------ helpers
def fmt(n):
    return f"{n:,}"

def streaks(days):
    counts = [d["contributionCount"] for d in days]
    longest = run = 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    i = len(counts) - 1
    if i >= 0 and counts[i] == 0:  # today not counted yet: start from yesterday
        i -= 1
    current = 0
    while i >= 0 and counts[i] > 0:
        current += 1
        i -= 1
    return current, longest

def plural(n, word):
    return f"{fmt(n)} {word}{'' if n == 1 else 's'}"

# ------------------------------------------------------------------ cards
def build_stats(user, days):
    stars = sum(r["stargazerCount"] for r in user["repositories"]["nodes"])
    cc = user["contributionsCollection"]
    cur, lon = streaks(days)
    metrics = [
        ("Total stars", fmt(stars), ACCENTS[5]),
        ("Commits, past year", fmt(cc["totalCommitContributions"]), ACCENTS[0]),
        ("Pull requests", fmt(user["pullRequests"]["totalCount"]), ACCENTS[2]),
        ("Contributions, past year", fmt(cc["contributionCalendar"]["totalContributions"]), ACCENTS[1]),
        ("Current streak", plural(cur, "day"), ACCENTS[3]),
        ("Longest streak, past year", plural(lon, "day"), ACCENTS[4]),
    ]
    W, H, colw = 880, 236, (880 - 88) / 3
    parts = []
    for i, (label, value, col) in enumerate(metrics):
        r, c = divmod(i, 3)
        x, y = 44 + c * colw + 22, 40 + r * 100
        parts.append(f'''<g class="m" style="animation-delay:{i * 90}ms">
    <circle cx="{x + 4}" cy="{y + 12}" r="4" fill="{col}"/>
    <text x="{x + 18}" y="{y + 17}" class="j4" font-size="14" fill="{MUTED}">{E(label)}</text>
    <text x="{x}" y="{y + 60}" class="fr" font-size="36" fill="{FG}">{E(value)}</text></g>''')
    for c in (1, 2):
        x = 44 + c * colw
        parts.append(f'<line x1="{x}" y1="44" x2="{x}" y2="{H - 44}" stroke="{LINE}" stroke-width="1"/>')
    extra = TRAIL_CSS + """
    .m { animation: fade .8s ease-out both; }
    @keyframes fade { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }"""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{E(". ".join(f"{l}: {v}" for l, v, _ in metrics))}">
  {styles(fr="".join(v for _, v, _ in metrics), j4="".join(l for l, _, _ in metrics), extra=extra)}
  {card(W, H, ACCENTS[0])}
  {chr(10).join(parts)}
</svg>'''

def build_langs(user):
    totals = {}
    for repo in user["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            totals[e["node"]["name"]] = totals.get(e["node"]["name"], 0) + e["size"]
    grand = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])
    top = ranked[:5]
    rest = sum(v for _, v in ranked[5:])
    if rest:
        top.append(("Other", rest))
    items = [(n, v / grand * 100, ACCENTS[i % len(ACCENTS)]) for i, (n, v) in enumerate(top)]
    W, H = 880, 230
    bx, bw, by = 44, 792, 96
    segs, x = [], bx
    for i, (n, pct, col) in enumerate(items):
        w = bw * pct / 100
        segs.append(f'<rect x="{x:.2f}" y="{by}" width="{max(w - 3, 1):.2f}" height="12" fill="{col}"/>')
        x += w
    legend = []
    colw = bw / 3
    for i, (n, pct, col) in enumerate(items):
        r, c = divmod(i, 3)
        lx, ly = bx + c * colw, 150 + r * 40
        legend.append(f'''<circle cx="{lx + 5}" cy="{ly - 5}" r="5" fill="{col}"/>
    <text x="{lx + 20}" y="{ly}" class="j6" font-size="15" fill="{FG}">{E(n)}</text>
    <text x="{lx + 20 + text_width("Jakarta600", n, 15, 1.5) + 10:.1f}" y="{ly}" class="j4" font-size="14" fill="{MUTED}">{pct:.1f}%</text>''')
    title, cap = "Most used languages", "Share of code across my repositories"
    extra = TRAIL_CSS + """
    .bar { transform-origin: 44px 0; animation: grow 1.6s cubic-bezier(.2,.7,.2,1) both; }
    @keyframes grow { from { transform: scaleX(0); } to { transform: scaleX(1); } }"""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{E(title)}: {E(", ".join(f"{n} {p:.1f}%" for n, p, _ in items))}">
  {styles(j4=cap + "%", j6=title + "".join(n for n, _, _ in items), extra=extra)}
  <defs><clipPath id="bar"><rect x="{bx}" y="{by}" width="{bw}" height="12" rx="6"/></clipPath></defs>
  {card(W, H, ACCENTS[1])}
  <text x="44" y="56" class="j6" font-size="18" fill="{FG}">{E(title)}</text>
  <text x="44" y="78" class="j4" font-size="14" fill="{MUTED}">{E(cap)}</text>
  <rect x="{bx}" y="{by}" width="{bw}" height="12" rx="6" fill="{LINE}"/>
  <g clip-path="url(#bar)"><g class="bar">{"".join(segs)}</g></g>
  {chr(10).join(legend)}
</svg>'''

def smooth_path(pts, floor):
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        c1, c2 = (c1[0], min(c1[1], floor)), (c2[0], min(c2[1], floor))  # never dip below zero
        d += f" C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    return d

def build_activity(days):
    last = days[-30:]
    counts = [d["contributionCount"] for d in last]
    total, peak = sum(counts), max(counts) if counts else 0
    top = max(peak, 4)
    W, H = 880, 300
    x0, x1, y0, y1 = 64, 836, 250, 110
    pts = [(x0 + i * (x1 - x0) / (len(counts) - 1), y0 - c / top * (y0 - y1)) for i, c in enumerate(counts)]
    line = smooth_path(pts, y0)
    area = line + f" L{x1} {y0} L{x0} {y0} Z"
    grid, ticks = [], []
    for k in range(4):
        gy = y0 - k * (y0 - y1) / 3
        grid.append(f'<line x1="{x0}" y1="{gy:.1f}" x2="{x1}" y2="{gy:.1f}" stroke="{LINE}" stroke-width="1" stroke-dasharray="{"0" if k == 0 else "3 5"}"/>')
        ticks.append(f'<text x="{x0 - 14}" y="{gy + 4:.1f}" text-anchor="end" class="j4" font-size="12" fill="{MUTED}">{round(top * k / 3)}</text>')
    def label(d):
        return dt.date.fromisoformat(d).strftime("%b %d").replace(" 0", " ")
    xl = [(x0, label(last[0]["date"]), "start"), ((x0 + x1) / 2, label(last[len(last) // 2]["date"]), "middle"), (x1, label(last[-1]["date"]), "end")]
    xlab = "".join(f'<text x="{x:.1f}" y="{y0 + 26}" text-anchor="{a}" class="j4" font-size="12" fill="{MUTED}">{E(t)}</text>' for x, t, a in xl)
    pi = counts.index(peak) if counts else 0
    px, py = pts[pi]
    title = "Contribution activity"
    cap = f"Last 30 days · {plural(total, 'contribution')}"
    extra = TRAIL_CSS + """
    .draw { stroke-dasharray: 1000; animation: draw 2.4s cubic-bezier(.3,.6,.2,1) both; }
    .area { animation: fadein 1.6s .6s ease-out both; }
    .peak { animation: fadein .6s 2.2s ease-out both; }
    @keyframes draw { from { stroke-dashoffset: 1000; } to { stroke-dashoffset: 0; } }
    @keyframes fadein { from { opacity: 0; } to { opacity: 1; } }"""
    alltext = title + cap + "".join(t for _, t, _ in xl) + "Peak " + "".join(str(round(top * k / 3)) for k in range(4))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{E(title)}. {E(cap)}. Peak day: {peak}.">
  {styles(j4=alltext, j6=title, extra=extra)}
  <defs>
    <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#BD93F9" stop-opacity=".35"/><stop offset="1" stop-color="#BD93F9" stop-opacity="0"/></linearGradient>
    <linearGradient id="stroke" x1="0" x2="1"><stop offset="0" stop-color="#BD93F9"/><stop offset="1" stop-color="#FF79C6"/></linearGradient>
  </defs>
  {card(W, H, ACCENTS[2])}
  <text x="44" y="56" class="j6" font-size="18" fill="{FG}">{E(title)}</text>
  <text x="44" y="78" class="j4" font-size="14" fill="{MUTED}">{E(cap)}</text>
  {"".join(grid)}{"".join(ticks)}
  <path class="area" d="{area}" fill="url(#fill)"/>
  <path class="draw" d="{line}" fill="none" stroke="url(#stroke)" stroke-width="2.5" stroke-linecap="round" pathLength="1000"/>
  <g class="peak"><circle cx="{px:.1f}" cy="{py:.1f}" r="9" fill="#FF79C6" fill-opacity=".2"/><circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="#FF79C6" stroke="{BG}" stroke-width="2"/>
  <text x="{min(max(px, 90), 790):.1f}" y="{py - 16:.1f}" text-anchor="middle" class="j4" font-size="12" fill="{FG}">Peak {peak}</text></g>
  {xlab}
</svg>'''

def build_pills(views):
    pills = [("Coding since", "2019", "#FF79C6"), ("Focus", "PHP ecosystem", "#8BE9FD")]
    if views is not None:
        pills.append(("Profile views", fmt(views), "#BD93F9"))
    S, x, parts = 14, 0.0, []
    for lab, val, col in pills:
        wl = text_width("Jakarta400", lab, S, 1.5)
        wv = text_width("Jakarta600", val, S, 1.5)
        w = 24 + wl + 8 + wv + 16
        parts.append(f'''<g transform="translate({x:.1f} 0)">
    <rect x=".5" y=".5" width="{w - 1:.1f}" height="33" rx="16.5" fill="{BG}" stroke="{LINE}"/>
    <circle cx="14" cy="17" r="3" fill="{col}"/>
    <text x="24" y="22" class="j4" font-size="{S}" fill="{MUTED}">{E(lab)}</text>
    <text x="{24 + wl + 8:.1f}" y="22" class="j6" font-size="{S}" fill="{col}">{E(val)}</text></g>''')
        x += w + 10
    total = x - 10
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total:.0f}" height="34" viewBox="0 0 {total:.0f} 34" role="img" aria-label="{E(". ".join(f"{l}: {v}" for l, v, _ in pills))}">
  {styles(j4="".join(p[0] for p in pills), j6="".join(p[1] for p in pills))}
  {chr(10).join(parts)}
</svg>'''

# ------------------------------------------------------------------ main
def main():
    if SAMPLE:
        user, views = sample_data()
    else:
        if not TOKEN:
            raise SystemExit("GH_TOKEN is not set")
        user, views = fetch_github(), fetch_views()
    days = [d for w in user["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    days.sort(key=lambda d: d["date"])
    os.makedirs(OUT, exist_ok=True)
    cards = {"stats.svg": build_stats(user, days), "langs.svg": build_langs(user),
             "activity.svg": build_activity(days), "pills.svg": build_pills(views)}
    for name, svg in cards.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write(svg)
    print("Wrote", ", ".join(cards))

if __name__ == "__main__":
    main()
