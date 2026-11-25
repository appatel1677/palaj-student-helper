import os
import re
import io
import json
import math
import urllib.request
import urllib.parse
from db_and_pdf import get_pdf_font

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib import font_manager
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

_GEO_MEM_CACHE = {}

GUJ_DIST_KEYWORDS = {
    "મહેસાણા": ("મહેસાણા", "Mehsana, Gujarat, India"),
    "mahesana": ("મહેસાણા", "Mehsana, Gujarat, India"),
    "mehsana": ("મહેસાણા", "Mehsana, Gujarat, India"),
    "બનાસકાંઠા": ("બનાસકાંઠા", "Banaskantha, Gujarat, India"),
    "banaskantha": ("બનાસકાંઠા", "Banaskantha, Gujarat, India"),
    "પાટણ": ("પાટણ", "Patan, Gujarat, India"),
    "patan": ("પાટણ", "Patan, Gujarat, India"),
    "કચ્છ": ("કચ્છ", "Kutch, Gujarat, India"),
    "kutch": ("કચ્છ", "Kutch, Gujarat, India"),
    "સાબરકાંઠા": ("સાબરકાંઠા", "Sabarkantha, Gujarat, India"),
    "sabarkantha": ("સાબરકાંઠા", "Sabarkantha, Gujarat, India"),
    "અરવલ્લી": ("અરવલ્લી", "Aravalli, Gujarat, India"),
    "aravalli": ("અરવલ્લી", "Aravalli, Gujarat, India"),
    "ગાંધીનગર": ("ગાંધીનગર", "Gandhinagar, Gujarat, India"),
    "gandhinagar": ("ગાંધીનગર", "Gandhinagar, Gujarat, India"),
    "અમદાવાદ": ("અમદાવાદ", "Ahmedabad, Gujarat, India"),
    "ahmedabad": ("અમદાવાદ", "Ahmedabad, Gujarat, India"),
    "ખેડા": ("ખેડા", "Kheda, Gujarat, India"),
    "kheda": ("ખેડા", "Kheda, Gujarat, India"),
    "આણંદ": ("આણંદ", "Anand, Gujarat, India"),
    "anand": ("આણંદ", "Anand, Gujarat, India"),
    "વડોદરા": ("વડોદરા", "Vadodara, Gujarat, India"),
    "vadodara": ("વડોદરા", "Vadodara, Gujarat, India"),
    "સુરત": ("સુરત", "Surat, Gujarat, India"),
    "surat": ("સુરત", "Surat, Gujarat, India"),
    "ભરૂચ": ("ભરૂચ", "Bharuch, Gujarat, India"),
    "bharuch": ("ભરૂચ", "Bharuch, Gujarat, India"),
    "નર્મદા": ("નર્મદા", "Narmada, Gujarat, India"),
    "narmada": ("નર્મદા", "Narmada, Gujarat, India"),
    "વલસાડ": ("વલસાડ", "Valsad, Gujarat, India"),
    "valsad": ("વલસાડ", "Valsad, Gujarat, India"),
    "નવસારી": ("નવસારી", "Navsari, Gujarat, India"),
    "navsari": ("નવસારી", "Navsari, Gujarat, India"),
    "ડાંગ": ("ડાંગ", "Dang, Gujarat, India"),
    "dang": ("ડાંગ", "Dang, Gujarat, India"),
    "રાજકોટ": ("રાજકોટ", "Rajkot, Gujarat, India"),
    "rajkot": ("રાજકોટ", "Rajkot, Gujarat, India"),
    "જામનગર": ("જામનગર", "Jamnagar, Gujarat, India"),
    "jamnagar": ("જામનગર", "Jamnagar, Gujarat, India"),
    "જૂનાગઢ": ("જૂનાગઢ", "Junagadh, Gujarat, India"),
    "junagadh": ("જૂનાગઢ", "Junagadh, Gujarat, India"),
    "ભાવનગર": ("ભાવનગર", "Bhavnagar, Gujarat, India"),
    "bhavnagar": ("ભાવનગર", "Bhavnagar, Gujarat, India"),
    "અમરેલી": ("અમરેલી", "Amreli, Gujarat, India"),
    "amreli": ("અમરેલી", "Amreli, Gujarat, India"),
    "મોરબી": ("મોરબી", "Morbi, Gujarat, India"),
    "morbi": ("મોરબી", "Morbi, Gujarat, India"),
    "સુરેન્દ્રનગર": ("સુરેન્દ્રનગર", "Surendranagar, Gujarat, India"),
    "surendranagar": ("સુરેન્દ્રનગર", "Surendranagar, Gujarat, India"),
    "પોરબંદર": ("પોરબંદર", "Porbandar, Gujarat, India"),
    "porbandar": ("પોરબંદર", "Porbandar, Gujarat, India"),
    "ગીર સોમનાથ": ("ગીર સોમનાથ", "Gir Somnath, Gujarat, India"),
    "gir somnath": ("ગીર સોમનાથ", "Gir Somnath, Gujarat, India"),
    "દેવભૂમિ દ્વારકા": ("દેવભૂમિ દ્વારકા", "Devbhoomi Dwarka, Gujarat, India"),
    "dwarka": ("દેવભૂમિ દ્વારકા", "Devbhoomi Dwarka, Gujarat, India"),
    "બોટાદ": ("બોટાદ", "Botad, Gujarat, India"),
    "botad": ("બોટાદ", "Botad, Gujarat, India"),
    "મહીસાગર": ("મહીસાગર", "Mahisagar, Gujarat, India"),
    "mahisagar": ("મહીસાગર", "Mahisagar, Gujarat, India"),
    "પંચમહાલ": ("પંચમહાલ", "Panchmahal, Gujarat, India"),
    "panchmahal": ("પંચમહાલ", "Panchmahal, Gujarat, India"),
    "દાહોદ": ("દાહોદ", "Dahod, Gujarat, India"),
    "dahod": ("દાહોદ", "Dahod, Gujarat, India"),
    "છોટા ઉદેપુર": ("છોટા ઉદેપુર", "Chhota Udaipur, Gujarat, India"),
    "chhota udaipur": ("છોટા ઉદેપુર", "Chhota Udaipur, Gujarat, India"),
    "તાપી": ("તાપી", "Tapi, Gujarat, India"),
    "tapi": ("તાપી", "Tapi, Gujarat, India"),
}

