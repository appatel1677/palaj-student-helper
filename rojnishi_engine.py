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
            elif grade and (
                grade in fl
                or "3to8" in fl
                or ("4to5" in fl and grade in ("4", "5"))
                or ("6to8" in fl and grade in ("6", "7", "8"))
                or ("7to8" in fl and grade in ("7", "8"))
            ):
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
    match = re.search(r"```rojnishi_json\s*(\{[\s\S]*?\})\s*```", raw_text)
    if not match:
        return None, raw_text

    clean_text = re.sub(r"```rojnishi_json\s*\{[\s\S]*?\}\s*```", "", raw_text).strip()
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
