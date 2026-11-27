import os
import re
import io
import json
import asyncio
from dotenv import load_dotenv
load_dotenv()

os.makedirs(".files", exist_ok=True)
os.makedirs("geo_cache", exist_ok=True)

import chainlit as cl
from chainlit.input_widget import Select
from PIL import Image
from google import genai
from google.genai import types

# અલગ-અલગ મોડ્યુલ્સ ઈમ્પોર્ટ કરો
from db_and_pdf import (
    init_chainlit_sqlite_db,
    build_sqlalchemy_data_layer,
    get_pdf_font,
    make_svg_element,
    build_pdf_bytes,
)
from graph_engine import wants_graph, extract_or_build_graph_bytes
from map_engine import wants_map, load_real_geojson, extract_or_build_map_bytes
from rojnishi_engine import wants_rojnishi, load_teacher_reference_context, extract_or_build_rojnishi_docx

from drawing_engine import (
    wants_any_drawing_or_diagram,
    build_math_fraction_svg,
    generate_clean_drawing_async,
)

init_chainlit_sqlite_db()

@cl.data_layer
def get_data_layer():
    return build_sqlalchemy_data_layer()

@cl.password_auth_callback
def auth_callback(username: str, password: str):
    ident = (username or "palaj@school.com").strip()
    return cl.User(identifier=ident, metadata={"role": "teacher"})

ACTIVE_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
_CLIENT_CACHE = {}
_KEY_MODELS_CACHE = {}
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

def format_friendly_error(err_str):
    e = str(err_str)
    if "429" in e or "RESOURCE_EXHAUSTED" in e:
        return "API Key નો ફ્રી ક્વોટા પૂરો થઈ ગયો છે. થોડીવાર પછી પ્રયાસ કરો અથવા નવી API Key ઉમેરો."
    if "400" in e and ("API_KEY_INVALID" in e or "API key not valid" in e):
        return "તમારી GEMINI_API_KEY ખોટી છે. Environment Variables માં તપાસો."
    return f"કનેક્શન સમસ્યા: {e[:140]}"

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

_GUJ_DIGIT_MAP = str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")
_SUBJECT_LABELS = {"gujarati": "ગુજરાતી", "sanskrit": "સંસ્કૃત", "math": "ગણિત", "science": "વિજ્ઞાન", "social_science": "સામાજિક વિજ્ઞાન", "environment": "પર્યાવરણ", "english": "અંગ્રેજી", "hindi": "હિન્દી"}
_EXPLICIT_SUBJECTS = {
    "social_science": ["સામાજિક વિજ્ઞાન", "સામાજિક", "social", "ઇતિહાસ", "ભૂગોળ", "નકશો", "નક્શો", "નકશા", "નકશાપૂર્તિ", "naksho", "naksha", "જિલ્લા", "તાલુકા", "ગુજરાત", "મગધ", "કિલ્લો", "કિલ્લા", "પ્રદેશ", "ઉદ્યોગ", "ખેત ઉત્પાદન", "પાક"],
    "math": ["ગણિત", "math", "ભૂમિતિ", "અપૂર્ણાંક", "વર્તુળ", "ત્રિકોણ", "ચોરસ", "આલેખ", "alekh", "graph", "chart", "સ્તંભ", "રેખીય"],
    "science": ["વિજ્ઞાન", "science", "પ્રકાશસંશ્લેષણ", "કોષ", "વિદ્યુત", "ચુંબક"],
    "environment": ["પર્યાવરણ", "આસપાસ", "evs"],
    "gujarati": ["ગુજરાતી", "gujarati", "કલશોર", "કેકારવ", "કુહૂ", "પલાશ"],
    "sanskrit": ["સંસ્કૃત", "sanskrit"],
    "english": ["અંગ્રેજી", "english"],
    "hindi": ["હિન્દી", "hindi"],
}

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
    await asyncio.to_thread(get_pdf_font)
    await asyncio.to_thread(load_real_geojson, "gujarat")
    await asyncio.to_thread(load_real_geojson, "india")