DISTRICT_BUILTIN_PINS = {
    "મહેસાણા": [
        {"name": "મહેસાણા", "lon": 72.3693, "lat": 23.5880, "type": "taluka"},
        {"name": "વિસનગર", "lon": 72.5522, "lat": 23.6987, "type": "taluka"},
        {"name": "ઊંઝા", "lon": 72.3912, "lat": 23.8037, "type": "taluka"},
        {"name": "કડી", "lon": 72.3336, "lat": 23.2991, "type": "taluka"},
        {"name": "ખેરાલુ", "lon": 72.6133, "lat": 23.8861, "type": "taluka"},
        {"name": "વડનગર", "lon": 72.6331, "lat": 23.7852, "type": "taluka"},
        {"name": "વિજાપુર", "lon": 72.7525, "lat": 23.5612, "type": "taluka"},
        {"name": "બેચરાજી", "lon": 72.0461, "lat": 23.5015, "type": "taluka"},
        {"name": "સતલાસણા", "lon": 72.7358, "lat": 24.0061, "type": "taluka"},
        {"name": "જોટાણા", "lon": 72.3168, "lat": 23.4756, "type": "taluka"},
        {"name": "પલાજ", "lon": 72.4265, "lat": 23.5535, "type": "village"},
        {"name": "મોઢેરા", "lon": 72.1332, "lat": 23.5835, "type": "village"},
        {"name": "તારંગા", "lon": 72.7562, "lat": 23.9631, "type": "village"},
        {"name": "લાંઘણજ", "lon": 72.4950, "lat": 23.4520, "type": "village"},
        {"name": "ગોઝારિયા", "lon": 72.6010, "lat": 23.4890, "type": "village"},
        {"name": "આંબલિયાસણ", "lon": 72.4410, "lat": 23.4830, "type": "village"},
        {"name": "ઉનાવા", "lon": 72.3735, "lat": 23.7580, "type": "village"},
        {"name": "ભાંડુ", "lon": 72.3780, "lat": 23.6940, "type": "village"},
        {"name": "નંદાસણ", "lon": 72.4110, "lat": 23.3820, "type": "village"},
        {"name": "સુંઢિયા", "lon": 72.5780, "lat": 23.8210, "type": "village"},
        {"name": "કુકસ", "lon": 72.4150, "lat": 23.6350, "type": "village"},
        {"name": "લડાલ", "lon": 72.6850, "lat": 23.6320, "type": "village"},
    ],
    "પાટણ": [
        {"name": "પાટણ", "lon": 72.1266, "lat": 23.8493, "type": "taluka"},
        {"name": "સિદ્ધપુર", "lon": 72.3736, "lat": 23.9182, "type": "taluka"},
        {"name": "ચાણસ્મા", "lon": 72.1211, "lat": 23.7192, "type": "taluka"},
        {"name": "હારિજ", "lon": 71.8981, "lat": 23.6942, "type": "taluka"},
        {"name": "સમી", "lon": 71.7891, "lat": 23.6881, "type": "taluka"},
        {"name": "રાધનપુર", "lon": 71.6067, "lat": 23.8315, "type": "taluka"},
        {"name": "સાંતલપુર", "lon": 71.1892, "lat": 23.7765, "type": "taluka"},
        {"name": "સરસ્વતી", "lon": 72.0750, "lat": 23.8850, "type": "taluka"},
        {"name": "શંખેશ્વર", "lon": 71.7850, "lat": 23.5150, "type": "taluka"},
        {"name": "રાણીની વાવ", "lon": 72.1018, "lat": 23.8589, "type": "village"},
        {"name": "વરણા", "lon": 72.1550, "lat": 23.9050, "type": "village"},
        {"name": "ખાનપુર", "lon": 72.0550, "lat": 23.7950, "type": "village"},
    ]
}

# અસલી નકશા જેવા બારીક ખાંચાખૂંચીવાળા (Natural Cartographic) જિલ્લા આકારો
OFFLINE_DISTRICT_POLYGONS = {
    "મહેસાણા": [
        [71.95, 23.45], [71.93, 23.51], [71.97, 23.57], [72.02, 23.62], [72.09, 23.61],
        [72.16, 23.66], [72.22, 23.68], [72.24, 23.74], [72.29, 23.79], [72.32, 23.85],
        [72.39, 23.87], [72.46, 23.93], [72.52, 23.95], [72.59, 23.99], [72.65, 24.06],
        [72.72, 24.08], [72.79, 24.04], [72.83, 23.96], [72.81, 23.88], [72.76, 23.83],
        [72.78, 23.78], [72.82, 23.70], [72.84, 23.61], [72.82, 23.54], [72.75, 23.50],
        [72.70, 23.45], [72.66, 23.44], [72.58, 23.42], [72.53, 23.38], [72.48, 23.36],
        [72.44, 23.28], [72.38, 23.21], [72.31, 23.22], [72.25, 23.24], [72.22, 23.25],
        [72.21, 23.33], [72.18, 23.40], [72.10, 23.41], [72.03, 23.44], [71.95, 23.45]
    ],
    "પાટણ": [
        [71.03, 23.74], [71.07, 23.82], [71.13, 23.86], [71.18, 23.93], [71.25, 23.97],
        [71.36, 23.95], [71.48, 23.99], [71.58, 23.96], [71.68, 24.01], [71.79, 23.98],
        [71.90, 24.01], [72.02, 23.99], [72.12, 24.02], [72.23, 24.00], [72.34, 24.03],
        [72.44, 24.01], [72.48, 23.93], [72.45, 23.86], [72.37, 23.82], [72.32, 23.76],
        [72.25, 23.72], [72.21, 23.66], [72.16, 23.62], [72.08, 23.63], [72.02, 23.57],
        [71.96, 23.49], [71.90, 23.44], [71.81, 23.43], [71.73, 23.45], [71.67, 23.49],
        [71.62, 23.56], [71.56, 23.62], [71.48, 23.65], [71.38, 23.61], [71.27, 23.64],
        [71.16, 23.61], [71.08, 23.66], [71.03, 23.74]
    ]
}

