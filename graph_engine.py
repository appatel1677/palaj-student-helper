import io
import re
import json
from db_and_pdf import get_pdf_font

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

def wants_graph(text):
    t = (text or "").lower()
    return any(kw in t for kw in (
        "આલેખ", "alekh", "aalekh", "graph", "chart", "plot",
        "રેખીય", "સ્તંભ", "પાય ચાર્ટ", "pie chart", "bar graph", "line graph",
        "યામ", "બિંદુઓ દર્શાવો", "x-અક્ષ", "y-અક્ષ", "પ્રમાણમાપ"
    ))

def render_school_graph_png(spec):
    if not HAS_MPL:
        return None
    font_path = get_pdf_font()
    if font_path:
        try:
            font_manager.fontManager.addfont(font_path)
            prop_name = font_manager.FontProperties(fname=font_path).get_name()
            plt.rcParams["font.sans-serif"] = [prop_name, "DejaVu Sans"]
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["axes.unicode_minus"] = False
        except Exception:
            pass

    fp_title = font_manager.FontProperties(fname=font_path, size=13.5, weight="bold") if font_path else None
    fp_sub = font_manager.FontProperties(fname=font_path, size=10.5, weight="bold") if font_path else None
    fp_lbl = font_manager.FontProperties(fname=font_path, size=9.2, weight="bold") if font_path else None
    fp_small = font_manager.FontProperties(fname=font_path, size=8.2) if font_path else None

    gtype = str(spec.get("type", "line")).lower()
    title = str(spec.get("title", "ગણિત - આલેખ (Graph)")).strip()
    x_label = str(spec.get("x_label", "X-અક્ષ")).strip()
    y_label = str(spec.get("y_label", "Y-અક્ષ")).strip()
    scale_text = str(spec.get("scale", "")).strip()
    x_vals = spec.get("x") or []
    y_vals = spec.get("y") or []

    if not x_vals or not y_vals:
        return None

    fig = plt.figure(figsize=(10.5, 6.8), dpi=170)
    fig.patch.set_facecolor("#F8FAFC")

    ax = fig.add_axes([0.11, 0.14, 0.83, 0.72])
    ax.set_facecolor("#F0FDF4")

    fig.text(0.52, 0.94, title, ha="center", va="center", color="#1E3A8A", fontproperties=fp_title)
    if scale_text:
        fig.text(0.52, 0.895, f"પ્રમાણમાપ: {scale_text}", ha="center", va="center", color="#B91C1C", fontproperties=fp_sub)

    if gtype == "pie":
        ax.clear()
        ax.set_facecolor("#FFFFFF")
        nums = [float(v) for v in y_vals]
        labels = [str(v) for v in x_vals]
        colors = ["#FDE047", "#38BDF8", "#F472B6", "#4ADE80", "#FB923C", "#A78BFA", "#2DD4BF"]
        wedges, texts, autotexts = ax.pie(
            nums, labels=labels, autopct="%1.1f%%", startangle=90,
            colors=colors[:len(nums)], wedgeprops=dict(edgecolor="#1E293B", linewidth=1.2)
        )
        for t in texts:
            if fp_lbl:
                t.set_fontproperties(fp_lbl)
        for at in autotexts:
            at.set_fontsize(8.5)
            at.set_fontweight("bold")
        ax.axis("equal")

    elif gtype == "bar":
        labels = [str(v) for v in x_vals]
        nums = [float(v) for v in y_vals]
        bars = ax.bar(labels, nums, color="#3B82F6", edgecolor="#1E3A8A", linewidth=1.3, width=0.52, zorder=4)
        ax.grid(True, which="major", axis="y", color="#86EFAC", linestyle="-", linewidth=1.0, zorder=1)
        ax.minorticks_on()
        ax.grid(True, which="minor", axis="y", color="#BBF7D0", linestyle=":", linewidth=0.7, zorder=1)
        for bar, val in zip(bars, nums):
            disp = int(val) if val == int(val) else round(val, 2)
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(nums) * 0.02, str(disp),
                    ha="center", va="bottom", color="#0F172A", fontproperties=fp_lbl, zorder=5)
        ax.set_ylim(0, max(nums) * 1.18 if max(nums) > 0 else 10)
        for lbl in ax.get_xticklabels() + ax.get_yticklabels():
            if fp_small:
                lbl.set_fontproperties(fp_small)

    else:
        try:
            xs = [float(v) for v in x_vals]
            is_numeric_x = True
        except Exception:
            xs = list(range(len(x_vals)))
            is_numeric_x = False

        ys = [float(v) for v in y_vals]

        ax.minorticks_on()
        ax.grid(True, which="major", color="#22C55E", linestyle="-", linewidth=1.0, alpha=0.65, zorder=1)
        ax.grid(True, which="minor", color="#86EFAC", linestyle="-", linewidth=0.55, alpha=0.55, zorder=1)

        if gtype != "points":
            ax.plot(xs, ys, color="#DC2626", linewidth=2.5, zorder=4)

        ax.scatter(xs, ys, s=68, color="#1D4ED8", edgecolor="#FFFFFF", linewidth=1.3, zorder=5)

        for idx_p, (px, py) in enumerate(zip(xs, ys)):
            x_disp = int(px) if (is_numeric_x and px == int(px)) else (px if is_numeric_x else x_vals[idx_p])
            y_disp = int(py) if py == int(py) else round(py, 2)
            ax.annotate(
                f"({x_disp}, {y_disp})",
                (px, py),
                textcoords="offset points",
                xytext=(0, 9),
                ha="center",
                color="#0F172A",
                fontproperties=fp_small,
                bbox=dict(boxstyle="round,pad=0.15", facecolor="#FFFFFF", edgecolor="#94A3B8", alpha=0.88),
                zorder=6
            )

        if not is_numeric_x:
            ax.set_xticks(xs)
            ax.set_xticklabels([str(v) for v in x_vals])

        x_max = max(xs) if xs else 10
        y_max = max(ys) if ys else 10
        x_min = min(0, min(xs)) if is_numeric_x else -0.5
        y_min = min(0, min(ys))
        ax.set_xlim(x_min, x_max * 1.15 if x_max > 0 else 10)
        ax.set_ylim(y_min, y_max * 1.18 if y_max > 0 else 10)

        for lbl in ax.get_xticklabels() + ax.get_yticklabels():
            if fp_small:
                lbl.set_fontproperties(fp_small)

    if gtype != "pie":
        ax.set_xlabel(x_label, color="#0F172A", fontproperties=fp_lbl, labelpad=8)
        ax.set_ylabel(y_label, color="#0F172A", fontproperties=fp_lbl, labelpad=8)
        for spine in ["bottom", "left"]:
            ax.spines[spine].set_color("#0F172A")
            ax.spines[spine].set_linewidth(1.8)
        for spine in ["top", "right"]:
            ax.spines[spine].set_color("#64748B")
            ax.spines[spine].set_linewidth(1.0)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=170)
    plt.close(fig)
    return buf.getvalue()

def extract_or_build_graph_bytes(content):
    graph_img_bytes = None
    clean_text = content
    if "```graph_json" in clean_text:
        m = re.search(r"```graph_json\s*([\s\S]*?)```", clean_text)
        if m:
            try:
                spec = json.loads(m.group(1).strip())
                graph_img_bytes = render_school_graph_png(spec)
            except Exception:
                pass
        clean_text = re.sub(r"```graph_json[\s\S]*?```", "", clean_text)
    return graph_img_bytes, clean_text
