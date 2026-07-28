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

def save_summary_md(session_path, project, transcript, summary):
    content = f"# Tartışma Özeti\n\n**Konu:** {project}\n**Tarih:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n---\n\n{summary}\n"
    with open(session_path / "ozet.md", "w", encoding="utf-8") as f:
        f.write(content)