DISTRICT_EN_TO_GUJ = {
    "kachchh": ("કચ્છ", "kutch"), "kutch": ("કચ્છ", "kutch"),
    "banaskantha": ("બનાસકાંઠા", "north"), "banas kantha": ("બનાસકાંઠા", "north"),
    "patan": ("પાટણ", "north"),
    "mahesana": ("મહેસાણા", "north"), "mehsana": ("મહેસાણા", "north"),
    "sabarkantha": ("સાબરકાંઠા", "north"), "sabar kantha": ("સાબરકાંઠા", "north"),
    "aravalli": ("અરવલ્લી", "north"), "arvalli": ("અરવલ્લી", "north"),
    "gandhinagar": ("ગાંધીનગર", "central"),
    "ahmadabad": ("અમદાવાદ", "central"), "ahmedabad": ("અમદાવાદ", "central"),
    "kheda": ("ખેડા", "central"),
    "mahisagar": ("મહીસાગર", "central"),
    "panchmahal": ("પંચમહાલ", "central"), "panch mahals": ("પંચમહાલ", "central"),
    "dohad": ("દાહોદ", "central"), "dahod": ("દાહોદ", "central"),
    "anand": ("આણંદ", "central"),
    "vadodara": ("વડોદરા", "central"),
    "chhotaudepur": ("છોટા ઉદેપુર", "central"), "chhota udaipur": ("છોટા ઉદેપુર", "central"),
    "bharuch": ("ભરૂચ", "south"),
    "narmada": ("નર્મદા", "south"),
    "surat": ("સુરત", "south"),
    "tapi": ("તાપી", "south"),
    "navsari": ("નવસારી", "south"),
    "the dangs": ("ડાંગ", "south"), "dang": ("ડાંગ", "south"), "dangs": ("ડાંગ", "south"),
    "valsad": ("વલસાડ", "south"),
    "surendranagar": ("સુરેન્દ્રનગર", "saurashtra"),
    "morbi": ("મોરબી", "saurashtra"),
    "jamnagar": ("જામનગર", "saurashtra"),
    "devbhumi dwarka": ("દેવભૂમિ દ્વારકા", "saurashtra"), "dwarka": ("દેવભૂમિ દ્વારકા", "saurashtra"),
    "porbandar": ("પોરબંદર", "saurashtra"),
    "rajkot": ("રાજકોટ", "saurashtra"),
    "botad": ("બોટાદ", "saurashtra"),
    "junagadh": ("જૂનાગઢ", "saurashtra"),
    "amreli": ("અમરેલી", "saurashtra"),
    "bhavnagar": ("ભાવનગર", "saurashtra"),
    "gir somnath": ("ગીર સોમનાથ", "saurashtra"),
}

STATE_EN_TO_GUJ = {
    "jammu & kashmir": ("જમ્મુ-કાશ્મીર", "north"), "jammu and kashmir": ("જમ્મુ-કાશ્મીર", "north"),
    "ladakh": ("લદ્દાખ", "north"), "himachal pradesh": ("હિમાચલ", "north"),
    "punjab": ("પંજાબ", "north"), "uttarakhand": ("ઉત્તરાખંડ", "north"),
    "haryana": ("હરિયાણા", "north"), "delhi": ("દિલ્હી", "north"), "nct of delhi": ("દિલ્હી", "north"),
    "rajasthan": ("રાજસ્થાન", "west"), "uttar pradesh": ("ઉત્તર પ્રદેશ", "north"),
    "bihar": ("બિહાર", "east"), "gujarat": ("ગુજરાત", "west"),
    "madhya pradesh": ("મધ્ય પ્રદેશ", "central"), "jharkhand": ("ઝારખંડ", "east"),
    "west bengal": ("પશ્ચિમ બંગાળ", "east"), "chhattisgarh": ("છત્તીસગઢ", "central"),
    "odisha": ("ઓડિશા", "east"), "orissa": ("ઓડિશા", "east"),
    "maharashtra": ("મહારાષ્ટ્ર", "west"), "telangana": ("તેલંગાણા", "south"),
    "karnataka": ("કર્ણાટક", "south"), "goa": ("ગોવા", "west"),
    "andhra pradesh": ("આંધ્ર પ્રદેશ", "south"), "kerala": ("કેરળ", "south"),
    "tamil nadu": ("તમિલનાડુ", "south"), "assam": ("આસામ", "east"),
    "arunachal pradesh": ("અરુણાચલ", "east"), "meghalaya": ("મેઘાલય", "east"),
    "manipur": ("મણિપુર", "east"), "mizoram": ("મિઝોરમ", "east"),
    "nagaland": ("નાગાલેન્ડ", "east"), "tripura": ("ત્રિપુરા", "east"), "sikkim": ("સિક્કિમ", "east"),
}

ZONE_COLORS = {
    "kutch": "#DCE775", "north": "#F8BBD0", "central": "#FFCC80",
    "saurashtra": "#CE93D8", "south": "#80DEEA", "west": "#DCE775", "east": "#80DEEA",
}
HIGHLIGHT_COLORS = ["#FEF08A", "#BAE6FD", "#FBCFE8", "#BBF7D0", "#FED7AA", "#DDD6FE", "#99F6E4", "#FECACA"]
PASTEL_PALETTE = ["#FDE68A", "#BAE6FD", "#FBCFE8", "#BBF7D0", "#DDD6FE", "#FED7AA", "#99F6E4", "#FECACA", "#E9D5FF", "#BFDBFE"]

GUJARAT_RIVERS_GEO = [
    ("નર્મદા નદી", [(74.1, 21.85), (73.5, 21.88), (73.0, 21.72), (72.6, 21.68)]),
    ("તાપી નદી", [(74.2, 21.25), (73.5, 21.28), (72.8, 21.12), (72.65, 21.05)]),
    ("સાબરમતી નદી", [(72.9, 24.1), (72.65, 23.2), (72.55, 22.6), (72.35, 22.25)]),
    ("મહી નદી", [(73.8, 23.3), (73.3, 22.8), (72.95, 22.35), (72.7, 22.2)]),
    ("બનાસ નદી", [(72.6, 24.4), (72.0, 24.1), (71.5, 23.8)]),
    ("સરસ્વતી નદી", [(72.8, 24.2), (72.2, 23.85), (71.7, 23.6)]),
    ("દમણગંગા નદી", [(73.3, 20.35), (72.95, 20.4), (72.82, 20.41)]),
]

INDIA_RIVERS_GEO = [
    ("ગંગા નદી", [(78.2, 30.1), (80.5, 26.5), (83.0, 25.3), (86.5, 25.2), (88.2, 23.0)]),
    ("યમુના નદી", [(77.2, 28.6), (78.0, 27.1), (81.8, 25.4)]),
    ("નર્મદા નદી", [(81.5, 22.7), (77.0, 22.1), (73.0, 21.7)]),
    ("ગોદાવરી નદી", [(73.8, 19.9), (78.0, 18.8), (82.1, 16.8)]),
    ("કૃષ્ણા નદી", [(74.0, 17.8), (77.5, 16.3), (80.9, 15.8)]),
]