@cl.on_chat_start
async def on_chat_start():
    ensure_thread_files_dir()
    asyncio.create_task(prewarm_geo_cache())
    cl.user_session.set("messages", [])
    cl.user_session.set("model_choice", ACTIVE_MODELS[0])

    settings = await cl.ChatSettings(
        [Select(id="model_choice", label="🤖 AI મોડેલ પસંદ કરો:", values=ACTIVE_MODELS, initial_index=0)]
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
        clean_q = "[કેમેરા / ફાઈલ સંલગ્ન છે — તેમાં રહેલા દાખલા / આલેખ / પ્રશ્નનો સંપૂર્ણ ઉકેલ આપો]"
    await process_teacher_query(clean_q, elements)

async def process_teacher_query(clean_q: str, elements: list):
    ensure_thread_files_dir()
    api_keys = get_api_keys()
    model_choice = cl.user_session.get("model_choice", ACTIVE_MODELS[0])
    messages = cl.user_session.get("messages") or []
    messages.append({"role": "user", "content": clean_q})
    cl.user_session.set("messages", messages)

    if not api_keys:
        await cl.Message(content="⚠️ Environment Variables માં `GEMINI_API_KEY` દાખલ કરો.").send()
        return

    user_att_parts = []
    for el in elements:
        try:
            fb = open(el.path, "rb").read() if (getattr(el, "path", None) and os.path.exists(el.path)) else getattr(el, "content", None)
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
    has_image_att = len(user_att_parts) > 0

    is_map_q = wants_map(clean_q)
    is_graph_q = (wants_graph(clean_q) or has_image_att) and not is_map_q
    math_svg_code = build_math_fraction_svg(clean_q) if (not is_map_q and not is_graph_q) else None
    is_drawing_q = wants_any_drawing_or_diagram(clean_q) and not is_map_q and not is_graph_q and not math_svg_code

    recent_hist = "\n".join(f"{'વિદ્યાર્થી' if m['role']=='user' else 'શિક્ષક'}: {m['content']}" for m in messages[:-1][-3:])
    book_page_parts = await asyncio.to_thread(build_vision_pdf_parts, local_pdf_paths[0]) if (local_pdf_paths and needs_textbook_vision(clean_q)) else []

    img_task = asyncio.create_task(generate_clean_drawing_async(clean_q, api_keys, get_cached_client, get_working_models_for_key)) if is_drawing_q else None

    visual_instruction = ""
    if is_graph_q:
        visual_instruction += (
            "\n**આલેખ (GRAPH) માટેની મહત્વની સૂચના:** જો પ્રશ્નમાં કે મોકલેલા ફોટોમાં કોઈ **આલેખ** હોય, તો જવાબની શરૂઆતમાં નીચે મુજબનો ```graph_json બ્લોક ફરજિયાત આપો (બધી સંખ્યા અંગ્રેજી અંકોમાં રાખો):\n"
            "```graph_json\n"
            '{"type": "line", "title": "આલેખ", "x_label": "X-અક્ષ", "y_label": "Y-અક્ષ", "scale": "X-અક્ષ: 1 એકમ | Y-અક્ષ: 5 એકમ", "x": [1, 2, 3, 4], "y": [5, 10, 15, 20]}\n'
            "```\n"
            "(`type` માટે `\"line\"`, `\"bar\"`, `\"pie\"`, અથવા `\"points\"` વાપરો)."
        )
    if is_map_q:
        visual_instruction += (
            "\n**નકશા (MAP) માટેની સૂચના:** પ્રશ્ન મુજબ સાચો ```map_json બ્લોક ફરજિયાત આપો:\n"
            "```map_json\n"
            '{"region": "gujarat", "only_selected": true, "header_top": "સામાજિક વિજ્ઞાન - નકશા પૂર્તિ", "title": "જિલ્લાના તાલુકા મથકો અને મુખ્ય ગામો", "show_rivers": true, "highlights": [{"place": "પાટણ", "label": "પાટણ", "color": "#FEF08A"}], "pins": [{"name": "પાટણ", "lat": 23.849, "lon": 72.126, "type": "taluka"}]}\n'
            "```"
        )
    elif is_drawing_q:
        visual_instruction += "\n**ચિત્ર / આકૃતિ માટેની સૂચના:** ઉપર પાઠ્યપુસ્તકનું ચિત્ર/આકૃતિ આપમેળે દોરાઈને દેખાશે, તેથી ટેક્સ્ટમાં dot/dash વાળી ASCII આકૃતિ ન બનાવશો — ફક્ત નીચે મુદ્દાસર સમજૂતી ગુજરાતીમાં આપો."

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
                        if "```map_json" not in temp and "```graph_json" not in temp and "<svg" not in temp.lower():
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

    computed_graph_bytes, clean_text = await asyncio.to_thread(extract_or_build_graph_bytes, answer_text)

    computed_map_bytes = None
    if is_map_q:
        computed_map_bytes, clean_text = await asyncio.to_thread(extract_or_build_map_bytes, clean_text, True, clean_q)
    else:
        clean_text = re.sub(r"```map_json[\s\S]*?```", "", clean_text)

    msg_elements = []
    if computed_map_bytes:
        msg_elements.append(cl.Image(name="palaj_map.png", content=computed_map_bytes, display="inline"))
    elif computed_graph_bytes:
        msg_elements.append(cl.Image(name="palaj_graph.png", content=computed_graph_bytes, display="inline"))
    elif generated_svg_code:
        msg_elements.append(make_svg_element(generated_svg_code, "palaj_diagram"))
    elif generated_img_bytes:
        msg_elements.append(cl.Image(name="palaj_illustration.png", content=generated_img_bytes, display="inline"))
    elif math_svg_code:
        msg_elements.append(make_svg_element(math_svg_code, "math_diagram"))

    badge = ""
    if computed_map_bytes:
        badge = "🗺️ *પાઠ્યપુસ્તક શૈલીનો રાજકીય અને ભૌગોલિક નકશો*\n\n"
    elif computed_graph_bytes:
        badge = "📊 *ગ્રાફ પેપર પર દોરેલો સચોટ આલેખ (Graph)*\n\n"
    elif generated_img_bytes:
        badge = "🎨 *શૈક્ષણિક ચિત્ર (AI Illustration)*\n\n"
    elif grade and subject and local_pdf_paths:
        badge = f"📖 *ધોરણ {grade} | {_SUBJECT_LABELS.get(subject, subject)}*\n\n"

    msg.content = f"{badge}{clean_text.strip()}"
    msg.elements = msg_elements
    msg.actions = get_quick_actions()
    await msg.update()

    messages.append({
        "role": "assistant",
        "content": answer_text,
        "graph_bytes": computed_graph_bytes,
        "map_bytes": computed_map_bytes,
        "image_bytes": generated_img_bytes,
        "math_svg": generated_svg_code or math_svg_code,
    })
    cl.user_session.set("messages", messages)
