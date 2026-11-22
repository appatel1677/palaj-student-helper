import os
import sqlite3
from dotenv import load_dotenv
load_dotenv()

os.makedirs(".files", exist_ok=True)
os.makedirs("geo_cache", exist_ok=True)

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.input_widget import Select
import json, io, re, math, asyncio, urllib.request, urllib.parse
from PIL import Image
from fpdf import FPDF

# ==============================================================================
# AUTO-CREATE SQLITE TABLES FOR CHAINLIT LEFT SIDEBAR (CHAT HISTORY)
# ==============================================================================
DB_FILE = os.path.abspath("chat_history.db")

def init_chainlit_sqlite_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        "id" TEXT PRIMARY KEY,
        "identifier" TEXT NOT NULL UNIQUE,
        "metadata" TEXT NOT NULL,
        "createdAt" TEXT
    );
    CREATE TABLE IF NOT EXISTS threads (
        "id" TEXT PRIMARY KEY,
        "createdAt" TEXT,
        "name" TEXT,
        "userId" TEXT,
        "userIdentifier" TEXT,
        "tags" TEXT,
        "metadata" TEXT,
        FOREIGN KEY ("userId") REFERENCES users("id") ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS steps (
        "id" TEXT PRIMARY KEY,
        "name" TEXT NOT NULL,
        "type" TEXT NOT NULL,
        "threadId" TEXT NOT NULL,
        "parentId" TEXT,
        "streaming" BOOLEAN NOT NULL,
        "waitForAnswer" BOOLEAN,
        "isError" BOOLEAN,
        "metadata" TEXT,
        "tags" TEXT,
        "input" TEXT,
        "output" TEXT,
        "createdAt" TEXT,
        "start" TEXT,
        "end" TEXT,
        "generation" TEXT,
        "showInput" TEXT,
        "language" TEXT,
        "indent" INTEGER,
        "defaultOpen" BOOLEAN,
        "autoCollapse" BOOLEAN,
        FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS elements (
        "id" TEXT PRIMARY KEY,
        "threadId" TEXT,
        "type" TEXT,
        "url" TEXT,
        "chainlitKey" TEXT,
        "name" TEXT NOT NULL,
        "display" TEXT,
        "objectKey" TEXT,
        "size" TEXT,
        "page" INTEGER,
        "language" TEXT,
        "forId" TEXT,
        "mime" TEXT,
        "props" TEXT,
        FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS feedbacks (
        "id" TEXT PRIMARY KEY,
        "forId" TEXT NOT NULL,
        "threadId" TEXT NOT NULL,
        "value" INTEGER NOT NULL,
        "comment" TEXT,
        FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
    );
    """)
    try:
        cur.execute('ALTER TABLE steps ADD COLUMN "autoCollapse" BOOLEAN')
    except Exception:
        pass
    conn.commit()
    conn.close()

init_chainlit_sqlite_db()

@cl.data_layer
def get_data_layer():
    db_url = f"sqlite+aiosqlite:///{DB_FILE.replace(chr(92), '/')}"
    return SQLAlchemyDataLayer(conninfo=db_url)

@cl.password_auth_callback
def auth_callback(username: str, password: str):
    ident = (username or "palaj@school.com").strip()
    return cl.User(identifier=ident, metadata={"role": "teacher"})

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib import font_manager
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

ACTIVE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]

DEFAULT_IMAGE_MODELS = [
    "gemini-2.5-flash-image",
]

_CLIENT_CACHE = {}
_KEY_MODELS_CACHE = {}
_GEO_MEM_CACHE = {}
_PDF_FONT_CACHE = None
_SYLLABUS_CACHE = None

def get_api_keys():
    raw = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
    return [k.strip().strip("\"'") for k in str(raw).split(",") if k.strip()]

def get_cached_client(api_key):
    if api_key not in _CLIENT_CACHE:
        _CLIENT_CACHE[api_key] = genai.Client(api_key=api_key)
    return _CLIENT_CACHE[api_key]

def get_working_models_for_key(api_key, preferred_model="gemini-2.5-flash"):
    cache_key = (api_key, preferred_model)
    if cache_key in _KEY_MODELS_CACHE:
        return _KEY_MODELS_CACHE[cache_key]
    discovered = []
    try:
        client = get_cached_client(api_key)
        for m in client.models.list():
            name = (getattr(m, "name", "") or "").replace("models/", "")
            low = name.lower()
            if "gemini" in low and "flash" in low and not any(x in low for x in ("2.0", "1.5", "1.0", "image", "audio", "tts", "embedding", "live", "thinking", "robotics")):
                discovered.append(name)
    except Exception:
        pass
    base = discovered if discovered else list(ACTIVE_MODELS)
    ordered = list(dict.fromkeys(([preferred_model] if preferred_model in base or not discovered else []) + base))
    _KEY_MODELS_CACHE[cache_key] = ordered[:4]
    return _KEY_MODELS_CACHE[cache_key]

def get_pdf_font():
    global _PDF_FONT_CACHE
    if _PDF_FONT_CACHE:
        return _PDF_FONT_CACHE
    for p in ["C:/Windows/Fonts/Nirmala.ttf", "C:/Windows/Fonts/Shruti.ttf", "NotoSansGujarati-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSansGujarati-Regular.ttf"]:
        if os.path.exists(p):
            _PDF_FONT_CACHE = p
            return p
    return None

def svg_to_png_bytes(svg_code):
    try:
        import fitz
        doc = fitz.open(stream=svg_code.encode("utf-8"), filetype="svg")
        pix = doc[0].get_pixmap(dpi=170, alpha=False)
        return pix.tobytes("png")
    except Exception:
        return None

def make_svg_or_png_element(svg_code, name="diagram"):
    clean_svg = svg_code.strip()
    if "xmlns=" not in clean_svg:
        clean_svg = clean_svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    return cl.Image(name=f"{name}.svg", content=clean_svg.encode("utf-8"), mime="image/svg+xml", display="inline")

def build_pdf_bytes(messages):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    try:
        pdf.set_text_shaping(True)
    except Exception:
        pass
    font_path = get_pdf_font()
    base_font = "Gujarati" if font_path else "helvetica"
    if font_path:
        pdf.add_font("Gujarati", "", font_path)
        pdf.add_font("Gujarati", "B", font_path)
    pdf.add_page()
    pdf.set_font(base_font, "B", 15)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 10, "Standard 3 to 8 Smart AI Palaj Student Helper - Notes", ln=True, align="C")
    pdf.set_draw_color(147, 197, 253)
    pdf.line(12, pdf.get_y(), 198, pdf.get_y())
    pdf.ln(4)

    for m in messages:
        is_user = m["role"] == "user"
        pdf.set_font(base_font, "B", 11)
        pdf.set_text_color(185, 28, 28) if is_user else pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 7, ("વિદ્યાર્થી / શિક્ષક પ્રશ્ન:" if is_user else "સ્માર્ટ AI શિક્ષક જવાબ:"), ln=True)

        vis_bytes = m.get("map_bytes") or m.get("image_bytes")
        if not vis_bytes and m.get("math_svg"):
            vis_bytes = svg_to_png_bytes(m["math_svg"])
        if not vis_bytes and "<svg" in m.get("content", "").lower():
            svg_m = re.search(r"(<svg[\s\S]*?</svg>)", m["content"], flags=re.IGNORECASE)
            if svg_m:
                vis_bytes = svg_to_png_bytes(svg_m.group(1))

        if vis_bytes:
            try:
                pil_im = Image.open(io.BytesIO(vis_bytes)).convert("RGB")
                img_buf = io.BytesIO()
                pil_im.save(img_buf, format="JPEG", quality=88)
                img_buf.seek(0)
                aspect = pil_im.height / max(pil_im.width, 1)
                disp_w = 176
                disp_h = min(disp_w * aspect, 125)
                if pdf.get_y() + disp_h > 275:
                    pdf.add_page()
                pdf.image(img_buf, x=17, w=disp_w, h=disp_h)
                pdf.ln(3)
            except Exception:
                pass

        pdf.set_font(base_font, "", 10.5)
        pdf.set_text_color(30, 41, 59)
        clean_txt = re.sub(r"```(?:svg|xml|html)?\s*<svg[\s\S]*?</svg>\s*```", "", m["content"], flags=re.IGNORECASE)
        clean_txt = re.sub(r"<svg[\s\S]*?</svg>", "", clean_txt, flags=re.IGNORECASE)
        clean_txt = re.sub(r"```(?:map_json|village_map_json)[\s\S]*?```", "", clean_txt)
        clean_txt = re.sub(r"<[^>]+>", "", clean_txt)
        clean_txt = clean_txt.replace("**", "").replace("###", "").replace("##", "").strip()
        if clean_txt:
            pdf.multi_cell(0, 6.2, clean_txt)
        pdf.ln(3)
        pdf.set_draw_color(226, 232, 240)
        pdf.line(14, pdf.get_y(), 196, pdf.get_y())
        pdf.ln(3)

    return bytes(pdf.output())

def format_friendly_error(err_str):
    e = str(err_str)
    if "429" in e or "RESOURCE_EXHAUSTED" in e:
        return "API Key નો ફ્રી ક્વોટા પૂરો થઈ ગયો છે. થોડીવાર પછી પ્રયાસ કરો અથવા નવી API Key ઉમેરો."
    if "400" in e and ("API_KEY_INVALID" in e or "API key not valid" in e):
        return "તમારી GEMINI_API_KEY ખોટી છે. Environment Variables માં તપાસો."
    return f"કનેક્શન સમસ્યા: {e[:140]}"

async def transcribe_gujarati_bytes_async(audio_bytes, mime_type, api_keys, preferred_model="gemini-2.5-flash"):
    if not HAS_GENAI or not api_keys or not audio_bytes or len(audio_bytes) < 100:
        return "", "API Key અથવા ઓડિયો ઉપલબ્ધ નથી."
    prompt = "Transcribe ONLY the exact spoken words in Gujarati script (ગુજરાતી લિપિ). No extra text."
    last_err = ""
    for key in api_keys:
        client = get_cached_client(key)
        models_list = await asyncio.to_thread(get_working_models_for_key, key, preferred_model)
        for mod in models_list:
            try:
                resp = await client.aio.models.generate_content(
                    model=mod,
                    contents=[types.Part.from_bytes(data=audio_bytes, mime_type=mime_type or "audio/webm"), prompt]
                )
                if resp and resp.text and resp.text.strip():
                    return resp.text.strip(), ""
            except Exception as e:
                last_err = str(e)
    return "", format_friendly_error(last_err)

def load_syllabus():
    global _SYLLABUS_CACHE
    if _SYLLABUS_CACHE is not None:
        return _SYLLABUS_CACHE
    if os.path.exists("diksha_syllabus.json"):
        with open("diksha_syllabus.json", "r", encoding="utf-8") as f:
            _SYLLABUS_CACHE = json.load(f)
            return _SYLLABUS_CACHE
    _SYLLABUS_CACHE = {}
    return _SYLLABUS_CACHE

# ==============================================================================
# REAL GIS MAP ENGINE + MULTI-DISTRICT ZOOM ENGINE
# ==============================================================================
GUJ_DIST_KEYWORDS = {
    "મહેસાણા": "મહેસાણા", "mahesana": "મહેસાણા", "mehsana": "મહેસાણા",
    "બનાસકાંઠા": "બનાસકાંઠા", "banaskantha": "બનાસકાંઠા", "banas kantha": "બનાસકાંઠા",
    "પાટણ": "પાટણ", "patan": "પાટણ",
    "કચ્છ": "કચ્છ", "kutch": "કચ્છ", "kachchh": "કચ્છ",
    "સાબરકાંઠા": "સાબરકાંઠા", "sabarkantha": "સાબરકાંઠા",
    "અરવલ્લી": "અરવલ્લી", "aravalli": "અરવલ્લી",
    "ગાંધીનગર": "ગાંધીનગર", "gandhinagar": "ગાંધીનગર",
    "અમદાવાદ": "અમદાવાદ", "ahmedabad": "અમદાવાદ",
    "ખેડા": "ખેડા", "kheda": "ખેડા",
    "આણંદ": "આણંદ", "anand": "આણંદ",
    "વડોદરા": "વડોદરા", "vadodara": "વડોદરા",
    "સુરત": "સુરત", "surat": "સુરત",
    "ભરૂચ": "ભરૂચ", "bharuch": "ભરૂચ",
    "નર્મદા": "નર્મદા", "narmada": "નર્મદા",
    "વલસાડ": "વલસાડ", "valsad": "વલસાડ",
    "નવસારી": "નવસારી", "navsari": "નવસારી",
    "ડાંગ": "ડાંગ", "dang": "ડાંગ",
    "રાજકોટ": "રાજકોટ", "rajkot": "રાજકોટ",
    "જામનગર": "જામનગર", "jamnagar": "જામનગર",
    "જૂનાગઢ": "જૂનાગઢ", "junagadh": "જૂનાગઢ",
    "ભાવનગર": "ભાવનગર", "bhavnagar": "ભાવનગર",
    "અમરેલી": "અમરેલી", "amreli": "અમરેલી",
    "મોરબી": "મોરબી", "morbi": "મોરબી",
    "સુરેન્દ્રનગર": "સુરેન્દ્રનગર", "surendranagar": "સુરેન્દ્રનગર",
    "પોરબંદર": "પોરબંદર", "porbandar": "પોરબંદર",
    "ગીર સોમનાથ": "ગીર સોમનાથ", "gir somnath": "ગીર સોમનાથ",
    "દેવભૂમિ દ્વારકા": "દેવભૂમિ દ્વારકા", "dwarka": "દેવભૂમિ દ્વારકા",
    "બોટાદ": "બોટાદ", "botad": "બોટાદ",
    "મહીસાગર": "મહીસાગર", "mahisagar": "મહીસાગર",
    "પંચમહાલ": "પંચમહાલ", "panchmahal": "પંચમહાલ",
    "દાહોદ": "દાહોદ", "dahod": "દાહોદ",
    "છોટા ઉદેપુર": "છોટા ઉદેપુર", "chhota udaipur": "છોટા ઉદેપુર",
    "તાપી": "તાપી", "tapi": "તાપી",
}

def extract_mentioned_districts(query_text):
    q = (query_text or "").lower()
    found = []
    for kw, guj_d in GUJ_DIST_KEYWORDS.items():
        if kw in q and guj_d not in found:
            found.append(guj_d)
    return found

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
HIGHLIGHT_COLORS = ["#FACC15", "#38BDF8", "#F472B6", "#4ADE80", "#FB923C", "#A78BFA", "#2DD4BF", "#F87171"]
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

def load_real_geojson(kind="gujarat"):
    if kind in _GEO_MEM_CACHE:
        return _GEO_MEM_CACHE[kind]
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
            with urllib.request.urlopen(req, timeout=15) as resp:
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
        with urllib.request.urlopen(req, timeout=8) as resp:
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

def render_textbook_map_png(spec, raw_query=""):
    if not HAS_MPL:
        return None
    font_path = get_pdf_font()
    fp_title = font_manager.FontProperties(fname=font_path, size=14, weight="bold") if font_path else None
    fp_sub = font_manager.FontProperties(fname=font_path, size=10.5, weight="bold") if font_path else None
    fp_lbl = font_manager.FontProperties(fname=font_path, size=9.5, weight="bold") if font_path else None
    fp_leg = font_manager.FontProperties(fname=font_path, size=8.8) if font_path else None
    fp_small = font_manager.FontProperties(fname=font_path, size=7.8, weight="bold") if font_path else None

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
    highlights = spec.get("highlights", [])
    hl_map = {}
    for idx_h, h in enumerate(highlights):
        p_name = str(h.get("place", "")).strip()
        if p_name:
            h_copy = dict(h)
            if not h_copy.get("color"):
                h_copy["color"] = HIGHLIGHT_COLORS[idx_h % len(HIGHLIGHT_COLORS)]
            hl_map[p_name] = h_copy

    mentioned_dists = extract_mentioned_districts(raw_query)
    only_selected = bool(spec.get("only_selected", False)) or (len(mentioned_dists) >= 1)
    q_low = (raw_query or "").lower()
    force_rivers = bool(spec.get("show_rivers", False)) or any(w in q_low for w in ("નદી", "nadi", "river", "નર્મદા", "તાપી", "સાબરમતી", "ગંગા", "ભૌગોલિક", "bhaugolik"))

    if region == "local":
        search_en = str(spec.get("osm_query_en") or "Mehsana, Gujarat, India").strip()
        osm_geo = fetch_osm_real_boundary(search_en)
        all_x, all_y = [], []
        if osm_geo and osm_geo.get("features"):
            feat = osm_geo["features"][0]
            polys = _extract_polygons_from_geom(feat.get("geometry") or {})
            for poly in polys:
                map_ax.add_patch(patches.Polygon(poly, closed=True, facecolor="#FEF08A", edgecolor="#B91C1C", linewidth=2.2, alpha=0.95, joinstyle="round"))
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
        geo = load_real_geojson("gujarat")
        if geo and geo.get("features"):
            all_x, all_y = [], []
            for idx_d, feat in enumerate(geo["features"]):
                props = feat.get("properties") or {}
                raw_dist = str(props.get("NAME_2") or props.get("DISTRICT") or props.get("dtname") or props.get("district") or "").strip()
                guj_name, zone = DISTRICT_EN_TO_GUJ.get(raw_dist.lower(), (raw_dist, "central"))
                matched_hl = next((v for k, v in hl_map.items() if k in guj_name or guj_name in k or k.lower() in raw_dist.lower()), None)

                if only_selected and not matched_hl:
                    continue

                fc = matched_hl.get("color") if matched_hl else ("#F1F5F9" if hl_map else ZONE_COLORS.get(zone, "#E2E8F0"))
                ec = "#B91C1C" if matched_hl else "#334155"
                lw = 2.4 if matched_hl else 0.9

                polys = _extract_polygons_from_geom(feat.get("geometry") or {})
                biggest = max(polys, key=len) if polys else []
                for poly in polys:
                    map_ax.add_patch(patches.Polygon(poly, closed=True, facecolor=fc, edgecolor=ec, linewidth=lw, alpha=0.96, joinstyle="round"))
                    for px, py in poly:
                        all_x.append(px)
                        all_y.append(py)
                if biggest:
                    cx, cy = _polygon_centroid(biggest)
                    map_ax.text(cx, cy, guj_name, ha="center", va="center", color="#0F172A", fontproperties=fp_lbl if (only_selected or matched_hl) else fp_small)
                    if matched_hl and matched_hl.get("label") and matched_hl.get("label") != guj_name:
                        map_ax.text(cx, cy - 0.14, f"▲ {matched_hl.get('label')[:16]}", ha="center", va="center", color="#991B1B", fontproperties=fp_small)

            if force_rivers and all_x and all_y:
                for r_name, pts in GUJARAT_RIVERS_GEO:
                    xs, ys = zip(*pts)
                    if only_selected:
                        if not any((min(all_x) - 0.1 <= x <= max(all_x) + 0.1 and min(all_y) - 0.1 <= y <= max(all_y) + 0.1) for x, y in pts):
                            continue
                    map_ax.plot(xs, ys, color="#0284C7", linewidth=2.6)
                    map_ax.text(xs[1], ys[1] + 0.05, r_name, ha="center", va="center", color="#0369A1", fontproperties=fp_lbl)

            if all_x and all_y:
                dx = max((max(all_x) - min(all_x)) * 0.14, 0.22)
                dy = max((max(all_y) - min(all_y)) * 0.14, 0.22)
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

# ==============================================================================
# NCERT/GCERT TEXTBOOK DIAGRAM ENGINE (CURATED + REALISTIC VECTOR SVG)
# ==============================================================================
def get_curated_textbook_svg(query_text):
    q = (query_text or "").lower()
    if any(w in q for w in ("કંઠસ્થાન", "કંઠસ્થન", "સ્વરપેટી", "larynx", "laryx", "larnyx", "vocal")):
        return '''<svg width="740" height="450" viewBox="0 0 740 450" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="skinGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#DBEAFE"/>
      <stop offset="60%" stop-color="#93C5FD"/>
      <stop offset="100%" stop-color="#60A5FA"/>
    </linearGradient>
    <linearGradient id="cartilageGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#BFDBFE"/>
      <stop offset="50%" stop-color="#93C5FD"/>
      <stop offset="100%" stop-color="#3B82F6"/>
    </linearGradient>
    <linearGradient id="handGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#E2E8F0"/>
      <stop offset="100%" stop-color="#CBD5E1"/>
    </linearGradient>
  </defs>

  <rect width="740" height="450" rx="12" fill="#FFFFFF"/>
  <rect x="24" y="20" width="692" height="365" rx="6" fill="#F8FAFC" stroke="#475569" stroke-width="1.8"/>

  <!-- LEFT PANEL: HUMAN HEAD/NECK PROFILE + HAND TOUCHING LARYNX -->
  <g transform="translate(45, 32)">
    <path d="M 110,15 
             C 175,10 220,38 225,75 
             C 228,88 220,96 226,108 
             C 234,122 238,130 226,136 
             C 220,140 224,148 222,154 
             C 220,160 225,166 220,174 
             C 214,184 192,192 155,192 
             C 128,192 118,205 118,232 
             L 124,335 L 35,335 
             C 22,275 18,195 30,120 
             C 40,62 68,20 110,15 Z" 
          fill="url(#skinGrad)" stroke="#1E3A8A" stroke-width="2.2"/>

    <path d="M 65,330 L 92,225 C 96,208 112,204 114,220 L 92,330" fill="#60A5FA" stroke="#1E3A8A" stroke-width="1.8"/>
    <line x1="87" y1="242" x2="107" y2="246" stroke="#1E3A8A" stroke-width="1.8"/>
    <line x1="83" y1="258" x2="103" y2="262" stroke="#1E3A8A" stroke-width="1.8"/>
    <line x1="79" y1="274" x2="99" y2="278" stroke="#1E3A8A" stroke-width="1.8"/>
    <line x1="75" y1="290" x2="95" y2="294" stroke="#1E3A8A" stroke-width="1.8"/>
    <line x1="71" y1="306" x2="91" y2="310" stroke="#1E3A8A" stroke-width="1.8"/>

    <ellipse cx="116" cy="216" rx="7" ry="12" fill="#3B82F6" stroke="#0F172A" stroke-width="1.8"/>

    <path d="M 118,214 C 132,206 148,212 156,222 
             C 178,228 205,245 202,272 
             C 198,295 182,315 178,335 
             L 112,335 
             C 110,305 112,275 104,252 
             C 98,236 104,220 118,214 Z" 
          fill="url(#handGrad)" stroke="#1E293B" stroke-width="2"/>
    <path d="M 105,232 C 118,226 134,230 142,240" fill="none" stroke="#1E293B" stroke-width="1.8"/>
    <path d="M 135,236 C 148,248 146,272 136,288" fill="none" stroke="#1E293B" stroke-width="1.8"/>
    <path d="M 152,226 C 166,238 168,262 160,280" fill="none" stroke="#1E293B" stroke-width="1.6"/>

    <circle cx="117" cy="215" r="3.5" fill="#DC2626"/>
    <line x1="120" y1="215" x2="215" y2="215" stroke="#0F172A" stroke-width="1.8"/>
    <text x="222" y="220" font-size="17" font-weight="bold" fill="#0F172A">સ્વરપેટી</text>
  </g>

  <!-- RIGHT PANEL: ANATOMICAL LARYNX & VOCAL CORDS -->
  <g transform="translate(395, 55)">
    <path d="M 35,45 
             C 28,25 42,15 50,35 
             C 56,55 62,82 88,88 
             C 115,94 165,94 192,88 
             C 218,82 224,55 230,35 
             C 238,15 252,25 245,45 
             C 238,75 248,125 242,165 
             C 236,205 198,238 162,245 
             C 148,248 142,240 140,235 
             C 138,240 132,248 118,245 
             C 82,238 44,205 38,165 
             C 32,125 42,75 35,45 Z" 
          fill="url(#cartilageGrad)" stroke="#1E3A8A" stroke-width="2.4"/>

    <path d="M 88,88 C 102,55 178,55 192,88 C 175,102 105,102 88,88 Z" fill="#93C5FD" stroke="#1E3A8A" stroke-width="2"/>
    <path d="M 102,84 C 118,72 162,72 178,84" fill="#1E293B" stroke="#0F172A" stroke-width="1.5"/>

    <path d="M 85,112 C 95,98 185,98 195,112 C 202,145 182,195 140,212 C 98,195 78,145 85,112 Z" 
          fill="#EFF6FF" stroke="#1E3A8A" stroke-width="2"/>

    <path d="M 136,112 C 112,135 112,175 138,205 L 138,112 Z" fill="#60A5FA" stroke="#0F172A" stroke-width="2"/>
    <path d="M 144,112 C 168,135 168,175 142,205 L 142,112 Z" fill="#60A5FA" stroke="#0F172A" stroke-width="2"/>
    <line x1="140" y1="112" x2="140" y2="206" stroke="#0F172A" stroke-width="2.5"/>

    <line x1="65" y1="275" x2="124" y2="162" stroke="#0F172A" stroke-width="1.8"/>
    <polygon points="124,162 115,168 122,173" fill="#0F172A"/>

    <line x1="65" y1="275" x2="154" y2="168" stroke="#0F172A" stroke-width="1.8"/>
    <polygon points="154,168 145,172 151,178" fill="#0F172A"/>

    <text x="65" y="298" text-anchor="middle" font-size="17" font-weight="bold" fill="#0F172A">સ્વરતંતુઓ</text>
  </g>

  <text x="370" y="422" text-anchor="middle" font-size="18" font-weight="bold" fill="#0F172A">[આકૃતિ 10.1 : મનુષ્યમાં સ્વરપેટી (કંઠસ્થાન)]</text>
</svg>'''
    return None

async def generate_clean_drawing_async(query_text, api_keys, is_infographic_map=False):
    if not is_infographic_map:
        curated = get_curated_textbook_svg(query_text)
        if curated:
            return ("svg", curated)

    if not HAS_GENAI or not api_keys:
        return None

    if not is_infographic_map:
        svg_prompt = (
            f"Create a detailed, realistic Indian NCERT / GCERT Class 3-8 Science textbook SVG diagram (width='740' height='450' viewBox='0 0 740 450') for: {query_text}.\n"
            "STRICT RULES:\n"
            "1. Output ONLY raw <svg width='740' height='450' viewBox='0 0 740 450' xmlns='http://www.w3.org/2000/svg'>...</svg>.\n"
            "2. White background <rect width='740' height='450' rx='12' fill='#FFFFFF'/> and inner border <rect x='24' y='20' width='692' height='365' rx='6' fill='#F8FAFC' stroke='#475569' stroke-width='1.8'/>.\n"
            "3. Draw realistic anatomical/scientific curves using smooth cubic Bezier <path d='... C ...'> with <linearGradient> shading — NEVER draw crude boxes or plain circles.\n"
            "4. Add pointer lines with arrowheads and clear Gujarati part labels (font-size='16' font-weight='bold' fill='#0F172A') strictly inside x=45..690, y=45..370.\n"
            "5. Put the textbook caption at the bottom: <text x='370' y='422' text-anchor='middle' font-size='18' font-weight='bold' fill='#0F172A'>[આકૃતિ : ...]</text>."
        )
        for key in api_keys:
            client = get_cached_client(key)
            models_list = await asyncio.to_thread(get_working_models_for_key, key, "gemini-2.5-flash")
            for mod in models_list:
                try:
                    res = await client.aio.models.generate_content(model=mod, contents=[svg_prompt])
                    raw = (res.text or "").strip()
                    m = re.search(r"(<svg[\s\S]*?</svg>)", raw, flags=re.IGNORECASE)
                    if m:
                        return ("svg", m.group(1))
                except Exception:
                    pass

    img_prompt = (
        f"Educational Indian school textbook dual map infographic for: {query_text}."
        if is_infographic_map else
        f"Clean educational Indian NCERT school textbook diagram with clear labels for: {query_text}."
    )
    for key in api_keys:
        client = get_cached_client(key)
        for nb_model in DEFAULT_IMAGE_MODELS:
            try:
                res = await client.aio.models.generate_content(
                    model=nb_model,
                    contents=[img_prompt],
                    config=types.GenerateContentConfig(response_modalities=["IMAGE"])
                )
                for cand in getattr(res, "candidates", []) or []:
                    for part in getattr(cand.content, "parts", []) or []:
                        if getattr(part, "inline_data", None) and getattr(part.inline_data, "data", None):
                            return ("png", part.inline_data.data)
            except Exception:
                pass
    return None

def build_math_fraction_svg(query_text):
    q = (query_text or "").translate(str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")).lower()
    if "ત્રિકોણ" in q or "triangle" in q or "trikon" in q:
        return '<svg width="520" height="290" viewBox="0 0 520 290" xmlns="http://www.w3.org/2000/svg"><rect width="520" height="290" rx="12" fill="#FFFFFF"/><text x="260" y="28" text-anchor="middle" font-size="17" font-weight="bold" fill="#1E3A8A">📐 ત્રિકોણની આકૃતિ અને તેના અંગો</text><polygon points="260,60 130,235 390,235" fill="#DBEAFE" stroke="#1D4ED8" stroke-width="3"/><text x="260" y="48" text-anchor="middle" font-size="14" font-weight="bold" fill="#DC2626">શિરોબિંદુ A</text><text x="105" y="258" text-anchor="middle" font-size="14" font-weight="bold" fill="#DC2626">શિરોબિંદુ B</text><text x="415" y="258" text-anchor="middle" font-size="14" font-weight="bold" fill="#DC2626">શિરોબિંદુ C</text><text x="260" y="258" text-anchor="middle" font-size="13" font-weight="bold" fill="#0F172A">પાયો BC (૩ બાજુ, ૩ ખૂણા)</text></svg>'
    if "ચોરસ" in q or "લંબચોરસ" in q or "square" in q or "rectangle" in q or "choras" in q:
        is_rect = "લંબચોરસ" in q or "rectangle" in q
        w = 240 if is_rect else 160
        x0 = 260 - w // 2
        return f'<svg width="520" height="290" viewBox="0 0 520 290" xmlns="http://www.w3.org/2000/svg"><rect width="520" height="290" rx="12" fill="#FFFFFF"/><text x="260" y="28" text-anchor="middle" font-size="17" font-weight="bold" fill="#1E3A8A">📐 {"લંબચોરસ" if is_rect else "ચોરસ"} ની આકૃતિ</text><rect x="{x0}" y="68" width="{w}" height="155" fill="#DCFCE7" stroke="#15803D" stroke-width="3"/><text x="260" y="255" text-anchor="middle" font-size="13" font-weight="bold" fill="#15803D">દરેક ખૂણો ૯૦° (કાટખૂણો)</text></svg>'
    return None

# --- DETECTION HELPERS ---
_GUJ_DIGIT_MAP = str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")
_SUBJECT_LABELS = {"gujarati": "ગુજરાતી", "sanskrit": "સંસ્કૃત", "math": "ગણિત", "science": "વિજ્ઞાન", "social_science": "સામાજિક વિજ્ઞાન", "environment": "પર્યાવરણ", "english": "અંગ્રેજી", "hindi": "હિન્દી"}
_EXPLICIT_SUBJECTS = {
    "social_science": ["સામાજિક વિજ્ઞાન", "સામાજિક", "social", "ઇતિહાસ", "ભૂગોળ", "નકશો", "નક્શો", "નકશા", "નકશાપૂર્તિ", "naksho", "naksha", "જિલ્લા", "તાલુકા", "ગુજરાત", "મગધ", "કિલ્લો", "કિલ્લા", "પ્રદેશ", "ઉદ્યોગ", "ખેત ઉત્પાદન", "પાક"],
    "math": ["ગણિત", "math", "ભૂમિતિ", "અપૂર્ણાંક", "વર્તુળ", "ત્રિકોણ", "ચોરસ"],
    "science": ["વિજ્ઞાન", "science", "પ્રકાશસંશ્લેષણ", "કોષ", "વિદ્યુત", "ચુંબક"],
    "environment": ["પર્યાવરણ", "આસપાસ", "evs"],
    "gujarati": ["ગુજરાતી", "gujarati", "કલશોર", "કેકારવ", "કુહૂ", "પલાશ"],
    "sanskrit": ["સંસ્કૃત", "sanskrit"],
    "english": ["અંગ્રેજી", "english"],
    "hindi": ["હિન્દી", "hindi"],
}

def wants_map(text):
    t = (text or "").lower()
    return any(kw in t for kw in (
        "નકશો", "નક્શો", "નકશા", "નક્શા", "નકશાપૂર્તિ", "naksho", "naksha", "map",
        "સંજ્ઞા વડે", "નકશામાં દર્શાવો", "કિલ્લા", "મગધ", "પ્રદેશો",
        "રાજકીય", "ભૌગોલિક", "ગામનો", "gamno", "gamda", "ખેત ઉત્પાદન", "ઉદ્યોગો", "નદીઓ", "મતદાર", "વસ્તી ગણતરી", "blo"
    ))

def wants_taluka_dual_infographic_map(text):
    t = (text or "").lower()
    if len(extract_mentioned_districts(text)) >= 1:
        return False
    is_taluka_or_village = any(w in t for w in ("તાલુકો", "તાલુકા", "taluko", "taluka", "ગામ", "gam"))
    return wants_map(t) and is_taluka_or_village

def wants_any_drawing_or_diagram(text):
    t = (text or "").lower()
    return any(kw in t for kw in (
        "આકૃતિ", "akruti", "aakruti", "નામનિર્દેશ", "ચિત્ર", "chitra", "chira", "chitran",
        "દોરો", "દોરી", "doro", "dori", "બનાવો", "banavo", "banavi",
        "diagram", "draw", "drawing", "sketch", "image", "picture", "photo", "painting",
        "બાળક", "balak", "ગાય", "gay", "cow", "ફૂલ", "ful", "પ્રાણી", "પક્ષી", "વાંદરો", "વાંદરા", "monkey", "કોષ", "પ્રકાશસંશ્લેષણ", "સફરજન", "કેળું", "દ્રાક્ષ", "કંઠસ્થાન", "કંઠસ્થન", "larynx", "સ્વરપેટી", "હૃદય", "ફેફસાં"
    ))

def needs_textbook_vision(text):
    t = (text or "").lower()
    return any(k in t for k in ("પાઠ", "પ્રકરણ", "સ્વાધ્યાય", "સારાંશ", "કવિતા", "વાર્તા", "પુસ્તક", "chapter", "lesson", "exercise", "mcq"))

def extract_grade(text):
    t = (text or "").translate(_GUJ_DIGIT_MAP).lower()
    for p in [r"ધોરણ\s*[-:.]?\s*([3-8])", r"ધો\.?\s*[-:.]?\s*([3-8])", r"std\.?\s*[-:.]?\s*([3-8])", r"grade\s*[-:.]?\s*([3-8])"]:
        if m := re.search(p, t):
            return int(m.group(1))
    return None

def extract_subject(text):
    t = (text or "").lower()
    for code, keywords in _EXPLICIT_SUBJECTS.items():
        if any(kw.lower() in t for kw in keywords):
            return code
    return None

def resolve_grade_subject_and_pdfs(current_query, syllabus):
    grade, subject = extract_grade(current_query), extract_subject(current_query)
    if not grade or not subject:
        return grade, subject, []
    matched = []
    for _label, info in ((syllabus.get(f"ધોરણ {grade}") or {}).get("subjects", {})).items():
        if info.get("code") == subject:
            for p in info.get("local_pdfs") or []:
                path = p.replace("\\", "/")
                if os.path.exists(path) and path not in matched:
                    matched.append(path)
            break
    return grade, subject, matched[:1]

def build_vision_pdf_parts(pdf_path):
    try:
        abspath = os.path.abspath(pdf_path)
        import fitz
        parts = []
        with fitz.open(abspath) as doc:
            for idx in range(min(6, len(doc))):
                b = doc[idx].get_pixmap(dpi=100, alpha=False).tobytes("jpeg", jpg_quality=70)
                parts.append(types.Part.from_bytes(data=b, mime_type="image/jpeg"))
        return parts
    except Exception:
        return []

def detect_default_map_spec(query_text):
    q = (query_text or "").lower()
    dist_list = extract_mentioned_districts(query_text)
    if dist_list:
        hls = [{"place": d, "label": d, "color": HIGHLIGHT_COLORS[i % len(HIGHLIGHT_COLORS)]} for i, d in enumerate(dist_list)]
        return {
            "region": "gujarat",
            "only_selected": True,
            "header_top": "સામાજિક વિજ્ઞાન - નકશા પૂર્તિ",
            "title": f"{', '.join(dist_list)} જિલ્લાનો નકશો",
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
                    spec["highlights"] = [{"place": d, "label": d, "color": HIGHLIGHT_COLORS[i % len(HIGHLIGHT_COLORS)]} for i, d in enumerate(mentioned_dists)]
                map_img_bytes = render_textbook_map_png(spec, raw_query=raw_query)
            except Exception:
                map_img_bytes = render_textbook_map_png(detect_default_map_spec(raw_query), raw_query=raw_query)
        clean_text = re.sub(r"```map_json[\s\S]*?```", "", clean_text)
    if is_map_query and not map_img_bytes:
        map_img_bytes = render_textbook_map_png(detect_default_map_spec(raw_query), raw_query=raw_query)
    return map_img_bytes, clean_text

def get_quick_actions():
    return [
        cl.Action(name="quick_summary", payload={"type": "summary"}, label="📖 સારાંશ"),
        cl.Action(name="quick_exercise", payload={"type": "exercise"}, label="📝 સ્વાધ્યાય"),
        cl.Action(name="quick_mcq", payload={"type": "mcq"}, label="🎯 MCQ ટેસ્ટ"),
        cl.Action(name="quick_example", payload={"type": "easy_example"}, label="💡 ઉદાહરણ"),
        cl.Action(name="download_pdf", payload={"type": "pdf"}, label="📄 PDF નોટ્સ ડાઉનલોડ"),
    ]

def ensure_thread_files_dir():
    os.makedirs(".files", exist_ok=True)
    tid = cl.context.session.thread_id if getattr(cl.context, "session", None) else None
    if tid:
        os.makedirs(os.path.join(".files", tid), exist_ok=True)

async def prewarm_geo_cache():
    await asyncio.to_thread(load_real_geojson, "gujarat")
    await asyncio.to_thread(load_real_geojson, "india")

# ==============================================================================
# CHAINLIT HOOKS
# ==============================================================================
@cl.on_chat_start
async def on_chat_start():
    ensure_thread_files_dir()
    asyncio.create_task(prewarm_geo_cache())
    cl.user_session.set("messages", [])
    cl.user_session.set("model_choice", ACTIVE_MODELS[0])

    settings = await cl.ChatSettings(
        [
            Select(
                id="model_choice",
                label="🤖 AI મોડેલ પસંદ કરો:",
                values=ACTIVE_MODELS,
                initial_index=0,
            )
        ]
    ).send()
    if settings and settings.get("model_choice"):
        cl.user_session.set("model_choice", settings["model_choice"])

    await cl.Message(
        content="📚 **Standard 3 to 8 Smart AI Palaj Student Helper** તૈયાર છે! નીચે પ્રશ્ન લખો, માઈક વડે બોલો અથવા ફોટો/PDF મોકલો.",
        actions=get_quick_actions()
    ).send()

@cl.on_chat_resume
async def on_chat_resume(thread):
    ensure_thread_files_dir()
    asyncio.create_task(prewarm_geo_cache())
    restored = []
    for step in thread.get("steps", []):
        stype = step.get("type")
        if stype == "user_message" and step.get("output"):
            restored.append({"role": "user", "content": step["output"]})
        elif stype == "assistant_message" and step.get("output"):
            restored.append({"role": "assistant", "content": step["output"]})
    cl.user_session.set("messages", restored)
    cl.user_session.set("model_choice", ACTIVE_MODELS[0])

@cl.on_settings_update
async def on_settings_update(settings):
    if settings and settings.get("model_choice"):
        cl.user_session.set("model_choice", settings["model_choice"])

@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk):
    if chunk.isStart:
        cl.user_session.set("audio_buffer", io.BytesIO())
        cl.user_session.set("audio_mime", chunk.mimeType or "audio/webm")
    buf = cl.user_session.get("audio_buffer")
    if buf is not None:
        buf.write(chunk.data)

@cl.on_audio_end
async def on_audio_end():
    buf = cl.user_session.get("audio_buffer")
    mime = cl.user_session.get("audio_mime", "audio/webm")
    if not buf:
        return
    audio_bytes = buf.getvalue()
    cl.user_session.set("audio_buffer", None)

    api_keys = get_api_keys()
    model_choice = cl.user_session.get("model_choice", ACTIVE_MODELS[0])
    spoken, err = await transcribe_gujarati_bytes_async(audio_bytes, mime, api_keys, model_choice)
    if spoken:
        await cl.Message(content=f"🎤 **તમે બોલ્યા:** {spoken}", author="User").send()
        await process_teacher_query(spoken, [])
    elif err:
        await cl.Message(content=f"⚠️ {err}").send()

@cl.action_callback("quick_summary")
@cl.action_callback("quick_exercise")
@cl.action_callback("quick_mcq")
@cl.action_callback("quick_example")
async def on_quick_action(action: cl.Action):
    prompts = {
        "summary": "છેલ્લી ચર્ચા મુજબના પાઠનો મુદ્દાસર સારાંશ આપો.",
        "exercise": "છેલ્લી ચર્ચા મુજબના પાઠના સ્વાધ્યાયના પ્રશ્નો અને જવાબો આપો.",
        "mcq": "છેલ્લી ચર્ચા મુજબ ૫ MCQ બનાવો. ફોર્મેટ:\nપ્રશ્ન 1: પ્રશ્ન?\nA. ...\nB. ...\nC. ...\nD. ...\nસાચો જવાબ: B\nસમજૂતી: ...",
        "easy_example": "છેલ્લી ચર્ચા મુજબના વિષયના સરળ ઉદાહરણો આપો.",
    }
    q = prompts.get(action.payload.get("type", "summary"))
    await cl.Message(content=q, author="User").send()
    await process_teacher_query(q, [])

@cl.action_callback("download_pdf")
async def on_download_pdf(action: cl.Action):
    ensure_thread_files_dir()
    msgs = cl.user_session.get("messages") or []
    if not msgs:
        await cl.Message(content="⚠️ PDF બનાવવા માટે પહેલા કોઈ પ્રશ્ન પૂછો.").send()
        return
    try:
        pdf_bytes = await asyncio.to_thread(build_pdf_bytes, msgs)
        await cl.Message(
            content="📄 તમારી ક્લાસરૂમ નોટ્સની PDF તૈયાર છે — નીચેની ફાઈલ પર ક્લિક કરીને ડાઉનલોડ કરો:",
            elements=[cl.File(name="palaj_classroom_notes.pdf", content=pdf_bytes, display="inline")]
        ).send()
    except Exception as e:
        await cl.Message(content=f"⚠️ PDF બનાવવામાં ભૂલ આવી: {e}").send()

@cl.on_message
async def on_message(message: cl.Message):
    ensure_thread_files_dir()
    clean_q = (message.content or "").strip()
    elements = message.elements or []
    if not clean_q and not elements:
        return
    if not clean_q:
        clean_q = "[કેમેરા / ફાઈલ સંલગ્ન છે]"
    await process_teacher_query(clean_q, elements)

async def process_teacher_query(clean_q: str, elements: list):
    ensure_thread_files_dir()
    api_keys = get_api_keys()
    model_choice = cl.user_session.get("model_choice", ACTIVE_MODELS[0])
    messages = cl.user_session.get("messages") or []
    messages.append({"role": "user", "content": clean_q})
    cl.user_session.set("messages", messages)

    if not HAS_GENAI or not api_keys:
        await cl.Message(content="⚠️ Environment Variables માં `GEMINI_API_KEY` દાખલ કરો.").send()
        return

    user_att_parts = []
    for el in elements:
        try:
            if getattr(el, "path", None) and os.path.exists(el.path):
                with open(el.path, "rb") as f:
                    fb = f.read()
            else:
                fb = getattr(el, "content", None)
            if fb:
                mime = getattr(el, "mime", "") or ""
                if "pdf" in mime or str(getattr(el, "name", "")).lower().endswith(".pdf"):
                    user_att_parts.append(types.Part.from_bytes(data=fb, mime_type="application/pdf"))
                else:
                    user_att_parts.append(Image.open(io.BytesIO(fb)))
        except Exception:
            pass

    syllabus_data = load_syllabus()
    grade, subject, local_pdf_paths = resolve_grade_subject_and_pdfs(clean_q, syllabus_data)
    is_map_q = wants_map(clean_q)
    is_taluka_dual = wants_taluka_dual_infographic_map(clean_q)
    math_svg_code = build_math_fraction_svg(clean_q) if not is_map_q else None
    is_drawing_q = wants_any_drawing_or_diagram(clean_q) and not is_map_q and not math_svg_code

    recent_hist = "\n".join(f"{'વિદ્યાર્થી' if m['role']=='user' else 'શિક્ષક'}: {m['content']}" for m in messages[:-1][-3:])
    book_page_parts = await asyncio.to_thread(build_vision_pdf_parts, local_pdf_paths[0]) if (local_pdf_paths and needs_textbook_vision(clean_q)) else []

    img_task = None
    if is_drawing_q:
        img_task = asyncio.create_task(generate_clean_drawing_async(clean_q, api_keys, is_infographic_map=False))
    elif is_taluka_dual:
        img_task = asyncio.create_task(generate_clean_drawing_async(clean_q, api_keys, is_infographic_map=True))

    visual_instruction = ""
    if is_map_q and not is_taluka_dual:
        visual_instruction = (
            "\n**મહત્વની સૂચના:** પ્રશ્ન મુજબ સાચો ```map_json બ્લોક ફરજિયાત આપો:\n"
            "- જો **ભારતના રાજ્યો** પૂછ્યા હોય (જેમ કે ગુજરાત, રાજસ્થાન, દિલ્હી), તો `\"region\": \"india\"` રાખો અને `\"highlights\"` માં દરેક રાજ્ય માટે અલગ `color` આપો.\n"
            "- જો **ગુજરાતના જિલ્લા** પૂછ્યા હોય, તો `\"region\": \"gujarat\"` રાખો.\n"
            "- જો **વિશ્વ** પૂછ્યું હોય, તો `\"region\": \"world\"` રાખો.\n"
            "```map_json\n"
            '{"region": "india", "only_selected": false, "header_top": "સામાજિક વિજ્ઞાન - નકશા પૂર્તિ", "title": "ભારતનો રાજકીય નકશો", "show_rivers": false, "highlights": [{"place": "ગુજરાત", "label": "ગુજરાત", "color": "#FACC15"}, {"place": "રાજસ્થાન", "label": "રાજસ્થાન", "color": "#38BDF8"}, {"place": "દિલ્હી", "label": "દિલ્હી", "color": "#F472B6"}], "legend": [{"color": "#FACC15", "label": "ગુજરાત"}, {"color": "#38BDF8", "label": "રાજસ્થાન"}, {"color": "#F472B6", "label": "દિલ્હી"}]}\n'
            "```\nઅને નીચે પ્રશ્નમાં પૂછેલા સ્થળોની મુદ્દાસર સમજૂતી આપો."
        )
    elif is_taluka_dual:
        visual_instruction = "\n**મહત્વની સૂચના:** ઉપર રાજકીય (વહીવટી) અને ભૌગોલિક નકશો દર્શાવ્યો છે. નીચે તે તાલુકા/વિસ્તારની ભૌગોલિક અને વહીવટી માહિતી મુદ્દાસર ગુજરાતીમાં આપો."
    elif is_drawing_q:
        visual_instruction = "\n**મહત્વની સૂચના:** ઉપર પાઠ્યપુસ્તકની આકૃતિ આપમેળે દોરાઈને દેખાશે, તેથી ટેક્સ્ટમાં dot/dash (`---`, `|||`) વાળી ASCII આકૃતિ ન બનાવશો — ફક્ત નીચે મુદ્દાસર સમજૂતી અને કાર્ય ગુજરાતીમાં આપો."

    sys_prompt = f"તમે ધોરણ 3 થી 8 ના વિદ્યાર્થીઓ અને શિક્ષકો માટેના ઝડપી અને નિષ્ણાત AI સહાયક છો. જવાબ શુદ્ધ ગુજરાતીમાં, ત્વરિત અને મુદ્દાસર આપો.{visual_instruction}"
    prompt_text = f"{sys_prompt}\n\n{recent_hist}\nપ્રશ્ન: {clean_q}"

    msg = cl.Message(content="")
    await msg.send()

    answer_text, success, last_err = "", False, None
    for key in api_keys:
        client = get_cached_client(key)
        models_list = await asyncio.to_thread(get_working_models_for_key, key, model_choice)
        for mod in models_list:
            try:
                temp = ""
                stream = await client.aio.models.generate_content_stream(
                    model=mod,
                    contents=book_page_parts + user_att_parts + [prompt_text]
                )
                async for chunk in stream:
                    if chunk.text:
                        temp += chunk.text
                        if "```map_json" not in temp and "<svg" not in temp.lower():
                            await msg.stream_token(chunk.text)
                if temp.strip():
                    answer_text, success = temp, True
                    break
            except Exception as e:
                last_err = e
                if any(x in str(e) for x in ("429", "RESOURCE_EXHAUSTED", "API_KEY_INVALID")):
                    break
        if success:
            break

    if not success:
        msg.content = f"❌ {format_friendly_error(last_err)}"
        await msg.update()
        return

    raw_drawing = await img_task if img_task else None
    generated_svg_code = raw_drawing[1] if (isinstance(raw_drawing, tuple) and raw_drawing[0] == "svg") else None
    generated_img_bytes = raw_drawing[1] if (isinstance(raw_drawing, tuple) and raw_drawing[0] == "png") else (raw_drawing if isinstance(raw_drawing, bytes) else None)

    computed_map_bytes, clean_text = (None, answer_text)
    if is_map_q and not generated_img_bytes and not generated_svg_code:
        computed_map_bytes, clean_text = await asyncio.to_thread(
            extract_or_build_map_bytes, answer_text, True, clean_q
        )
    else:
        clean_text = re.sub(r"```map_json[\s\S]*?```", "", answer_text)

    msg_elements = []
    if generated_svg_code:
        msg_elements.append(make_svg_or_png_element(generated_svg_code, "palaj_diagram"))
    elif generated_img_bytes or computed_map_bytes:
        msg_elements.append(cl.Image(name="palaj_visual.png", content=(generated_img_bytes or computed_map_bytes), display="inline"))
    elif math_svg_code:
        msg_elements.append(make_svg_or_png_element(math_svg_code, "math_diagram"))

    badge = ""
    if is_map_q:
        badge = "🗺️ *પાઠ્યપુસ્તક શૈલીનો રાજકીય અને ભૌગોલિક નકશો*\n\n"
    elif grade and subject and local_pdf_paths:
        badge = f"📖 *ધોરણ {grade} | {_SUBJECT_LABELS.get(subject, subject)}*\n\n"

    msg.content = f"{badge}{clean_text.strip()}"
    msg.elements = msg_elements
    msg.actions = get_quick_actions()
    await msg.update()

    messages.append({
        "role": "assistant",
        "content": answer_text,
        "map_bytes": computed_map_bytes,
        "image_bytes": generated_img_bytes,
        "math_svg": generated_svg_code or math_svg_code,
    })
    cl.user_session.set("messages", messages)