def extract_mentioned_districts(query_text):
    q = (query_text or "").lower()
    found = []
    for kw, (guj_d, _en_q) in GUJ_DIST_KEYWORDS.items():
        if kw in q and guj_d not in found:
            found.append(guj_d)
    return found

def get_osm_en_for_guj_dist(guj_dist):
    for _kw, (gd, en_q) in GUJ_DIST_KEYWORDS.items():
        if gd == guj_dist:
            return en_q
    return f"{guj_dist}, Gujarat, India"

def wants_map(text):
    t = (text or "").lower()
    return any(kw in t for kw in (
        "નકશો", "નક્શો", "નકશા", "નક્શા", "નકશાપૂર્તિ", "naksho", "naksha", "map",
        "સંજ્ઞા વડે", "નકશામાં દર્શાવો", "કિલ્લા", "મગધ", "પ્રદેશો",
        "રાજકીય", "ભૌગોલિક", "ગામનો", "gamno", "gamda", "ખેત ઉત્પાદન", "ઉદ્યોગો", "નદીઓ", "મતદાર", "વસ્તી ગણતરી", "blo"
    )) or len(extract_mentioned_districts(text)) > 0

def _organic_border_subdivide(poly, passes=2):
    """સીધી રેખાઓને બદલે અસલી ભૌગોલિક નકશા જેવી ખાંચાખૂંચીવાળી સરહદ (Cartographic Fractal Border) બનાવે છે."""
    pts = list(poly)
    for p_idx in range(passes):
        new_pts = []
        n = len(pts)
        for i in range(n - 1):
            x1, y1 = pts[i]
            x2, y2 = pts[i + 1]
            new_pts.append([x1, y1])
            dx, dy = x2 - x1, y2 - y1
            seg_len = math.hypot(dx, dy)
            if seg_len > 0.015:
                nx, ny = -dy / seg_len, dx / seg_len
                # ડિટર્મિનિસ્ટિક તરંગો જેથી આકાર હંમેશા સ્થિર અને કુદરતી રહે
                w1 = math.sin((x1 + y1) * 47.0 + p_idx) * 0.11 * seg_len
                w2 = math.cos((x2 - y2) * 53.0 + p_idx) * 0.11 * seg_len
                new_pts.append([x1 + dx * 0.33 + nx * w1, y1 + dy * 0.33 + ny * w1])
                new_pts.append([x1 + dx * 0.67 + nx * w2, y1 + dy * 0.67 + ny * w2])
        new_pts.append(new_pts[0])
        pts = new_pts
    return pts

def _build_convex_hull_polygon(points, pad=0.09):
    pts = sorted(set((round(p[0], 4), round(p[1], 4)) for p in points))
    if len(pts) < 3:
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        base = [
            [cx - 0.18, cy - 0.12], [cx + 0.18, cy - 0.12],
            [cx + 0.22, cy + 0.04], [cx + 0.12, cy + 0.15],
            [cx - 0.14, cy + 0.14], [cx - 0.20, cy + 0.02], [cx - 0.18, cy - 0.12]
        ]
        return _organic_border_subdivide(base, passes=2)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    cx = sum(p[0] for p in hull) / len(hull)
    cy = sum(p[1] for p in hull) / len(hull)
    padded = []
    for hx, hy in hull:
        ang = math.atan2(hy - cy, hx - cx)
        padded.append([hx + math.cos(ang) * pad, hy + math.sin(ang) * pad])
    padded.append(padded[0])
    return _organic_border_subdivide(padded, passes=2)

def _polygon_covers_pins(poly_xs, poly_ys, pins):
    if not poly_xs or not pins:
        return True
    min_px, max_px = min(poly_xs), max(poly_xs)
    min_py, max_py = min(poly_ys), max(poly_ys)
    for p in pins:
        if not (min_px - 0.02 <= p["lon"] <= max_px + 0.02 and min_py - 0.02 <= p["lat"] <= max_py + 0.02):
            return False
    return True

def load_real_geojson(kind="gujarat"):
    if kind in _GEO_MEM_CACHE:
        return _GEO_MEM_CACHE[kind]
    os.makedirs("geo_cache", exist_ok=True)
    if kind == "gujarat":
        local_path = "geo_cache/gujarat_real_districts.geojson"
        urls = [
            "https://raw.githubusercontent.com/geohacker/india/master/district/india_district.geojson",
            "https://raw.githubusercontent.com/datameet/maps/master/Districts/Census_2011/2011_Dist.geojson",
        ]
    elif kind == "world":
        local_path = "geo_cache/world_countries.geojson"
        urls = ["https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json"]
    else:
        local_path = "geo_cache/india_real_states.geojson"
        urls = [
            "https://raw.githubusercontent.com/geohacker/india/master/state/india_state.geojson",
            "https://raw.githubusercontent.com/Subhash9325/GeoJson-Data-of-Indian-States/master/Indian_States",
        ]

    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
                if cached.get("features"):
                    _GEO_MEM_CACHE[kind] = cached
                    return cached
        except Exception:
            pass

    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=22) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                if kind == "gujarat":
                    guj_feats = []
                    for feat in raw.get("features", []):
                        props = feat.get("properties") or {}
                        st_val = str(props.get("NAME_1") or props.get("ST_NM") or props.get("state") or "").lower()
                        if "gujarat" in st_val:
                            guj_feats.append(feat)
                    if len(guj_feats) >= 20:
                        data = {"type": "FeatureCollection", "features": guj_feats}
                        with open(local_path, "w", encoding="utf-8") as f:
                            json.dump(data, f)
                        _GEO_MEM_CACHE[kind] = data
                        return data
                else:
                    if raw.get("features"):
                        with open(local_path, "w", encoding="utf-8") as f:
                            json.dump(raw, f)
                        _GEO_MEM_CACHE[kind] = raw
                        return raw
        except Exception:
            continue
    return None

def fetch_osm_real_boundary(place_query):
    os.makedirs("geo_cache", exist_ok=True)
    safe_key = re.sub(r"[^a-zA-Z0-9_]", "_", place_query.lower())[:50]
    cache_file = f"geo_cache/osm_{safe_key}.json"
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    try:
        q_enc = urllib.parse.quote(place_query)
        url = f"https://nominatim.openstreetmap.org/search?q={q_enc}&format=geojson&polygon_geojson=1&limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "PalajSmartSchoolTeacherApp/4.0 (education)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("features"):
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                return data
    except Exception:
        pass
    return None

