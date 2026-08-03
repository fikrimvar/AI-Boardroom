import sys
import queue
import os
import shutil
import json
import markdown as md_lib
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QTextEdit, QTextBrowser, QPushButton, QComboBox, QScrollArea,
    QGroupBox, QFormLayout, QSpinBox, QMessageBox, QTabWidget,
    QListWidget, QFileDialog, QAbstractItemView, QFrame, QCheckBox
)

from config import load_config, save_config, SESSIONS_DIR
from orchestrator import DiscussionWorker
from session_log import new_session_dir, save_transcript_json, save_summary_md, build_summary_report

# --- SABİT VERİLER ---
PROVIDER_OPTIONS = ["anthropic", "openai", "gemini", "groq", "openrouter"]

# Model Listesi (Sağlayıcıya göre dinamik güncellenir)
MODEL_MAPS = {
    "openrouter": [
        "google/gemma-2-9b-it:free", 
        "google/gemini-flash-1.5-exp:free",
        "meta-llama/llama-3.1-8b-instruct:free", 
        "mistralai/pixtral-12b:free",
        "qwen/qwen-2-7b-instruct:free", 
        "nvidia/nemotron-4-340b-instruct:free",
        "microsoft/phi-3-medium-128k-instruct:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free"
    ],
    "openai": ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
    "gemini": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash-exp", "gemini-2.0-flash"],
    "groq": ["llama-3.1-70b-versatile", "mixtral-8x7b-32768", "llama-3.3-70b-versatile"],
    "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"]
}

COLORS = ["#378ADD", "#D85A30", "#1D9E75", "#7F77DD", "#B3307E"]

PERSONA_TEMPLATES = {
    "Özel (Serbest)": {"name": "", "role": ""},
    "Mimar (Kodlama)": {"name": "Mimar", "role": "Sistem mimarı, performans ve veritabanı uzmanı. Sağlam altyapı tasarlar."},
    "Eleştirmen (Analiz)": {"name": "Eleştirmen", "role": "Kritik yaklaşım sergileyen, güvenlik açıklarını ve mantık hatalarını yakalayan uzman."},
    "Ürün-UX (Tasarım)": {"name": "Ürün-UX", "role": "Kullanıcı deneyimi, akış hızı ve işlevsellik odaklı ürün yöneticisi."},
    "Sanatçı (Görsel)": {"name": "Sanatçı", "role": "Estetik, renk teorisi ve görsel kompozisyon uzmanı."},
    "Yazar (İçerik)": {"name": "Yazar", "role": "Etkili iletişim, marka dili ve metin akıcılığı konusunda uzman."}
}

