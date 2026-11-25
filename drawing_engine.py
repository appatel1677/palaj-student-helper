import re
import asyncio
import urllib.request
import urllib.parse
from google.genai import types

NANO_BANANA_MODELS = [
    "gemini-2.5-flash-image",
    "gemini-2.0-flash-exp-image-generation",
]

def wants_any_drawing_or_diagram(text):
    t = (text or "").lower()
    return any(kw in t for kw in (
        "આકૃતિ", "akruti", "aakruti", "નામનિર્દેશ", "ચિત્ર", "chitra", "chira", "chitran",
        "દોરો", "દોરી", "doro", "dori", "બનાવો", "banavo", "banavi",
        "diagram", "draw", "drawing", "sketch", "image", "picture", "photo", "painting", "nano banana",
        "બાળક", "balak", "ગાય", "gay", "cow", "વાછરડું", "વાછરડા", "ફૂલ", "ful", "પ્રાણી", "પક્ષી",
        "વાંદરો", "વાંદરા", "monkey", "કોષ", "પ્રકાશસંશ્લેષણ", "સફરજન", "કેળું", "દ્રાક્ષ",
        "કંઠસ્થાન", "કંઠસ્થન", "larynx", "સ્વરપેટી", "હૃદય", "ફેફસાં", "મંદિર", "સૂર્ય", "વૃક્ષ", "ઝાડ"
    ))

def is_scientific_diagram_request(query_text):
    q = (query_text or "").lower()
    return any(w in q for w in (
        "આકૃતિ", "akruti", "aakruti", "નામનિર્દેશ", "diagram",
        "કંઠસ્થાન", "કંઠસ્થન", "સ્વરપેટી", "larynx", "કોષ", "પ્રકાશસંશ્લેષણ",
        "વિદ્યુત", "પરિપથ", "ચુંબક", "હૃદય", "ફેફસાં", "પાચનતંત્ર", "શ્વસનતંત્ર", "પરાગનયન", "પુષ્પ"
    ))

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

def get_curated_textbook_svg(query_text):
    q = (query_text or "").lower()
    if any(w in q for w in ("કંઠસ્થાન", "કંઠસ્થન", "સ્વરપેટી", "larynx", "laryx", "larnyx", "vocal")):
        return '''<svg width="740" height="450" viewBox="0 0 740 450" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="skinGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#DBEAFE"/><stop offset="60%" stop-color="#93C5FD"/><stop offset="100%" stop-color="#60A5FA"/>
    </linearGradient>
    <linearGradient id="cartilageGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#BFDBFE"/><stop offset="50%" stop-color="#93C5FD"/><stop offset="100%" stop-color="#3B82F6"/>
    </linearGradient>
    <linearGradient id="handGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#E2E8F0"/><stop offset="100%" stop-color="#CBD5E1"/>
    </linearGradient>
  </defs>
  <rect width="740" height="450" rx="12" fill="#FFFFFF"/>
  <rect x="24" y="20" width="692" height="365" rx="6" fill="#F8FAFC" stroke="#475569" stroke-width="1.8"/>
  <g transform="translate(45, 32)">
    <path d="M 110,15 C 175,10 220,38 225,75 C 228,88 220,96 226,108 C 234,122 238,130 226,136 C 220,140 224,148 222,154 C 220,160 225,166 220,174 C 214,184 192,192 155,192 C 128,192 118,205 118,232 L 124,335 L 35,335 C 22,275 18,195 30,120 C 40,62 68,20 110,15 Z" fill="url(#skinGrad)" stroke="#1E3A8A" stroke-width="2.2"/>
    <path d="M 65,330 L 92,225 C 96,208 112,204 114,220 L 92,330" fill="#60A5FA" stroke="#1E3A8A" stroke-width="1.8"/>
    <ellipse cx="116" cy="216" rx="7" ry="12" fill="#3B82F6" stroke="#0F172A" stroke-width="1.8"/>
    <path d="M 118,214 C 132,206 148,212 156,222 C 178,228 205,245 202,272 C 198,295 182,315 178,335 L 112,335 C 110,305 112,275 104,252 C 98,236 104,220 118,214 Z" fill="url(#handGrad)" stroke="#1E293B" stroke-width="2"/>
    <circle cx="117" cy="215" r="3.5" fill="#DC2626"/>
    <line x1="120" y1="215" x2="215" y2="215" stroke="#0F172A" stroke-width="1.8"/>
    <text x="222" y="220" font-size="17" font-weight="bold" fill="#0F172A">સ્વરપેટી</text>
  </g>
  <g transform="translate(395, 55)">
    <path d="M 35,45 C 28,25 42,15 50,35 C 56,55 62,82 88,88 C 115,94 165,94 192,88 C 218,82 224,55 230,35 C 238,15 252,25 245,45 C 238,75 248,125 242,165 C 236,205 198,238 162,245 C 148,248 142,240 140,235 C 138,240 132,248 118,245 C 82,238 44,205 38,165 C 32,125 42,75 35,45 Z" fill="url(#cartilageGrad)" stroke="#1E3A8A" stroke-width="2.4"/>
    <path d="M 85,112 C 95,98 185,98 195,112 C 202,145 182,195 140,212 C 98,195 78,145 85,112 Z" fill="#EFF6FF" stroke="#1E3A8A" stroke-width="2"/>
    <path d="M 136,112 C 112,135 112,175 138,205 L 138,112 Z" fill="#60A5FA" stroke="#0F172A" stroke-width="2"/>
    <path d="M 144,112 C 168,135 168,175 142,205 L 142,112 Z" fill="#60A5FA" stroke="#0F172A" stroke-width="2"/>
    <line x1="65" y1="275" x2="124" y2="162" stroke="#0F172A" stroke-width="1.8"/>
    <line x1="65" y1="275" x2="154" y2="168" stroke="#0F172A" stroke-width="1.8"/>
    <text x="65" y="298" text-anchor="middle" font-size="17" font-weight="bold" fill="#0F172A">સ્વરતંતુઓ</text>
  </g>
  <text x="370" y="422" text-anchor="middle" font-size="18" font-weight="bold" fill="#0F172A">[આકૃતિ 10.1 : મનુષ્યમાં સ્વરપેટી (કંઠસ્થાન)]</text>
</svg>'''
    return None