def _extract_polygons_from_geom(geom):
    gtype = geom.get("type")
    coords = geom.get("coordinates", [])
    polys = []
    if gtype == "Polygon" and coords:
        polys.append(coords[0])
    elif gtype == "MultiPolygon":
        for poly in coords:
            if poly:
                polys.append(poly[0])
    return polys

def _polygon_centroid(pts):
    if not pts:
        return (0, 0)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (sum(xs) / len(xs), sum(ys) / len(ys))

def _draw_cartographic_border(ax, poly, facecolor="#FEF08A", edgecolor="#991B1B"):
    """અસલી નકશાપોથી (Atlas) જેવી ડબલ-લાઈન સરહદી હદ શૈલી દોરે છે."""
    # બહારનો હળવો પડછાયો / બોર્ડર
    ax.add_patch(patches.Polygon(
        poly, closed=True, facecolor="none", edgecolor="#F87171",
        linewidth=4.2, alpha=0.38, joinstyle="round", zorder=2
    ))
    # અંદરનો મુખ્ય પીળો/રંગીન નકશો અને ઘેરી સરહદી હદ
    ax.add_patch(patches.Polygon(
        poly, closed=True, facecolor=facecolor, edgecolor=edgecolor,
        linewidth=2.0, alpha=0.96, joinstyle="round", zorder=3
    ))

