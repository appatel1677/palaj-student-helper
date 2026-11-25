import os
import re
import io
import glob
import sqlite3
import urllib.request
from PIL import Image
from fpdf import FPDF
import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

DB_FILE = os.path.abspath("chat_history.db")
_PDF_FONT_CACHE = None

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

class LocalFileStorageProvider:
    def __init__(self, base_dir=".files"):
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    async def upload_file(self, object_key: str, data: bytes | str, mime: str = "application/octet-stream", overwrite: bool = True, content_disposition: str | None = None):
        full_path = os.path.join(self.base_dir, object_key.replace("/", os.sep))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        raw = data.encode("utf-8") if isinstance(data, str) else data
        with open(full_path, "wb") as f:
            f.write(raw)
        return {"object_key": object_key, "url": f"/files/{object_key}"}

    async def delete_file(self, object_key: str) -> bool:
        full_path = os.path.join(self.base_dir, object_key.replace("/", os.sep))
        if os.path.exists(full_path):
            os.remove(full_path)
            return True
        return False

    async def get_read_url(self, object_key: str) -> str:
        return f"/files/{object_key}"

def build_sqlalchemy_data_layer():
    db_url = f"sqlite+aiosqlite:///{DB_FILE.replace(chr(92), '/')}"
    return SQLAlchemyDataLayer(conninfo=db_url, storage_provider=LocalFileStorageProvider(".files"))

def get_pdf_font():
    global _PDF_FONT_CACHE
    if _PDF_FONT_CACHE and os.path.exists(_PDF_FONT_CACHE):
        return _PDF_FONT_CACHE

    candidates = [
        "NotoSansGujarati-Regular.ttf",
        "C:/Windows/Fonts/Nirmala.ttf",
        "C:/Windows/Fonts/Shruti.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansGujarati-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansGujarati-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSerifGujarati-Regular.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            _PDF_FONT_CACHE = p
            return p

    for found in glob.glob("/usr/share/fonts/**/*Gujarati*.ttf", recursive=True):
        if os.path.exists(found):
            _PDF_FONT_CACHE = found
            return found

    os.makedirs("geo_cache", exist_ok=True)
    local_dl = os.path.abspath("geo_cache/NotoSansGujarati-Regular.ttf")
    if os.path.exists(local_dl):
        _PDF_FONT_CACHE = local_dl
        return local_dl
    try:
        url = "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSansGujarati/NotoSansGujarati-Regular.ttf"
        urllib.request.urlretrieve(url, local_dl)
        if os.path.exists(local_dl) and os.path.getsize(local_dl) > 10000:
            _PDF_FONT_CACHE = local_dl
            return local_dl
    except Exception:
        pass

    return None

def svg_to_png_bytes(svg_code):
    try:
        import fitz
        doc = fitz.open(stream=svg_code.encode("utf-8"), filetype="svg")
        pix = doc[0].get_pixmap(dpi=170, alpha=False)
        return pix.tobytes("png")
    except Exception:
        return None

def make_svg_element(svg_code, name="diagram"):
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

        vis_bytes = m.get("graph_bytes") or m.get("map_bytes") or m.get("image_bytes")
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
        clean_txt = re.sub(r"```(?:map_json|graph_json|village_map_json)[\s\S]*?```", "", clean_txt)
        clean_txt = re.sub(r"<[^>]+>", "", clean_txt)
        clean_txt = clean_txt.replace("**", "").replace("###", "").replace("##", "").strip()
        if clean_txt:
            pdf.multi_cell(0, 6.2, clean_txt)
        pdf.ln(3)
        pdf.set_draw_color(226, 232, 240)
        pdf.line(14, pdf.get_y(), 196, pdf.get_y())
        pdf.ln(3)

    return bytes(pdf.output())
