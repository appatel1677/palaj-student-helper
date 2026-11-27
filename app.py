import os
import re
import io
import json
import fitz
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

def wants_rojnishi(text: str) -> bool:
    t = (text or "").lower()
    keywords = [
        "રોજનીશી", "rojnishi", "દૈનિક આયોજન", "dainik ayojan", "dainik",
        "સાપ્તાહિક આયોજન", "માસિક આયોજન", "નોંધપોથી", "daily diary", "lesson plan"
    ]
    return any(k in t for k in keywords)

def load_teacher_reference_context(query: str) -> str:
    base_dir = "teacher_data"
    if not os.path.exists(base_dir):
        return ""

    grade_match = re.search(r"([3-8])", query.translate(str.maketrans("૩૪૫૬૭૮", "345678")))
    grade = grade_match.group(1) if grade_match else ""

    selected_pdfs = []
    for root, _dirs, files in os.walk(base_dir):
        for fname in files:
            if not fname.lower().endswith(".pdf"):
                continue
            fpath = os.path.join(root, fname)
            fl = fname.lower()
            if "annual" in fl or "calendar" in fl or "calender" in fl:
                selected_pdfs.append(fpath)
            elif grade and (grade in fl or "3to8" in fl or ("4to5" in fl and grade in ("4", "5")) or ("6to8" in fl and grade in ("6", "7", "8")) or ("7to8" in fl and grade in ("7", "8"))):
                selected_pdfs.append(fpath)

    extracted_chunks = []
    for pdf_path in selected_pdfs[:4]:
        try:
            with fitz.open(pdf_path) as doc:
                text_buf = []
                for page in doc[:8]:
                    txt = page.get_text("text").strip()
                    if txt:
                        text_buf.append(txt[:1500])
                if text_buf:
                    extracted_chunks.append(f"--- ફાઈલ: {os.path.basename(pdf_path)} ---\n" + "\n".join(text_buf)[:3500])
        except Exception:
            continue

    return "\n\n".join(extracted_chunks)[:10000]