def render_textbook_map_png(spec, raw_query=""):
    if not HAS_MPL:
        return None
    font_path = get_pdf_font()
    if font_path:
        try:
            font_manager.fontManager.addfont(font_path)
            prop_name = font_manager.FontProperties(fname=font_path).get_name()
            plt.rcParams["font.sans-serif"] = [prop_name, "DejaVu Sans"]
            plt.rcParams["font.family"] = "sans-serif"
        except Exception:
            pass

    fp_title = font_manager.FontProperties(fname=font_path, size=14, weight="bold") if font_path else None
    fp_sub = font_manager.FontProperties(fname=font_path, size=10.5, weight="bold") if font_path else None
    fp_lbl = font_manager.FontProperties(fname=font_path, size=9.2, weight="bold") if font_path else None
    fp_leg = font_manager.FontProperties(fname=font_path, size=8.8) if font_path else None
    fp_small = font_manager.FontProperties(fname=font_path, size=7.6, weight="bold") if font_path else None

    fig = plt.figure(figsize=(13.0, 8.4), dpi=170)
    fig.patch.set_facecolor("#F5F5F4")

    bg_ax = fig.add_axes([0, 0, 1, 1])
    bg_ax.set_xlim(0, 100)
    bg_ax.set_ylim(0, 100)
    bg_ax.axis("off")
    bg_ax.add_patch(patches.FancyBboxPatch((1.5, 2), 97, 96, boxstyle="round,pad=0.4", facecolor="#FAF8F5", edgecolor="#78716C", linewidth=1.8))
    bg_ax.text(50, 94.8, spec.get("header_top", "સામાજિક વિજ્ઞાન - નકશા પૂર્તિ"), ha="center", va="center", color="#1E293B", fontproperties=fp_title)
    bg_ax.text(50, 91.2, spec.get("title", "ભૌગોલિક / રાજકીય નકશો"), ha="center", va="center", color="#B91C1C", fontproperties=fp_sub)

    map_ax = fig.add_axes([0.035, 0.055, 0.72, 0.82])
    map_ax.set_facecolor("#E0F2FE")
    for spine in map_ax.spines.values():
        spine.set_edgecolor("#475569")
        spine.set_linewidth(1.4)
    map_ax.set_xticks([])
    map_ax.set_yticks([])

    region = str(spec.get("region", "gujarat")).lower()
    mentioned_dists = extract_mentioned_districts(raw_query)

    hl_map = {}
    if mentioned_dists:
        for idx_d, d in enumerate(mentioned_dists):
            hl_map[d] = {"place": d, "label": d, "color": HIGHLIGHT_COLORS[idx_d % len(HIGHLIGHT_COLORS)]}
    else:
        for idx_h, h in enumerate(spec.get("highlights", [])):
            p_name = str(h.get("place", "")).strip()
            if p_name:
                h_copy = dict(h)
                if not h_copy.get("color"):
                    h_copy["color"] = HIGHLIGHT_COLORS[idx_h % len(HIGHLIGHT_COLORS)]
                hl_map[p_name] = h_copy

    only_selected = bool(spec.get("only_selected", False)) or (len(mentioned_dists) >= 1)
    q_low = (raw_query or "").lower()
    force_rivers = bool(spec.get("show_rivers", False)) or any(w in q_low for w in ("નદી", "nadi", "river", "નર્મદા", "તાપી", "સાબરમતી", "ગંગા", "ભૌગોલિક", "bhaugolik"))

    pins_to_draw = []
    for d_name in mentioned_dists:
        if d_name in DISTRICT_BUILTIN_PINS:
            pins_to_draw.extend(DISTRICT_BUILTIN_PINS[d_name])
    for p_item in (spec.get("pins") or []):
        try:
            p_name = str(p_item.get("name", "")).strip()
            p_lat = float(p_item.get("lat"))
            p_lon = float(p_item.get("lon"))
            p_type = str(p_item.get("type", "village")).lower()
            if p_name and not any(existing["name"] == p_name for existing in pins_to_draw):
                pins_to_draw.append({"name": p_name, "lat": p_lat, "lon": p_lon, "type": p_type})
        except Exception:
            continue

    if region == "local":
        search_en = str(spec.get("osm_query_en") or "Mehsana, Gujarat, India").strip()
        osm_geo = fetch_osm_real_boundary(search_en)
        all_x, all_y = [], []
        if osm_geo and osm_geo.get("features"):
            feat = osm_geo["features"][0]
            polys = _extract_polygons_from_geom(feat.get("geometry") or {})
            for poly in polys:
                _draw_cartographic_border(map_ax, poly, facecolor="#FEF08A", edgecolor="#991B1B")
                for px, py in poly:
                    all_x.append(px)
                    all_y.append(py)
        if all_x and all_y:
            dx = max((max(all_x) - min(all_x)) * 0.14, 0.06)
            dy = max((max(all_y) - min(all_y)) * 0.14, 0.06)
            map_ax.set_xlim(min(all_x) - dx, max(all_x) + dx)
            map_ax.set_ylim(min(all_y) - dy, max(all_y) + dy)
            map_ax.set_aspect("equal", adjustable="datalim")
        else:
            region = "gujarat"

    if region == "world":
        geo = load_real_geojson("world")
        if geo and geo.get("features"):
            all_x, all_y = [], []
            for idx_w, feat in enumerate(geo["features"]):
                props = feat.get("properties") or {}
                raw_name = str(props.get("name") or "").strip()
                is_india = "india" in raw_name.lower()
                matched_hl = next((v for k, v in hl_map.items() if k.lower() in raw_name.lower()), None)
                if only_selected and not matched_hl:
                    continue
                fc = "#EF4444" if is_india else (matched_hl.get("color") if matched_hl else PASTEL_PALETTE[idx_w % len(PASTEL_PALETTE)])
                polys = _extract_polygons_from_geom(feat.get("geometry") or {})
                for poly in polys:
                    map_ax.add_patch(patches.Polygon(poly, closed=True, facecolor=fc, edgecolor="#334155", linewidth=0.8, alpha=0.95))
                    for px, py in poly:
                        all_x.append(px)
                        all_y.append(py)
                if (is_india or matched_hl) and polys:
                    cx, cy = _polygon_centroid(max(polys, key=len))
                    lbl = matched_hl.get("label") if matched_hl else "ભારત"
                    map_ax.text(cx, cy, lbl, ha="center", va="center", color="#0F172A", fontproperties=fp_lbl)
            if all_x and all_y:
                map_ax.set_xlim(-175, 180)
                map_ax.set_ylim(-58, 84)
                map_ax.set_aspect("equal", adjustable="datalim")

    elif region == "india":
        geo = load_real_geojson("india")
        if geo and geo.get("features"):
            all_x, all_y = [], []
            for idx_st, feat in enumerate(geo["features"]):
                props = feat.get("properties") or {}
                raw_name = str(props.get("NAME_1") or props.get("ST_NM") or props.get("state") or "").strip()
                guj_name, zone = STATE_EN_TO_GUJ.get(raw_name.lower(), (raw_name, "central"))
                matched_hl = next((v for k, v in hl_map.items() if k in guj_name or guj_name in k or k.lower() in raw_name.lower()), None)
                fc = matched_hl.get("color") if matched_hl else ("#F1F5F9" if hl_map else ZONE_COLORS.get(zone, "#E2E8F0"))
                ec = "#B91C1C" if matched_hl else "#334155"
                lw = 2.2 if matched_hl else 0.85

                polys = _extract_polygons_from_geom(feat.get("geometry") or {})
                biggest = max(polys, key=len) if polys else []
                for poly in polys:
                    map_ax.add_patch(patches.Polygon(poly, closed=True, facecolor=fc, edgecolor=ec, linewidth=lw, alpha=0.96, joinstyle="round"))
                    for px, py in poly:
                        all_x.append(px)
                        all_y.append(py)
                if biggest:
                    cx, cy = _polygon_centroid(biggest)
                    map_ax.text(cx, cy, guj_name, ha="center", va="center", color="#0F172A", fontproperties=fp_lbl if matched_hl else fp_small)
                    if matched_hl and matched_hl.get("label") and matched_hl.get("label") != guj_name:
                        map_ax.text(cx, cy - 0.9, f"▲ {matched_hl.get('label')[:16]}", ha="center", va="center", color="#991B1B", fontproperties=fp_lbl)
            if force_rivers:
                for r_name, pts in INDIA_RIVERS_GEO:
                    xs, ys = zip(*pts)
                    map_ax.plot(xs, ys, color="#0284C7", linewidth=2.4)
                    map_ax.text(xs[1], ys[1] + 0.5, r_name, ha="center", va="center", color="#0369A1", fontproperties=fp_lbl)
            if all_x and all_y:
                dx = max((max(all_x) - min(all_x)) * 0.14, 1.0)
                dy = max((max(all_y) - min(all_y)) * 0.14, 1.0)
                map_ax.set_xlim(min(all_x) - dx, max(all_x) + dx)
                map_ax.set_ylim(min(all_y) - dy, max(all_y) + dy)
                map_ax.set_aspect("equal", adjustable="datalim")
                map_ax.text(min(all_x) + 3.5, min(all_y) + 6.0, "અરબ સાગર", ha="center", va="center", color="#0369A1", fontproperties=fp_lbl)
                map_ax.text(max(all_x) - 8.5, min(all_y) + 6.0, "બંગાળની ખાડી", ha="center", va="center", color="#0369A1", fontproperties=fp_lbl)

    elif region == "gujarat":
        all_x, all_y = [], []
        target_dists = mentioned_dists or list(hl_map.keys())
        geo = load_real_geojson("gujarat")

        if only_selected and target_dists:
            for idx_td, d_name in enumerate(target_dists):
                col = HIGHLIGHT_COLORS[idx_td % len(HIGHLIGHT_COLORS)]
                drawn_this = False

                # ૧. પહેલા ગુજરાતના અસલી GeoJSON (gujarat_real_districts) માંથી શોધો
                if geo and geo.get("features"):
                    for feat in geo["features"]:
                        props = feat.get("properties") or {}
                        raw_dist = str(props.get("NAME_2") or props.get("DISTRICT") or props.get("dtname") or props.get("district") or "").strip()
                        guj_name, _z = DISTRICT_EN_TO_GUJ.get(raw_dist.lower(), (raw_dist, "central"))
                        if d_name in guj_name or guj_name in d_name:
                            polys = _extract_polygons_from_geom(feat.get("geometry") or {})
                            cand_x = [px for poly in polys for px, _ in poly]
                            cand_y = [py for poly in polys for _, py in poly]
                            if polys and _polygon_covers_pins(cand_x, cand_y, pins_to_draw):
                                for poly in polys:
                                    _draw_cartographic_border(map_ax, poly, facecolor=col, edgecolor="#991B1B")
                                all_x.extend(cand_x)
                                all_y.extend(cand_y)
                                drawn_this = True
                                break

                # ૨. ન મળે તો બિલ્ટ-ઇન પ્રાકૃતિક ખાંચાખૂંચીવાળી સરહદ (Organic Cartographic Border) વાપરો
                if not drawn_this and d_name in OFFLINE_DISTRICT_POLYGONS:
                    organic_poly = _organic_border_subdivide(OFFLINE_DISTRICT_POLYGONS[d_name], passes=2)
                    _draw_cartographic_border(map_ax, organic_poly, facecolor=col, edgecolor="#991B1B")
                    for px, py in organic_poly:
                        all_x.append(px)
                        all_y.append(py)
                    drawn_this = True

                # ૩. અન્ય જિલ્લા માટે OSM અસલી સરહદ લાવો
                if not drawn_this:
                    osm_d = fetch_osm_real_boundary(get_osm_en_for_guj_dist(d_name))
                    if osm_d and osm_d.get("features"):
                        polys = _extract_polygons_from_geom(osm_d["features"][0].get("geometry") or {})
                        cand_x = [px for poly in polys for px, _ in poly]
                        cand_y = [py for poly in polys for _, py in poly]
                        if polys and _polygon_covers_pins(cand_x, cand_y, pins_to_draw):
                            for poly in polys:
                                _draw_cartographic_border(map_ax, poly, facecolor=col, edgecolor="#991B1B")
                            all_x.extend(cand_x)
                            all_y.extend(cand_y)
                            drawn_this = True

        if not all_x and not only_selected and geo and geo.get("features"):
            for idx_d, feat in enumerate(geo["features"]):
                props = feat.get("properties") or {}
                raw_dist = str(props.get("NAME_2") or props.get("DISTRICT") or props.get("dtname") or props.get("district") or "").strip()
                guj_name, zone = DISTRICT_EN_TO_GUJ.get(raw_dist.lower(), (raw_dist, "central"))
                matched_hl = next((v for k, v in hl_map.items() if k in guj_name or guj_name in k or k.lower() in raw_dist.lower()), None)

                fc = matched_hl.get("color") if matched_hl else ("#F1F5F9" if hl_map else ZONE_COLORS.get(zone, "#E2E8F0"))
                ec = "#B91C1C" if matched_hl else "#334155"
                lw = 2.2 if matched_hl else 0.9

                polys = _extract_polygons_from_geom(feat.get("geometry") or {})
                biggest = max(polys, key=len) if polys else []
                for poly in polys:
                    map_ax.add_patch(patches.Polygon(poly, closed=True, facecolor=fc, edgecolor=ec, linewidth=lw, alpha=0.96, joinstyle="round"))
                    for px, py in poly:
                        all_x.append(px)
                        all_y.append(py)
                if biggest and not pins_to_draw:
                    cx, cy = _polygon_centroid(biggest)
                    map_ax.text(cx, cy, guj_name, ha="center", va="center", color="#0F172A", fontproperties=fp_lbl if matched_hl else fp_small)

        # ૪. જો હજુ પણ સરહદ ન મળી હોય તો તાલુકા/ગામોની ફરતે પ્રાકૃતિક ખાંચાખૂંચીવાળી સરહદ બનાવો
        if not all_x and pins_to_draw:
            hull_poly = _build_convex_hull_polygon([(p["lon"], p["lat"]) for p in pins_to_draw], pad=0.09)
            _draw_cartographic_border(map_ax, hull_poly, facecolor="#FEF08A", edgecolor="#991B1B")
            for px, py in hull_poly:
                all_x.append(px)
                all_y.append(py)

        if force_rivers and all_x and all_y:
            for r_name, pts in GUJARAT_RIVERS_GEO:
                xs, ys = zip(*pts)
                if only_selected:
                    if not any((min(all_x) - 0.15 <= x <= max(all_x) + 0.15 and min(all_y) - 0.15 <= y <= max(all_y) + 0.15) for x, y in pts):
                        continue
                map_ax.plot(xs, ys, color="#0284C7", linewidth=2.2, alpha=0.8, zorder=4)
                map_ax.text(xs[1], ys[1] + 0.03, r_name, ha="center", va="center", color="#0369A1", fontproperties=fp_small, zorder=5)

        if pins_to_draw:
            for p in pins_to_draw:
                px, py = p["lon"], p["lat"]
                all_x.append(px)
                all_y.append(py)
                is_taluka = p.get("type") == "taluka"
                if is_taluka:
                    map_ax.scatter([px], [py], s=75, marker="*", color="#DC2626", edgecolor="#0F172A", linewidth=0.7, zorder=6)
                    map_ax.text(px, py + 0.014, p["name"], ha="center", va="bottom", color="#991B1B", fontproperties=fp_lbl,
                                bbox=dict(boxstyle="round,pad=0.12", facecolor="#FFFFFF", edgecolor="none", alpha=0.75), zorder=7)
                else:
                    map_ax.scatter([px], [py], s=26, marker="o", color="#1D4ED8", edgecolor="#FFFFFF", linewidth=0.6, zorder=5)
                    map_ax.text(px, py - 0.012, p["name"], ha="center", va="top", color="#1E3A8A", fontproperties=fp_small,
                                bbox=dict(boxstyle="round,pad=0.08", facecolor="#FFFFFF", edgecolor="none", alpha=0.68), zorder=6)

        if all_x and all_y:
            dx = max((max(all_x) - min(all_x)) * 0.14, 0.15)
            dy = max((max(all_y) - min(all_y)) * 0.14, 0.15)
            map_ax.set_xlim(min(all_x) - dx, max(all_x) + dx)
            map_ax.set_ylim(min(all_y) - dy, max(all_y) + dy)
            map_ax.set_aspect("equal", adjustable="datalim")
            if not only_selected:
                map_ax.text(69.5, 22.65, "કચ્છનો અખાત", ha="center", va="center", color="#0369A1", fontproperties=fp_small)
                map_ax.text(72.35, 21.45, "ખંભાતનો અખાત", ha="center", va="center", color="#0369A1", fontproperties=fp_small)
                map_ax.text(70.2, 20.45, "અરબ સાગર", ha="center", va="center", color="#0369A1", fontproperties=fp_lbl)

    map_ax.text(0.95, 0.94, "ઉત્તર", transform=map_ax.transAxes, ha="center", va="center", color="#0F172A", fontproperties=fp_lbl)
    map_ax.annotate("", xy=(0.95, 0.91), xytext=(0.95, 0.80), xycoords="axes fraction", textcoords="axes fraction", arrowprops=dict(arrowstyle="->", lw=2.2, color="#0F172A"))

    bg_ax.add_patch(patches.FancyBboxPatch((77.2, 5.5), 20.0, 82.0, boxstyle="round,pad=0.35", facecolor="#FFFFFF", edgecolor="#94A3B8", linewidth=1.3))
    bg_ax.text(87.2, 84.8, "📌 સંજ્ઞા સૂચિ", ha="center", va="center", color="#1E3A8A", fontproperties=fp_sub)
    bg_ax.plot([78.8, 95.6], [82.4, 82.4], color="#CBD5E1", linewidth=1)

    default_legends = {
        "gujarat": [{"color": "#DCE775", "label": "કચ્છ પ્રદેશ"}, {"color": "#F8BBD0", "label": "ઉત્તર ગુજરાત"}, {"color": "#FFCC80", "label": "મધ્ય ગુજરાત"}, {"color": "#CE93D8", "label": "સૌરાષ્ટ્ર"}, {"color": "#80DEEA", "label": "દક્ષિણ ગુજરાત"}],
        "india": [{"color": "#F8BBD0", "label": "ઉત્તર ભારત"}, {"color": "#FFCC80", "label": "મધ્ય ભારત"}, {"color": "#DCE775", "label": "પશ્ચિમ ભારત"}, {"color": "#80DEEA", "label": "પૂર્વ ભારત"}, {"color": "#CE93D8", "label": "દક્ષિણ ભારત"}],
        "world": [{"color": "#EF4444", "label": "ભારત દેશ"}, {"color": "#FDE68A", "label": "વિશ્વના દેશો"}],
        "local": [{"color": "#FEF08A", "label": "વિસ્તારની સરહદ"}],
    }
    if hl_map:
        legend_items = [{"color": v["color"], "label": v.get("label") or k} for k, v in hl_map.items()]
    else:
        legend_items = spec.get("legend") or default_legends.get(region, default_legends["gujarat"])

    if pins_to_draw:
        legend_items = [
            {"color": "#DC2626", "label": "★ તાલુકા મથક"},
            {"color": "#1D4ED8", "label": "● મુખ્ય ગામ"},
        ] + list(legend_items)
    if force_rivers:
        legend_items = [{"color": "#0284C7", "label": "મુખ્ય નદીઓ"}] + list(legend_items)

    for idx_l, li in enumerate(legend_items[:9]):
        ly = 78.0 - idx_l * 7.8
        bg_ax.add_patch(patches.Rectangle((78.8, ly - 1.6), 3.4, 3.2, facecolor=li.get("color", "#FACC15"), edgecolor="#334155", linewidth=1))
        bg_ax.text(83.3, ly, str(li.get("label", ""))[:16], ha="left", va="center", color="#0F172A", fontproperties=fp_leg)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=170)
    plt.close(fig)
    return buf.getvalue()