def _fetch_free_ai_illustration_sync(en_prompt):
    """ફ્રી API Key પર Nano Banana ન ચાલે ત્યારે Pollinations AI પરથી રંગીન શૈક્ષણિક ચિત્ર લાવે છે."""
    try:
        clean_p = urllib.parse.quote(f"colorful Indian elementary school textbook illustration of {en_prompt}, cute, bright, clean background, no text")
        url = f"https://image.pollinations.ai/prompt/{clean_p}?width=768&height=512&nologo=true&seed=42"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=18) as resp:
            data = resp.read()
            if data and len(data) > 4000:
                return data
    except Exception:
        pass
    return None

async def generate_nano_banana_image_async(query_text, api_keys, get_client_fn, get_models_fn):
    en_prompt = query_text
    if api_keys:
        client = get_client_fn(api_keys[0])
        models_list = await asyncio.to_thread(get_models_fn, api_keys[0], "gemini-2.5-flash")
        for mod in models_list:
            try:
                tr = await client.aio.models.generate_content(
                    model=mod,
                    contents=[f"Translate this drawing request into a short, vivid English image prompt (max 18 words, output ONLY English text): {query_text}"]
                )
                if tr.text and tr.text.strip():
                    en_prompt = tr.text.strip()
                    break
            except Exception:
                pass

    # ૧. પહેલા Nano Banana અજમાવો
    if api_keys:
        prompt = f"Create a clean, colorful, child-friendly Indian school textbook illustration for: {en_prompt}. Bright, clear, educational, zero text."
        for key in api_keys:
            client = get_client_fn(key)
            for img_mod in NANO_BANANA_MODELS:
                try:
                    res = await client.aio.models.generate_content(
                        model=img_mod,
                        contents=[prompt],
                        config=types.GenerateContentConfig(response_modalities=["IMAGE"])
                    )
                    for cand in (res.candidates or []):
                        for part in (cand.content.parts or []):
                            if getattr(part, "inline_data", None) and part.inline_data.data:
                                return ("png", part.inline_data.data)
                except Exception:
                    continue

    # ૨. ફ્રી API Key પર Nano Banana ન ચાલે તો Free AI Image Generator પરથી રંગીન ચિત્ર લાવો
    free_png = await asyncio.to_thread(_fetch_free_ai_illustration_sync, en_prompt)
    if free_png:
        return ("png", free_png)

    return None

async def generate_clean_drawing_async(query_text, api_keys, get_client_fn, get_models_fn):
    if is_scientific_diagram_request(query_text):
        curated = get_curated_textbook_svg(query_text)
        if curated:
            return ("svg", curated)

        if api_keys:
            svg_prompt = (
                f"Create a detailed, realistic Indian NCERT / GCERT Class 3-8 Science textbook SVG diagram (width='740' height='450' viewBox='0 0 740 450') for: {query_text}.\n"
                "STRICT RULES:\n"
                "1. Output ONLY raw <svg width='740' height='450' viewBox='0 0 740 450' xmlns='http://www.w3.org/2000/svg'>...</svg>.\n"
                "2. White background <rect width='740' height='450' rx='12' fill='#FFFFFF'/> and inner border <rect x='24' y='20' width='692' height='365' rx='6' fill='#F8FAFC' stroke='#475569' stroke-width='1.8'/>.\n"
                "3. Draw realistic anatomical/scientific curves using smooth cubic Bezier <path d='... C ...'> with <linearGradient> shading.\n"
                "4. Add pointer lines with arrowheads and clear Gujarati part labels (font-size='16' font-weight='bold' fill='#0F172A') strictly inside x=45..690, y=45..370.\n"
                "5. Put the textbook caption at the bottom: <text x='370' y='422' text-anchor='middle' font-size='18' font-weight='bold' fill='#0F172A'>[આકૃતિ : ...]</text>."
            )
            for key in api_keys:
                client = get_client_fn(key)
                models_list = await asyncio.to_thread(get_models_fn, key, "gemini-2.5-flash")
                for mod in models_list:
                    try:
                        res = await client.aio.models.generate_content(model=mod, contents=[svg_prompt])
                        raw = (res.text or "").strip()
                        m = re.search(r"(<svg[\s\S]*?</svg>)", raw, flags=re.IGNORECASE)
                        if m:
                            return ("svg", m.group(1))
                    except Exception:
                        pass

    nb_img = await generate_nano_banana_image_async(query_text, api_keys, get_client_fn, get_models_fn)
    if nb_img:
        return nb_img

    return None