class PersonaRow(QFrame):
    """Her bir katılımcının (Persona) ayar satırı"""
    def __init__(self, persona, color, remove_cb, up_cb, down_cb):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.color = color
        self.remove_cb = remove_cb
        self.up_cb = up_cb
        self.down_cb = down_cb

        layout = QFormLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.template_combo = QComboBox()
        self.template_combo.addItems(list(PERSONA_TEMPLATES.keys()))
        self.template_combo.currentIndexChanged.connect(self.on_template_changed)

        self.name_input = QLineEdit(persona.get("name", ""))
        self.role_input = QLineEdit(persona.get("role", ""))
        
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(PROVIDER_OPTIONS)
        self.provider_combo.setCurrentText(persona.get("provider", "openai"))
        self.provider_combo.currentTextChanged.connect(self.update_models)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        
        self.sees_context_cb = QCheckBox("Kod Bağlamını Görsün")
        self.sees_context_cb.setChecked(persona.get("sees_context", False))

        self.update_models(self.provider_combo.currentText())
        self.model_combo.setCurrentText(persona.get("model", ""))

        header_layout = QHBoxLayout()
        self.name_label = QLabel(f"● Katılımcı")
        self.name_label.setStyleSheet(f"color:{color}; font-weight:bold;")
        
        self.up_btn = QPushButton("▲")
        self.up_btn.setFixedWidth(30)
        self.up_btn.clicked.connect(lambda: self.up_cb(self))
        
        self.down_btn = QPushButton("▼")
        self.down_btn.setFixedWidth(30)
        self.down_btn.clicked.connect(lambda: self.down_cb(self))
        
        self.remove_btn = QPushButton("Sil")
        self.remove_btn.setFixedWidth(50)
        self.remove_btn.clicked.connect(lambda: self.remove_cb(self))

        header_layout.addWidget(self.name_label)
        header_layout.addStretch()
        header_layout.addWidget(self.up_btn)
        header_layout.addWidget(self.down_btn)
        header_layout.addWidget(self.remove_btn)

        layout.addRow(header_layout)
        layout.addRow("Şablon:", self.template_combo)
        layout.addRow("İsim:", self.name_input)
        layout.addRow("Rol/Bakış Açısı:", self.role_input)
        layout.addRow("Sağlayıcı:", self.provider_combo)
        layout.addRow("Model:", self.model_combo)
        layout.addRow(self.sees_context_cb)

    def update_models(self, prov):
        self.model_combo.clear()
        self.model_combo.addItems(MODEL_MAPS.get(prov, []))

    def on_template_changed(self):
        tmpl = self.template_combo.currentText()
        if tmpl in PERSONA_TEMPLATES and tmpl != "Özel (Serbest)":
            self.name_input.setText(PERSONA_TEMPLATES[tmpl]["name"])
            self.role_input.setText(PERSONA_TEMPLATES[tmpl]["role"])

    def to_dict(self):
        return {
            "name": self.name_input.text().strip(),
            "role": self.role_input.text().strip(),
            "provider": self.provider_combo.currentText(),
            "model": self.model_combo.currentText(),
            "sees_context": self.sees_context_cb.isChecked()
        }

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI-Boardroom v2 (Agentic & Context Aware)")
        self.resize(1100, 850)

        self.cfg = load_config()
        self.pending_user_msgs = queue.Queue()
        self.worker = None
        self.session_dir = None
        self.context_data = ""

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.setup_boardroom_tab()
        self.setup_summary_tab()
        self.setup_history_tab()
        self.setup_settings_tab()
        self.load_history_list()

    def setup_boardroom_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        file_layout = QHBoxLayout()
        self.file_label = QLabel("Bağlam dosyası (kod vb.) yüklenmedi.")
        btn_load = QPushButton("Dosya Yükle (.md / .txt)")
        btn_load.clicked.connect(self.on_load_context)
        file_layout.addWidget(self.file_label)
        file_layout.addStretch()
        file_layout.addWidget(btn_load)
        layout.addLayout(file_layout)

        self.project_input = QTextEdit()
        self.project_input.setPlaceholderText("Tartışılacak konuyu veya ai-context özetini buraya girin...")
        self.project_input.setMaximumHeight(80)
        layout.addWidget(self.project_input)

        self.transcript_view = QTextBrowser()
        layout.addWidget(self.transcript_view)

        self.status_label = QLabel("Hazır.")
        layout.addWidget(self.status_label)

        input_row = QHBoxLayout()
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("Araya girmek için mesajınızı yazın...")
        self.user_input.returnPressed.connect(self.on_send_user_msg)
        btn_send = QPushButton("Gönder")
        btn_send.clicked.connect(self.on_send_user_msg)
        input_row.addWidget(self.user_input)
        input_row.addWidget(btn_send)
        layout.addLayout(input_row)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Tartışmayı Başlat")
        self.start_btn.clicked.connect(self.on_start)
        self.continue_btn = QPushButton("Sonraki Tura Geç")
        self.continue_btn.clicked.connect(self.on_continue)
        self.continue_btn.setEnabled(False)
        self.stop_btn = QPushButton("Durdur")
        self.stop_btn.clicked.connect(self.on_stop)
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.continue_btn)
        btn_row.addWidget(self.stop_btn)
        layout.addLayout(btn_row)

        self.tabs.addTab(tab, "Tartışma Paneli")

    def on_load_context(self):
        path, _ = QFileDialog.getOpenFileName(self, "Bağlam Dosyası Seç", "", "Metin Dosyaları (*.txt *.md)")
        if path:
            with open(path, "r", encoding="utf-8") as f:
                self.context_data = f.read()
            self.file_label.setText(f"Yüklendi: {path.split('/')[-1]}")

    def setup_summary_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.summary_view = QTextBrowser()
        layout.addWidget(self.summary_view)
        
        btn_layout = QHBoxLayout()
        export_btn = QPushButton("Özeti Dışa Aktar (.md)")
        export_btn.clicked.connect(self.on_export_summary)
        btn_layout.addWidget(export_btn)
        layout.addLayout(btn_layout)
        
        self.tabs.addTab(tab, "Özet / Plan")

    def on_export_summary(self):
        path, _ = QFileDialog.getSaveFileName(self, "Kaydet", "ozet.md", "Markdown (*.md)")
        if path:
            # Widget'tan (.toPlainText()) değil, üretilen orijinal markdown
            # kaynağından yaz - render edilmiş içerikten geri çevirmek
            # tabloları/başlıkları bozuyordu.
            content = getattr(self, "last_full_report_md", None) or self.summary_view.toPlainText()
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

    def setup_history_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        
        left_panel = QVBoxLayout()
        self.history_list = QListWidget()
        self.history_list.currentItemChanged.connect(self.on_history_select)
        left_panel.addWidget(QLabel("Geçmiş Kayıtlar:"))
        left_panel.addWidget(self.history_list)
        
        del_btn = QPushButton("Seçili Kaydı Sil")
        del_btn.clicked.connect(self.on_delete_history)
        left_panel.addWidget(del_btn)
        
        self.history_view = QTextBrowser()
        layout.addLayout(left_panel, 1)
        layout.addWidget(self.history_view, 2)
        
        self.tabs.addTab(tab, "Geçmiş")

    def on_history_select(self, current, previous):
        if not current: return
        p = SESSIONS_DIR / current.text() / "ozet.md"
        if p.exists():
            self.history_view.setMarkdown(p.read_text(encoding="utf-8"))

    def on_delete_history(self):
        curr = self.history_list.currentItem()
        if curr and QMessageBox.question(self, "Onay", "Bu kaydı silmek istediğinize emin misiniz?") == QMessageBox.StandardButton.Yes:
            shutil.rmtree(SESSIONS_DIR / curr.text())
            self.load_history_list()

    def load_history_list(self):
        self.history_list.clear()
        if SESSIONS_DIR.exists():
            dirs = sorted([d.name for d in SESSIONS_DIR.iterdir() if d.is_dir()], reverse=True)
            self.history_list.addItems(dirs)

    def setup_settings_tab(self):
        tab = QWidget()
        main_layout = QVBoxLayout(tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.settings_layout = QVBoxLayout(content)

        # API Anahtarları
        api_group = QGroupBox("API Anahtarları")
        api_form = QFormLayout(api_group)
        self.key_inputs = {}
        for p in PROVIDER_OPTIONS:
            inp = QLineEdit(self.cfg["api_keys"].get(p, ""))
            inp.setEchoMode(QLineEdit.EchoMode.Password)
            self.key_inputs[p] = inp
            api_form.addRow(p.capitalize() + " API Key:", inp)
        self.settings_layout.addWidget(api_group)

        # Özet Ayarları
        summary_group = QGroupBox("Özet / Rapor Ayarları")
        summary_form = QFormLayout(summary_group)
        self.summary_provider_combo = QComboBox()
        self.summary_provider_combo.addItems(PROVIDER_OPTIONS)
        self.summary_provider_combo.setCurrentText(self.cfg.get("summary_provider", "gemini"))
        self.summary_provider_combo.currentTextChanged.connect(self.update_summary_models)
        
        self.summary_model_combo = QComboBox()
        self.summary_model_combo.setEditable(True)
        self.update_summary_models(self.summary_provider_combo.currentText())
        self.summary_model_combo.setCurrentText(self.cfg.get("summary_model", ""))
        
        summary_form.addRow("Özet Sağlayıcı:", self.summary_provider_combo)
        summary_form.addRow("Özet Modeli:", self.summary_model_combo)
        self.settings_layout.addWidget(summary_group)

        # Genel Ayarlar
        gen_group = QGroupBox("Genel Tartışma Ayarları")
        gen_form = QFormLayout(gen_group)
        self.rounds_spin = QSpinBox()
        self.rounds_spin.setRange(1, 10)
        self.rounds_spin.setValue(self.cfg.get("rounds", 2))
        gen_form.addRow("Tartışma Tur Sayısı:", self.rounds_spin)
        self.settings_layout.addWidget(gen_group)

        # Katılımcılar
        self.persona_group = QGroupBox("Katılımcılar (Sıralama Toplantı Akışını Belirler)")
        self.persona_layout = QVBoxLayout(self.persona_group)
        self.persona_rows = []
        for p in self.cfg.get("personas", []):
            self.add_persona_row(p)
        self.settings_layout.addWidget(self.persona_group)

        btn_add = QPushButton("+ Yeni Katılımcı Ekle")
        btn_add.clicked.connect(lambda: self.add_persona_row())
        self.settings_layout.addWidget(btn_add)

        save_btn = QPushButton("Ayarları Kaydet")
        save_btn.setFixedHeight(40)
        save_btn.setStyleSheet("font-weight: bold; background-color: #2e7d32; color: white;")
        save_btn.clicked.connect(self.on_save_settings)
        
        scroll.setWidget(content)
        main_layout.addWidget(scroll)
        main_layout.addWidget(save_btn)
        self.tabs.addTab(tab, "Ayarlar")

    def update_summary_models(self, prov):
        self.summary_model_combo.clear()
        self.summary_model_combo.addItems(MODEL_MAPS.get(prov, []))

    def add_persona_row(self, data=None):
        data = data or {"name": "Yeni Uzman", "role": "", "provider": "openai", "model": "gpt-4o-mini"}
        row = PersonaRow(data, COLORS[len(self.persona_rows)%len(COLORS)], self.remove_row, self.move_up, self.move_down)
        self.persona_rows.append(row)
        self.persona_layout.addWidget(row)

    def remove_row(self, r):
        if len(self.persona_rows) > 1:
            self.persona_layout.removeWidget(r)
            self.persona_rows.remove(r)
            r.deleteLater()

    def move_up(self, r):
        idx = self.persona_rows.index(r)
        if idx > 0:
            self.persona_rows.insert(idx-1, self.persona_rows.pop(idx))
            self.persona_layout.insertWidget(idx-1, r)

    def move_down(self, r):
        idx = self.persona_rows.index(r)
        if idx < len(self.persona_rows)-1:
            self.persona_rows.insert(idx+1, self.persona_rows.pop(idx))
            self.persona_layout.insertWidget(idx+1, r)

    def on_save_settings(self):
        for p in PROVIDER_OPTIONS:
            self.cfg["api_keys"][p] = self.key_inputs[p].text().strip()
        self.cfg["summary_provider"] = self.summary_provider_combo.currentText()
        self.cfg["summary_model"] = self.summary_model_combo.currentText()
        self.cfg["rounds"] = self.rounds_spin.value()
        self.cfg["personas"] = [row.to_dict() for row in self.persona_rows]
        save_config(self.cfg)
        QMessageBox.information(self, "Başarılı", "Ayarlar başarıyla kaydedildi.")

    def append_message(self, d):
        speaker_color = COLORS[0]
        for row in self.persona_rows:
            if row.name_input.text() == d['speaker']:
                speaker_color = row.color
                break

        # d['text'] modelin ham Markdown çıktısı - tablo, başlık, kalın yazı
        # içerebilir. Bunu doğrudan HTML'e gömmek "**" ve "|" karakterlerinin
        # olduğu gibi görünmesine yol açıyordu; gerçek HTML'e çevirip basıyoruz.
        body_html = md_lib.markdown(d['text'], extensions=['tables', 'fenced_code'])
        html = (
            f"<p><b style='color:{speaker_color}'>{d['speaker']}</b> (Tur {d['round']}):</p>"
            f"{body_html}<hr>"
        )
        self.transcript_view.append(html)

    def on_send_user_msg(self):
        txt = self.user_input.text().strip()
        if txt:
            self.pending_user_msgs.put(txt)
            self.transcript_view.append(f"<p><b>Sen:</b> {txt}</p><hr>")
            self.user_input.clear()

    def on_start(self):
        """Tartışmayı başlat"""
        self.on_save_settings()
        proj = self.project_input.toPlainText().strip()
        if not proj:
            QMessageBox.warning(self, "Hata", "Lütfen bir proje konusu girin.")
            return
        
        self.transcript_view.clear()
        self.summary_view.clear()
        self.session_dir = new_session_dir(proj)
        
        self.worker = DiscussionWorker(
            proj, self.cfg["personas"], self.cfg["rounds"], self.cfg["api_keys"],
            self.pending_user_msgs, self.cfg["summary_provider"], self.cfg["summary_model"], self.context_data
        )
        self.worker.message_ready.connect(self.append_message)
        self.worker.status.connect(self.status_label.setText)
        self.worker.finished_all.connect(self.on_finished)
        self.worker.round_paused.connect(lambda: self.continue_btn.setEnabled(True))
        self.worker.error.connect(self.on_worker_error)
        
        self.worker.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def on_worker_error(self, msg):
        """Worker'dan gelen hata mesajlarını göster"""
        self.transcript_view.append(f"<p style='color: orange;'><b>⚠️ Sistem:</b> {msg}</p>")
        self.status_label.setText(f"⚠️ {msg}")

    def on_continue(self):
        """Sonraki tura geç"""
        self.continue_btn.setEnabled(False)
        if self.worker:
            self.worker.resume()

    def on_stop(self):
        """Tartışmayı durdur"""
        if self.worker:
            self.worker.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def on_finished(self, summary, transcript, source):
        """Tartışma bitti"""
        proj_text = self.project_input.toPlainText()
        # Ekranda da diske kaydedilenle aynı şeyi göster: özet + tur tur
        # tartışma dökümü.
        full_report = build_summary_report(proj_text, transcript, summary, source)
        # Ham markdown kaynağını sakla - "Dışa Aktar" butonu bunu kullanacak.
        # self.summary_view.toPlainText()/.toMarkdown() render edilmiş
        # içerikten geri çevirdiği için tabloları/başlıkları bozabiliyor;
        # üretilen orijinal metni saklamak bunu önlüyor.
        self.last_full_report_md = full_report
        self.summary_view.setMarkdown(full_report)
        save_transcript_json(self.session_dir, proj_text, transcript)
        save_summary_md(self.session_dir, proj_text, transcript, summary, source)
        self.load_history_list()
        self.tabs.setCurrentIndex(1)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.continue_btn.setEnabled(False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())