def detect_default_map_spec(query_text):
    q = (query_text or "").lower()
    dist_list = extract_mentioned_districts(query_text)
    if dist_list:
        hls = [{"place": d, "label": d, "color": HIGHLIGHT_COLORS[i % len(HIGHLIGHT_COLORS)]} for i, d in enumerate(dist_list)]
        return {
            "region": "gujarat",
            "only_selected": True,
            "header_top": "સામાજિક વિજ્ઞાન - નકશા પૂર્તિ",
            "title": f"{', '.join(dist_list)} જિલ્લાના તાલુકા મથકો અને મુખ્ય ગામો",
            "show_rivers": True,
            "highlights": hls,
        }
    highlights = []
    for guj_st in ["ગુજરાત", "રાજસ્થાન", "દિલ્હી", "મહારાષ્ટ્ર", "મધ્ય પ્રદેશ", "ઉત્તર પ્રદેશ", "પંજાબ", "બિહાર", "કર્ણાટક", "તમિલનાડુ", "કેરળ"]:
        if guj_st in query_text:
            highlights.append({"place": guj_st, "label": guj_st, "color": HIGHLIGHT_COLORS[len(highlights) % len(HIGHLIGHT_COLORS)]})
    if any(w in q for w in ("વિશ્વ", "world", "દુનિયા", "ખંડો", "મહાસાગર")):
        return {"region": "world", "header_top": "સામાજિક વિજ્ઞાન - વિશ્વ નકશા પૂર્તિ", "title": "વિશ્વનો ભૌગોલિક અને રાજકીય નકશો", "highlights": highlights}
    if any(w in q for w in ("ભારત", "india", "મગધ", "દિલ્હી", "રાજસ્થાન", "મહારાષ્ટ્ર", "પંજાબ", "બિહાર", "ગંગા", "હિમાલય")) or highlights:
        show_riv = any(w in q for w in ("નદી", "nadi", "river", "ગંગા", "યમુના", "ગોદાવરી"))
        return {"region": "india", "header_top": "સામાજિક વિજ્ઞાન - ભારત નકશા પૂર્તિ", "title": "ભારતનો રાજકીય અને ભૌગોલિક નકશો", "show_rivers": show_riv, "highlights": highlights}
    show_riv = any(w in q for w in ("નદી", "nadi", "river", "નર્મદા", "તાપી", "સાબરમતી"))
    return {"region": "gujarat", "header_top": "સામાજિક વિજ્ઞાન - નકશા પૂર્તિ", "title": "ગુજરાતનો રાજકીય નકશો", "show_rivers": show_riv}

