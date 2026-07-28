import json
from datetime import datetime

from config import SESSIONS_DIR


def new_session_dir(project_text):
    safe_title = "".join(c if c.isalnum() else "_" for c in project_text[:30]).strip("_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dir_name = f"{timestamp}_{safe_title}"
    session_path = SESSIONS_DIR / dir_name
    session_path.mkdir(parents=True, exist_ok=True)
    return session_path


def save_transcript_json(session_path, project, transcript):
    data = {
        "project": project,
        "timestamp": datetime.now().isoformat(),
        "transcript": transcript
    }
    with open(session_path / "transcript.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def build_summary_report(project, transcript, summary_text, summary_source_label="Bilinmiyor"):
    """Ozet (kim cikardi) + tur tur tartisma dokumu tek bir Markdown metninde."""
    lines = [
        "# Ozet ve Plan",
        "",
        f"**Konu:** {project}",
        f"**Ozeti cikaran:** {summary_source_label}",
        f"**Tarih:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
        summary_text,
        "",
        "---",
        "",
        "## Tur Tur Tartisma",
        "",
    ]

    grouped = {}
    order = []
    for entry in transcript:
        key = entry.get("round") or 0
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(entry)

    for key in sorted(order, key=lambda k: (k == 0, k)):
        title = "Ek Notlar" if key == 0 else f"Tur {key}"
        lines.append(f"### {title}")
        lines.append("")
        for entry in grouped[key]:
            model_txt = f" — {entry['model']}" if entry.get("model") else ""
            lines.append(f"**{entry['speaker']}{model_txt}:**")
            lines.append("")
            lines.append(entry["text"])
            lines.append("")

    return "\n".join(lines)


def save_summary_md(session_path, project, transcript, summary, summary_source_label="Bilinmiyor"):
    content = build_summary_report(project, transcript, summary, summary_source_label)
    with open(session_path / "ozet.md", "w", encoding="utf-8") as f:
        f.write(content)