def extract_or_build_rojnishi_docx(raw_text: str):
    match = re.search(r"```rojnishi_json\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    if not match:
        return None, raw_text

    clean_text = re.sub(r"```rojnishi_json\s*\{.*?\}\s*```", "", raw_text, flags=re.DOTALL).strip()
    try:
        data = json.loads(match.group(1))
    except Exception:
        return None, clean_text

    days_list = data.get("days") or []
    if not days_list:
        return None, clean_text

    doc = Document()
    for section in doc.sections:
        section.top_margin = Inches(0.45)
        section.bottom_margin = Inches(0.45)
        section.left_margin = Inches(0.45)
        section.right_margin = Inches(0.45)

    gujarati_nums = ["૧", "૨", "૩", "૪", "૫", "૬", "૭", "૮"]

    for page_idx, day_info in enumerate(days_list):
        if page_idx > 0:
            doc.add_page_break()

        header_table = doc.add_table(rows=2, cols=3)
        header_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        header_table.autofit = False
        header_table.columns[0].width = Inches(2.1)
        header_table.columns[1].width = Inches(3.3)
        header_table.columns[2].width = Inches(2.1)

        header_table.cell(0, 0).text = f"ધોરણ : {day_info.get('std', data.get('std', ''))}"
        header_table.cell(1, 0).text = f"વર્ગ : {day_info.get('div', data.get('div', 'અ'))}"

        title_cell = header_table.cell(0, 1).merge(header_table.cell(1, 1))
        p_title = title_cell.paragraphs[0]
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_t = p_title.add_run("દૈનિક આયોજન")
        run_t.bold = True
        run_t.font.size = Pt(18)

        header_table.cell(0, 2).text = f"તા. : {day_info.get('date', '   /   /૨૦૨૬')}"
        header_table.cell(1, 2).text = f"વાર : {day_info.get('day', '')}"

        doc.add_paragraph("")

        table = doc.add_table(rows=9, cols=6)
        table.style = "Table Grid"
        table.autofit = False

        col_widths = [Inches(0.45), Inches(1.0), Inches(1.1), Inches(2.75), Inches(1.1), Inches(1.1)]
        headers = ["તાસ", "ધોરણ/\nવિષય", "અધ્યયન\nનિષ્પત્તિ ક્રમાંક", "એકમ - શૈક્ષણિક મુદ્દા", "શૈક્ષણિક\nસાધનો", "ગૃહકાર્ય"]

        hdr_cells = table.rows[0].cells
        for i, h_text in enumerate(headers):
            hdr_cells[i].width = col_widths[i]
            p = hdr_cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(h_text)
            r.bold = True
            r.font.size = Pt(10)

        periods_map = {
            int(p.get("tas", idx + 1)): p
            for idx, p in enumerate(day_info.get("periods") or [])
            if str(p.get("tas", idx + 1)).isdigit()
        }

        for r_idx in range(8):
            tas_no = r_idx + 1
            row_cells = table.rows[tas_no].cells
            row_cells[0].text = gujarati_nums[r_idx]
            row_cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

            p_data = periods_map.get(tas_no, {})
            row_cells[1].text = str(p_data.get("subject", ""))
            row_cells[2].text = str(p_data.get("lo_code", ""))
            row_cells[3].text = str(p_data.get("topic", ""))
            row_cells[4].text = str(p_data.get("tlm", ""))
            row_cells[5].text = str(p_data.get("homework", ""))

            for c_idx in range(6):
                row_cells[c_idx].width = col_widths[c_idx]
                for para in row_cells[c_idx].paragraphs:
                    for run in para.runs:
                        run.font.size = Pt(9.5)

        doc.add_paragraph("\n")

        sign_table = doc.add_table(rows=1, cols=2)
        sign_table.autofit = False
        sign_table.columns[0].width = Inches(3.75)
        sign_table.columns[1].width = Inches(3.75)
        sign_table.cell(0, 0).text = "વર્ગ શિક્ષકની સહી"
        p_sign_r = sign_table.cell(0, 1).paragraphs[0]
        p_sign_r.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_sign_r.add_run("આચાર્યની સહી")

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue(), clean_text
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
    book_page_parts = await asyncio.to_thread(build_vision_pdf_parts, local_pdf_paths[0]) if (local_pdf_paths and needs_textbook_vision(clean_q)) else []

    img_task = asyncio.create_task(generate_clean_drawing_async(clean_q, api_keys, get_cached_client, get_working_models_for_key)) if is_drawing_q else None

    visual_instruction = ""
    if is_graph_q:
        visual_instruction += (
            "\n**આલેખ (GRAPH) માટેની મહત્વની સૂચના:** જો પ્રશ્નમાં કે મોકલેલા ફોટોમાં કોઈ **આલેખ** હોય, તો જવાબની શરૂઆતમાં નીચે મુજબનો ```graph_json બ્લોક ફરજિયાત આપો (બધી સંખ્યા અંગ્રેજી અંકોમાં રાખો):\n"
            "```graph_json\n"
            '{"type": "line", "title": "આલેખ", "x_label": "X-અક્ષ", "y_label": "Y-અક્ષ", "scale": "X-અક્ષ: 1 એકમ | Y-અક્ષ: 5 એકમ", "x":, "y": [5, 10, 15, 20]}\n'
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
            "જવાબની શરૂઆતમાં નીચે મુજબનો ```rojnishi_json બ્લોક ફરજિયાત આપો (જો સાપ્તાહિક હોય તો 6 દિવસ અને માસિક હોય તો 20-24 કાર્યદિવસના days ઉમેરો, રવિવાર/જાહેર રજા বাদ રાખવી):\n"
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
                    contents=book_page_parts + user_att_parts + [prompt_text]
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

    rojnishi_docx_bytes, clean_text = await asyncio.to_thread(extract_or_build_rojnishi_docx, clean_text)

    msg.content = clean_text if clean_text else "✅ તૈયાર છે:"
    msg_elements = []

    if computed_graph_bytes:
        msg_elements.append(cl.Image(name="graph.png", content=computed_graph_bytes, display="inline"))
    if computed_map_bytes:
        msg_elements.append(cl.Image(name="map.png", content=computed_map_bytes, display="inline"))
    if math_svg_code:
        msg_elements.append(make_svg_element(math_svg_code, "math_diagram.svg"))
    elif generated_svg_code:
        msg_elements.append(make_svg_element(generated_svg_code, "diagram.svg"))
    elif generated_img_bytes:
        msg_elements.append(cl.Image(name="diagram.png", content=generated_img_bytes, display="inline"))

    if rojnishi_docx_bytes:
        msg_elements.append(
            cl.File(name="Dainik_Ayojan_Rojnishi.docx", content=rojnishi_docx_bytes, display="inline")
        )

    if msg_elements:
        msg.elements = msg_elements
    msg.actions = get_quick_actions()
    await msg.update()

    messages.append({"role": "assistant", "content": clean_text})
    cl.user_session.set("messages", messages)