def extract_or_build_map_bytes(content, is_map_query=False, raw_query=""):
    map_img_bytes = None
    clean_text = content
    mentioned_dists = extract_mentioned_districts(raw_query)
    if "```map_json" in clean_text:
        m = re.search(r"```map_json\s*([\s\S]*?)```", clean_text)
        if m:
            try:
                spec = json.loads(m.group(1).strip())
                if spec.get("region") in ("village", "blo_village"):
                    spec["region"] = "local"
                if mentioned_dists:
                    spec["region"] = "gujarat"
                    spec["only_selected"] = True
                    spec["title"] = f"{', '.join(mentioned_dists)} જિલ્લાના તાલુકા મથકો અને મુખ્ય ગામો"
                    spec["highlights"] = [{"place": d, "label": d, "color": HIGHLIGHT_COLORS[i % len(HIGHLIGHT_COLORS)]} for i, d in enumerate(mentioned_dists)]
                map_img_bytes = render_textbook_map_png(spec, raw_query=raw_query)
            except Exception:
                map_img_bytes = render_textbook_map_png(detect_default_map_spec(raw_query), raw_query=raw_query)
        clean_text = re.sub(r"```map_json[\s\S]*?```", "", clean_text)
    if is_map_query and not map_img_bytes:
        map_img_bytes = render_textbook_map_png(detect_default_map_spec(raw_query), raw_query=raw_query)
    return map_img_bytes, clean_text
