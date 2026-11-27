import os
import re
import io
import json
import math
import hashlib
import asyncio
from dotenv import load_dotenv
load_dotenv()

os.makedirs(".files", exist_ok=True)
os.makedirs("geo_cache", exist_ok=True)
os.makedirs(".rag_cache", exist_ok=True)

import fitz  # PyMuPDF
import chainlit as cl
from chainlit.input_widget import Select
from PIL import Image
from google import genai
from google.genai import types

from db_and_pdf import (
    init_chainlit_sqlite_db,
    build_sqlalchemy_data_layer,
    get_pdf_font,
    make_svg_element,
    build_pdf_bytes,
)
from graph_engine import wants_graph, extract_or_build_graph_bytes
from map_engine import wants_map, load_real_geojson, extract_or_build_map_bytes
from drawing_engine import (
    wants_any_drawing_or_diagram,
    build_math_fraction_svg,
    generate_clean_drawing_async,
)
from rojnishi_engine import (
    wants_rojnishi,
    load_teacher_reference_context,
    extract_or_build_rojnishi_docx,
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
_PDF_INDEX_MEMORY = {}

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
_SUBJECT_LABELS = {
    "gujarati": "ગુજરાતી",
    "sanskrit": "સંસ્કૃત",
    "math": "ગણિત",
    "science": "વિજ્ઞાન",
    "social_science": "સામાજિક વિજ્ઞાન",
    "environment": "પર્યાવરણ",
    "english": "અંગ્રેજી",
    "hindi": "હિન્દી",
}
_EXPLICIT_SUBJECTS = {
    "social_science": ["સામાજિક વિજ્ઞાન", "સામાજિક", "social", "ઇતિહાસ", "ભૂગોળ", "નકશો", "નક્શો", "નકશા", "નકશાપૂર્તિ", "naksho", "naksha", "જિલ્લા", "તાલુકા", "ગુજરાત", "મગધ", "કિલ્લો", "કિલ્લા", "પ્રદેશ", "ઉદ્યોગ", "ખેત ઉત્પાદન", "પાક"],
    "math": ["ગણિત", "math", "ભૂમિતિ", "અપૂર્ણાંક", "વર્તુળ", "ત્રિકોણ", "ચોરસ", "આલેખ", "alekh", "graph", "chart", "સ્તંભ", "રેખીય", "ક્ષેત્રફળ", "પરિમિતિ", "ઘનફળ", "ટકાવારી", "વ્યાજ"],
    "science": ["વિજ્ઞાન", "science", "પ્રકાશસંશ્લેષણ", "કોષ", "વિદ્યુત", "ચુંબક", "પદાર્થ", "ઉષ્મા", "પ્રકાશ", "ધ્વનિ"],
    "environment": ["પર્યાવરણ", "આસપાસ", "evs"],
    "gujarati": ["ગુજરાતી", "gujarati", "કલશોર", "કેકારવ", "કુહૂ", "પલાશ"],
    "sanskrit": ["સંસ્કૃત", "sanskrit"],
    "english": ["અંગ્રેજી", "english"],
    "hindi": ["હિન્દી", "hindi"],
}

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
    matched = []
    if grade and subject:
        for _label, info in ((syllabus.get(f"ધોરણ {grade}") or {}).get("subjects", {})).items():
            if info.get("code") == subject:
                for p in info.get("local_pdfs") or []:
                    path = p.replace("\\", "/")
                    if os.path.exists(path) and path not in matched:
                        matched.append(path)
                break
    elif subject and not grade:
        # જો ધોરણ ન લખ્યું હોય પણ વિષય લખ્યો હોય (દા.ત. "પ્રકાશસંશ્લેષણ"), તો તે વિષયની બધી PDF શોધો
        for g_key, g_val in syllabus.items():
            for _label, info in (g_val.get("subjects") or {}).items():
                if info.get("code") == subject:
                    for p in info.get("local_pdfs") or []:
                        path = p.replace("\\", "/")
                        if os.path.exists(path) and path not in matched:
                            matched.append(path)
    return grade, subject, matched[:3]

# ==============================================================================
# VECTOR SEARCH / EMBEDDING RAG ENGINE (Gemini text-embedding-004 + Cosine Sim)
# ==============================================================================
def _cosine_similarity(v1, v2):
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    return dot / (norm1 * norm2) if (norm1 and norm2) else 0.0

def _get_query_embedding(query_text, api_keys):
    for key in api_keys:
        try:
            client = get_cached_client(key)
            res = client.models.embed_content(
                model="text-embedding-004",
                contents=query_text,
            )
            if res and res.embeddings:
                return res.embeddings[0].values
        except Exception:
            continue
    return None

def _get_or_build_pdf_vector_index(pdf_path, api_keys):
    """આખી PDF ના દરેક પાનાનું Embedding બનાવીને .rag_cache માં સેવ કરે છે."""
    abspath = os.path.abspath(pdf_path)
    if not os.path.exists(abspath):
        return []

    file_stat = os.stat(abspath)
    cache_id = hashlib.md5(f"{abspath}_{file_stat.st_size}_{file_stat.st_mtime}".encode()).hexdigest()
    if cache_id in _PDF_INDEX_MEMORY:
        return _PDF_INDEX_MEMORY[cache_id]

    cache_file = os.path.join(".rag_cache", f"{cache_id}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                _PDF_INDEX_MEMORY[cache_id] = data
                return data
        except Exception:
            pass

    # PDF માંથી દરેક પાનાનું ટેક્સ્ટ કાઢો
    pages_data = []
    try:
        with fitz.open(abspath) as doc:
            for idx in range(len(doc)):
                txt = (doc[idx].get_text("text") or "").strip()
                # જો પાનું સ્કેન કરેલું હોય અને ટેક્સ્ટ ઓછું હોય તો પાનાનો નંબર રાખો
                embed_txt = txt[:2000] if len(txt) > 20 else f"પાઠ્યપુસ્તક પાના નંબર {idx + 1}"
                pages_data.append({"page_idx": idx, "text": txt[:2500], "embed_input": embed_txt})
    except Exception:
        return []

    if not pages_data:
        return []

    # Batch માં Embeddings જનરેટ કરો (ઝડપી અને API બચત માટે 20-20 ના જૂથમાં)
    indexed_chunks = []
    batch_size = 20
    for start in range(0, len(pages_data), batch_size):
        batch = pages_data[start:start + batch_size]
        texts_to_embed = [item["embed_input"] for item in batch]
        embedded_ok = False
        for key in api_keys:
            try:
                client = get_cached_client(key)
                res = client.models.embed_content(
                    model="text-embedding-004",
                    contents=texts_to_embed,
                )
                if res and res.embeddings and len(res.embeddings) == len(batch):
                    for item, emb in zip(batch, res.embeddings):
                        indexed_chunks.append({
                            "pdf_path": abspath,
                            "page_idx": item["page_idx"],
                            "text": item["text"],
                            "embedding": emb.values,
                        })
                    embedded_ok = True
                    break
            except Exception:
                continue
        if not embedded_ok:
            # જો API ક્વોટા પૂરો હોય તો fallback તરીકે માત્ર ટેક્સ્ટ સાચવો
            for item in batch:
                indexed_chunks.append({
                    "pdf_path": abspath,
                    "page_idx": item["page_idx"],
                    "text": item["text"],
                    "embedding": [],
                })

    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(indexed_chunks, f, ensure_ascii=False)
    except Exception:
        pass

    _PDF_INDEX_MEMORY[cache_id] = indexed_chunks
    return indexed_chunks

def search_textbook_rag(query_text, pdf_paths, api_keys, top_k=3):
    """
    Vector Search + Keyword Boost વડે આખા પુસ્તકમાંથી સૌથી વધુ બંધબેસતા top_k પાનાં શોધે છે,
    અને તેના HD Vision Image Parts + Text Context આપે છે.
    """
    if not pdf_paths:
        return [], ""

    q_emb = _get_query_embedding(query_text, api_keys)
    q_words = [w.lower() for w in re.findall(r"\w+", query_text) if len(w) > 2]

    scored_pages = []
    for pdf_p in pdf_paths:
        chunks = _get_or_build_pdf_vector_index(pdf_p, api_keys)
        for ch in chunks:
            vec_score = _cosine_similarity(q_emb, ch.get("embedding")) if (q_emb and ch.get("embedding")) else 0.0
            # ગુજરાતી શબ્દો માટે Keyword Match Boost
            txt_low = (ch.get("text") or "").lower()
            kw_hits = sum(1 for w in q_words if w in txt_low)
            kw_score = min(0.35, kw_hits * 0.08)
            total_score = vec_score + kw_score
            scored_pages.append((total_score, ch))

    scored_pages.sort(key=lambda x: x[0], reverse=True)
    top_chunks = [item[1] for item in scored_pages[:top_k] if item[0] > 0.15]

    # જો કોઈ સ્કોર ન મળે તો પહેલા 2 પાનાં લો
    if not top_chunks and scored_pages:
        top_chunks = [item[1] for item in scored_pages[:2]]

    vision_parts = []
    rag_text_snippets = []
    opened_docs = {}

    try:
        for ch in top_chunks:
            p_path = ch["pdf_path"]
            p_idx = ch["page_idx"]
            if p_path not in opened_docs:
                opened_docs[p_path] = fitz.open(p_path)
            doc = opened_docs[p_path]
            if 0 <= p_idx < len(doc):
                pix = doc[p_idx].get_pixmap(dpi=120, alpha=False)
                img_bytes = pix.tobytes("jpeg", jpg_quality=78)
                vision_parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
                book_name = os.path.basename(p_path)
                rag_text_snippets.append(f"--- પુસ્તક: {book_name} (પાના નં. {p_idx + 1}) ---\n{ch.get('text', '')[:1200]}")
    finally:
        for d in opened_docs.values():
            try:
                d.close()
            except Exception:
                pass

    return vision_parts, "\n\n".join(rag_text_snippets)

# ==============================================================================
# TOOL ROUTING HELPERS (Math Solver & Web Search)
# ==============================================================================
def needs_math_solver(text):
    t = (text or "").translate(_GUJ_DIGIT_MAP).lower()
    has_numbers = bool(re.search(r"\d", t))
    math_words = (
        "ગણતરી", "દાખલો", "દાખલા", "ક્ષેત્રફળ", "પરિમિતિ", "ઘનફળ", "સરવાળો", "બાદબાકી",
        "ગુણાકાર", "ભાગાકાર", "ટકા", "વ્યાજ", "સમીકરણ", "વર્ગમૂળ", "લ.સા.અ", "ગુ.સા.અ",
        "સરેરાશ", "ગુણોત્તર", "પ્રમાણ", "નફો", "ખોટ", "કિંમત", "area", "perimeter", "volume", "solve", "calculate"
    )
    return has_numbers and any(w in t for w in math_words)

def needs_web_search(text, has_rag_context):
    t = (text or "").lower()
    gk_keywords = (
        "વડાપ્રધાન", "રાષ્ટ્રપતિ", "મુખ્યમંત્રી", "રાજ્યપાલ", "હાલના", "અત્યારના", "તાજેતર",
        "ચંદ્રયાન", "ઈસરો", "isro", "nasa", "ઓલિમ્પિક", "વિશ્વકપ", "વર્લ્ડ કપ", "ક્રિકેટ",
        "સમાચાર", "કરંટ", "current", "gk", "જનરલ નોલેજ", "શોધ કોણે કરી", "ક્યારે થયું", "રાજધાની", "ચલણ"
    )
    if any(k in t for k in gk_keywords):
        return True
    # જો પાઠ્યપુસ્તકની PDF ન મળી હોય અને આલેખ/નકશો/રોજનીશી ન હોય, તો Web Search ચાલુ રાખો
    if not has_rag_context:
        return True
    return False

def get_quick_actions():
    return [
        cl.Action(name="quick_summary", payload={"type": "summary"}, label="📖 સારાંશ"),
        cl.Action(name="quick_exercise", payload={"type": "exercise"}, label="📝 સ્વાધ્યાય"),
        cl.Action(name="quick_mcq", payload={"type": "mcq"}, label="🎯 MCQ ટેસ્ટ"),
        cl.Action(name="quick_example", payload={"type": "easy_example"}, label="💡 ઉદાહરણ"),
        cl.Action(name="quick_rojnishi", payload={"type": "rojnishi"}, label="📅 દૈનિક આયોજન"),
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
        content="📚 **Standard 3 to 8 Smart AI Palaj Student Helper** (Vector RAG + Math Solver + Web Search) તૈયાર છે! નીચે પ્રશ્ન લખો, માઈક વડે બોલો અથવા ફોટો/PDF મોકલો.",
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

@cl.action_callback("quick_rojnishi")
async def on_quick_rojnishi(action: cl.Action):
    guide_msg = (
        "📅 **દૈનિક આયોજન (રોજનીશી) બનાવવા માટે નીચે મુજબ વિગત લખો અથવા બોલો:**\n"
        "- **૧ દિવસ માટે:** `ધોરણ ૬ ગણિત અને વિજ્ઞાનનું તા. ૩૦/૧૧/૨૦૨૬ નું દૈનિક આયોજન બનાવો`\n"
        "- **સાપ્તાહિક (અઠવાડિયા) માટે:** `ધોરણ ૫ ગુજરાતી અને પર્યાવરણનું આખા અઠવાડિયાનું (૬ દિવસનું) દૈનિક આયોજન બનાવો`\n"
        "- **માસિક (મહિના) માટે:** `ધોરણ ૭ વિજ્ઞાન પાઠ ૧ અને ૨ નું ડિસેમ્બર મહિનાનું માસિક દૈનિક આયોજન બનાવો`"
    )
    await cl.Message(content=guide_msg).send()

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

    is_rojnishi_q = wants_rojnishi(clean_q)
    rojnishi_ref = await asyncio.to_thread(load_teacher_reference_context, clean_q) if is_rojnishi_q else ""

    is_map_q = wants_map(clean_q) and not is_rojnishi_q
    is_graph_q = (wants_graph(clean_q) or has_image_att) and not is_map_q and not is_rojnishi_q
    math_svg_code = build_math_fraction_svg(clean_q) if (not is_map_q and not is_graph_q and not is_rojnishi_q) else None
    is_drawing_q = wants_any_drawing_or_diagram(clean_q) and not is_map_q and not is_graph_q and not math_svg_code and not is_rojnishi_q

    recent_hist = "\n".join(f"{'વિદ્યાર્થી' if m['role']=='user' else 'શિક્ષક'}: {m['content']}" for m in messages[:-1][-3:])

    # 1. VECTOR SEARCH / EMBEDDING RAG (પાઠ્યપુસ્તકમાંથી ચોક્કસ પાનાં શોધવા)
    book_page_parts, rag_text_context = [], ""
    if local_pdf_paths and not is_rojnishi_q and not is_map_q:
        book_page_parts, rag_text_context = await asyncio.to_thread(
            search_textbook_rag, clean_q, local_pdf_paths, api_keys, 3
        )

    # 2. PYTHON MATH SOLVER & GOOGLE WEB SEARCH TOOLS CONFIG
    active_tools = []
    used_tool_tag = ""
    if not is_rojnishi_q and not is_map_q and not is_graph_q:
        if needs_math_solver(clean_q):
            active_tools.append(types.Tool(code_execution=types.ToolCodeExecution()))
            used_tool_tag = "🧮 *Python Math Solver (૧૦૦% સચોટ ગણતરી)*"
        elif needs_web_search(clean_q, bool(book_page_parts)):
            active_tools.append(types.Tool(google_search=types.GoogleSearch()))
            used_tool_tag = "🌐 *Google Web Search (તાજી માહિતી)*"

    gen_config = types.GenerateContentConfig(tools=active_tools) if active_tools else None

    img_task = asyncio.create_task(generate_clean_drawing_async(clean_q, api_keys, get_cached_client, get_working_models_for_key)) if is_drawing_q else None

    visual_instruction = ""
    if rag_text_context:
        visual_instruction += (
            "\n**GCERT પાઠ્યપુસ્તક (Vector RAG) સંદર્ભ:**\n"
            f"નીચે પાઠ્યપુસ્તકના સંબંધિત પાનાંઓની માહિતી અને ઈમેજ આપેલ છે. તેના આધારે સચોટ અને સરળ ગુજરાતીમાં જવાબ આપો:\n{rag_text_context}\n"
        )
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

    if is_rojnishi_q:
        visual_instruction += (
            "\n**દૈનિક આયોજન (રોજનીશી) માટેની ફરજિયાત સૂચના:**\n"
            f"નીચે આપેલ GCERT અધ્યયન નિષ્પત્તિ અને વાર્ષિક આયોજનના સંદર્ભનો ઉપયોગ કરીને દૈનિક આયોજન બનાવો:\n{rojnishi_ref}\n\n"
            "જવાબની શરૂઆતમાં નીચે મુજબનો ```rojnishi_json બ્લોક ફરજિયાત આપો (જો સાપ્તાહિક હોય તો 6 દિવસ અને માસિક હોય તો 20-24 કાર્યદિવસના days ઉમેરો, રવિવાર/જાહેર રજા બાદ રાખવી):\n"
            "```rojnishi_json\n"
            '{"std": "૬", "div": "અ", "days": [{"date": "૩૦/૧૧/૨૦૨૬", "day": "સોમવાર", "periods": [{"tas": 1, "subject": "ધો.૬ ગણિત", "lo_code": "M601", "topic": "પાઠ ૧: સંખ્યા પરિચય - સ્થાનકિંમત", "tlm": "ચાર્ટ, પાઠ્યપુસ્તક", "homework": "સ્વાધ્યાય ૧.૧ ના દાખલા"}]}]}\n'
            "```\n"
            "અને નીચે ગુજરાતીમાં ટૂંકી વિગત લખો કે દૈનિક આયોજનની Word ફાઈલ તૈયાર છે."
        )

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
                    contents=book_page_parts + user_att_parts + [prompt_text],
                    config=gen_config
                )
                async for chunk in stream:
                    if chunk.text:
                        temp += chunk.text
                        if (
                            "```map_json" not in temp
                            and "```graph_json" not in temp
                            and "```rojnishi_json" not in temp
                            and "<svg" not in temp.lower()
                        ):
                            await msg.stream_token(chunk.text)
                if temp.strip():
                    answer_text, success = temp, True
                    break
            except Exception as e:
                last_err = e
                # જો કોઈ મોડેલમાં tool સપોર્ટ ન કરે તો config વગર ફરી પ્રયાસ કરો
                if gen_config is not None and "tool" in str(e).lower():
                    gen_config = None
                    used_tool_tag = ""
                    continue
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

    rojnishi_docx_bytes, clean_text = await asyncio.to_thread(extract_or_build_rojnishi_docx, clean_text)

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

    if rojnishi_docx_bytes:
        msg_elements.append(
            cl.File(name="Dainik_Ayojan_Rojnishi.docx", content=rojnishi_docx_bytes, display="inline")
        )

    badge = ""
    if rojnishi_docx_bytes:
        badge = "📅 *દૈનિક આયોજન (રોજનીશી) — Word (.docx) ફાઈલ તૈયાર છે*\n\n"
    elif computed_map_bytes:
        badge = "🗺️ *પાઠ્યપુસ્તક શૈલીનો રાજકીય અને ભૌગોલિક નકશો*\n\n"
    elif computed_graph_bytes:
        badge = "📊 *ગ્રાફ પેપર પર દોરેલો સચોટ આલેખ (Graph)*\n\n"
    elif generated_img_bytes:
        badge = "🎨 *શૈક્ષણિક ચિત્ર (AI Illustration)*\n\n"
    elif book_page_parts:
        subj_name = _SUBJECT_LABELS.get(subject, subject or "પાઠ્યપુસ્તક")
        std_txt = f"ધોરણ {grade} | " if grade else ""
        badge = f"📖 *{std_txt}{subj_name} (Vector RAG પાઠ્યપુસ્તક આધારિત)*\n\n"
    elif used_tool_tag:
        badge = f"{used_tool_tag}\n\n"

    msg.content = f"{badge}{clean_text.strip() or '✅ તૈયાર છે:'}"
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
