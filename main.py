import sys
import queue
import os
import shutil
import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QTextEdit, QTextBrowser, QPushButton, QComboBox, QScrollArea,
    QGroupBox, QFormLayout, QSpinBox, QMessageBox, QTabWidget,
    QListWidget, QFileDialog, QAbstractItemView, QFrame
)

from config import load_config, save_config, SESSIONS_DIR
from orchestrator import DiscussionWorker
from session_log import new_session_dir, save_transcript_json, save_summary_md

PROVIDER_OPTIONS = ["anthropic", "openai", "gemini", "groq", "openrouter"]
PROVIDER_LABELS = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI (GPT)",
    "gemini": "Google (Gemini)",
    "groq": "Groq (Llama vb.)",
    "openrouter": "OpenRouter (Çeşitli)"
}
COLORS = ["#378ADD", "#D85A30", "#1D9E75", "#7F77DD", "#B3307E"]

PERSONA_TEMPLATES = {
    "Özel (Serbest)": {"name": "", "role": ""},
    "Mimar (Kodlama)": {"name": "Mimar", "role": "Sistem mimarı, performans ve veritabanı uzmanı. Sağlam altyapı tasarlar."},
    "Eleştirmen (Analiz)": {"name": "Eleştirmen", "role": "Kritik yaklaşım sergileyen, güvenlik açıklarını ve mantık hatalarını yakalayan uzman."},
    "Ürün-UX (Tasarım)": {"name": "Ürün-UX", "role": "Kullanıcı deneyimi, akış hızı ve işlevsellik odaklı ürün yöneticisi."},
    "Sanatçı (Görsel)": {"name": "Sanatçı", "role": "Estetik, renk teorisi ve görsel kompozisyon uzmanı. Görsel kaliteyi artırır."},
    "Müzisyen (Ses)": {"name": "Müzisyen", "role": "Ses tasarımı, ritim ve işitsel uyum konusunda uzman."},
    "Yazar (İçerik)": {"name": "Yazar", "role": "Etkili iletişim, marka dili ve metin akıcılığı konusunda uzman."}
}

class PersonaRow(QFrame):
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
        for p in PROVIDER_OPTIONS:
            self.provider_combo.addItem(PROVIDER_LABELS[p], p)
        idx = PROVIDER_OPTIONS.index(persona.get("provider", "openai")) if persona.get("provider") in PROVIDER_OPTIONS else 0
        self.provider_combo.setCurrentIndex(idx)
        self.model_input = QLineEdit(persona.get("model", ""))

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
        layout.addRow("Şablon (Alan):", self.template_combo)
        layout.addRow("İsim:", self.name_input)
        layout.addRow("Rol/Bakış Açısı:", self.role_input)
        layout.addRow("Sağlayıcı:", self.provider_combo)
        layout.addRow("Model:", self.model_input)

    def on_template_changed(self):
        tmpl = self.template_combo.currentText()
        if tmpl in PERSONA_TEMPLATES and tmpl != "Özel (Serbest)":
            self.name_input.setText(PERSONA_TEMPLATES[tmpl]["name"])
            self.role_input.setText(PERSONA_TEMPLATES[tmpl]["role"])

    def to_dict(self):
        return {
            "name": self.name_input.text().strip() or "İsimsiz",
            "role": self.role_input.text().strip(),
            "provider": self.provider_combo.currentData(),
            "model": self.model_input.text().strip(),
        }

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI-Boardroom")
        self.resize(1000, 750)

        self.cfg = load_config()
        self.pending_user_msgs = queue.Queue()
        self.worker = None
        self.session_dir = None
        self.last_summary_md = ""

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
        
        top_row = QHBoxLayout()
        self.project_input = QTextEdit()
        self.project_input.setPlaceholderText("Tartışılacak konuyu veya projeyi kısaca anlat...")
        self.project_input.setMaximumHeight(60)
        top_row.addWidget(self.project_input)
        
        layout.addLayout(top_row)

        self.transcript_view = QTextBrowser()
        layout.addWidget(self.transcript_view)

        self.status_label = QLabel("Hazır.")
        layout.addWidget(self.status_label)

        input_row = QHBoxLayout()
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("İstediğin an araya girip yazabilirsin...")
        self.user_input.returnPressed.connect(self.on_send_user_msg)
        send_btn = QPushButton("Gönder")
        send_btn.clicked.connect(self.on_send_user_msg)
        input_row.addWidget(self.user_input)
        input_row.addWidget(send_btn)
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

    def setup_summary_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Üst kısım: Özet Çıkaracak Model Seçimi
        selection_layout = QHBoxLayout()
        selection_layout.addWidget(QLabel("<b>Özet Çıkaracak Sağlayıcı:</b>"))
        
        self.summary_provider_combo = QComboBox()
        for p in PROVIDER_OPTIONS:
            self.summary_provider_combo.addItem(PROVIDER_LABELS[p], p)
        selection_layout.addWidget(self.summary_provider_combo)
        
        selection_layout.addWidget(QLabel("Model:"))
        self.summary_model_input = QLineEdit()
        self.summary_model_input.setPlaceholderText("Boş bırakılırsa varsayılan kullanılır")
        selection_layout.addWidget(self.summary_model_input)
        
        layout.addLayout(selection_layout)

        self.summary_view = QTextBrowser()
        layout.addWidget(self.summary_view)
        
        btn_row = QHBoxLayout()
        self.retry_summary_btn = QPushButton("Özeti Yeniden Oluştur")
        self.retry_summary_btn.clicked.connect(self.on_retry_summary)
        btn_row.addWidget(self.retry_summary_btn)
        
        self.export_btn = QPushButton("Özeti Dışa Aktar (.md)")
        self.export_btn.clicked.connect(self.on_export_md)
        btn_row.addWidget(self.export_btn)
        
        layout.addLayout(btn_row)
        self.tabs.addTab(tab, "Özet / Plan")

    def setup_history_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.history_list = QListWidget()
        self.history_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.history_list.currentItemChanged.connect(self.on_history_select)
        left_layout.addWidget(QLabel("Birden fazla seçim yapabilirsiniz (Ctrl/Shift):"))
        left_layout.addWidget(self.history_list)
        
        self.delete_history_btn = QPushButton("Seçili Kayıtları Sil")
        self.delete_history_btn.clicked.connect(self.on_delete_history)
        left_layout.addWidget(self.delete_history_btn)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.history_view = QTextBrowser()
        right_layout.addWidget(self.history_view)
        
        self.export_history_btn = QPushButton("Geçmişi Dışa Aktar (.md)")
        self.export_history_btn.clicked.connect(self.on_export_history_md)
        right_layout.addWidget(self.export_history_btn)
        
        layout.addWidget(left_widget, 1)
        layout.addWidget(right_widget, 2)
        
        self.tabs.addTab(tab, "Geçmiş Kayıtlar")

    def setup_settings_tab(self):
        tab = QWidget()
        main_layout = QVBoxLayout(tab)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)

        api_group = QGroupBox("API Anahtarları")
        api_form = QFormLayout(api_group)
        self.key_inputs = {}
        for prov in PROVIDER_OPTIONS:
            inp = QLineEdit(self.cfg["api_keys"].get(prov, ""))
            inp.setEchoMode(QLineEdit.EchoMode.Password)
            self.key_inputs[prov] = inp
            api_form.addRow(PROVIDER_LABELS[prov] + ":", inp)
        layout.addWidget(api_group)

        general_group = QGroupBox("Genel Ayarlar")
        general_layout = QHBoxLayout(general_group)
        general_layout.addWidget(QLabel("Tur Sayısı:"))
        self.rounds_spin = QSpinBox()
        self.rounds_spin.setRange(1, 10)
        self.rounds_spin.setValue(self.cfg.get("rounds", 2))
        general_layout.addWidget(self.rounds_spin)
        general_layout.addStretch()
        layout.addWidget(general_group)

        self.persona_group = QGroupBox("Katılımcılar (Sıralamayı Yukarı/Aşağı Butonlarıyla Değiştirin)")
        self.persona_layout = QVBoxLayout(self.persona_group)
        
        self.persona_rows = []
        for p in self.cfg.get("personas", []):
            self.add_persona_row(p)
            
        layout.addWidget(self.persona_group)

        btn_layout = QHBoxLayout()
        add_persona_btn = QPushButton("+ Yeni Katılımcı Ekle")
        add_persona_btn.clicked.connect(lambda: self.add_persona_row())
        
        info_btn = QPushButton("ℹ️ Sıralama Stratejileri (Tavsiye)")
        info_btn.setStyleSheet("color: #2b78e4; font-weight: bold;")
        info_btn.clicked.connect(self.show_sorting_info)
        
        btn_layout.addWidget(add_persona_btn)
        btn_layout.addWidget(info_btn)
        
        layout.addLayout(btn_layout)

        save_btn = QPushButton("Ayarları Kaydet")
        save_btn.setStyleSheet("font-weight: bold; padding: 10px; margin-top: 15px;")
        save_btn.clicked.connect(self.on_save_settings)
        layout.addWidget(save_btn)
        
        layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        
        self.tabs.addTab(tab, "Ayarlar")

    def show_sorting_info(self):
        info_text = """Yapay zeka modelleri 'Çıpalama Etkisi' (Anchoring Effect) ile çalışır. İlk konuşan model, tartışmanın sınırlarını ve ana odağını belirler.

🛠️ Mühendislik ve Yazılım Projeleri İçin:
1. Mimar (Temeli atar)
2. Eleştirmen (Açıkları bulur)
3. Ürün-UX (Kullanıcıya uyarlar)

🎨 Tasarım ve İçerik Projeleri İçin:
1. Yazar / Sanatçı (Vizyonu belirler)
2. Ürün-UX (Akışı planlar)
3. Eleştirmen (Hataları arar)

💡 Unutmayın: Toplantının 'başkanı' her zaman 1. sıradaki kişidir!"""
        QMessageBox.information(self, "En Verimli Sıralama Stratejileri", info_text)

    def add_persona_row(self, persona_data=None):
        if len(self.persona_rows) >= 5:
            QMessageBox.warning(self, "Uyarı", "Maksimum 5 katılımcı ekleyebilirsiniz.")
            return
        
        if not persona_data:
            persona_data = {"name": "Yeni Katılımcı", "role": "", "provider": "openai", "model": "gpt-4o-mini"}
            
        color = COLORS[len(self.persona_rows) % len(COLORS)]
        row = PersonaRow(persona_data, color, self.remove_persona_row, self.move_persona_up, self.move_persona_down)
        self.persona_rows.append(row)
        self.persona_layout.addWidget(row)
        self.update_row_buttons()

    def remove_persona_row(self, row_widget):
        if len(self.persona_rows) <= 1:
            QMessageBox.warning(self, "Uyarı", "En az 1 katılımcı olmalıdır.")
            return
        self.persona_layout.removeWidget(row_widget)
        self.persona_rows.remove(row_widget)
        row_widget.deleteLater()
        self.update_row_buttons()

    def move_persona_up(self, row_widget):
        idx = self.persona_rows.index(row_widget)
        if idx > 0:
            self.persona_rows.insert(idx - 1, self.persona_rows.pop(idx))
            self.persona_layout.insertWidget(idx - 1, row_widget)
            self.update_row_buttons()

    def move_persona_down(self, row_widget):
        idx = self.persona_rows.index(row_widget)
        if idx < len(self.persona_rows) - 1:
            self.persona_rows.insert(idx + 1, self.persona_rows.pop(idx))
            self.persona_layout.insertWidget(idx + 1, row_widget)
            self.update_row_buttons()

    def update_row_buttons(self):
        can_remove = len(self.persona_rows) > 1
        for i, row in enumerate(self.persona_rows):
            row.remove_btn.setEnabled(can_remove)
            row.up_btn.setEnabled(i > 0)
            row.down_btn.setEnabled(i < len(self.persona_rows) - 1)
            row.color = COLORS[i % len(COLORS)]
            row.name_label.setStyleSheet(f"color:{row.color}; font-weight:bold;")

    def load_history_list(self):
        self.history_list.clear()
        self.history_view.clear()
        if not SESSIONS_DIR.exists():
            return
        dirs = sorted([d for d in SESSIONS_DIR.iterdir() if d.is_dir()], reverse=True)
        for d in dirs:
            self.history_list.addItem(d.name)

    def on_history_select(self, current, previous):
        if not current:
            return
        session_name = current.text()
        md_path = SESSIONS_DIR / session_name / "ozet.md"
        json_path = SESSIONS_DIR / session_name / "transcript.json"
        
        content = ""
        if md_path.exists():
            try:
                content += md_path.read_text(encoding="utf-8")
            except Exception:
                pass
                
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    transcript = data.get("transcript", [])
                    if transcript:
                        content += "\n\n---\n\n## Konuşma Geçmişi\n\n"
                        for entry in transcript:
                            rnd = f" (Tur {entry['round']})" if entry['round'] else ""
                            content += f"**{entry['speaker']}**{rnd}:\n{entry['text']}\n\n"
            except Exception:
                pass
                
        if not content:
            content = "Kayıt bulunamadı veya okunamadı."
            
        self.history_view.setMarkdown(content)

    def on_delete_history(self):
        selected_items = self.history_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Uyarı", "Silmek için listeden kayıt seçmelisiniz.")
            return
            
        count = len(selected_items)
        reply = QMessageBox.question(
            self, "Kayıt Silme Onayı", 
            f"Seçili {count} kayıt tamamen silinecek. Emin misiniz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            for item in selected_items:
                session_name = item.text()
                session_path = SESSIONS_DIR / session_name
                try:
                    if session_path.exists() and session_path.is_dir():
                        shutil.rmtree(session_path)
                except Exception:
                    pass
            self.load_history_list()
            self.history_view.clear()

    def on_export_history_md(self):
        current = self.history_list.currentItem()
        if not current:
            return
            
        session_name = current.text()
        content = self.history_view.toPlainText()
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Geçmişi Kaydet", 
            f"{session_name}_tam_kayit.md", 
            "Markdown Dosyaları (*.md);;Tüm Dosyalar (*)"
        )
        
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception:
                pass

    def on_export_md(self):
        if not self.last_summary_md:
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Özeti Kaydet", "", 
            "Markdown Dosyaları (*.md);;Tüm Dosyalar (*)"
        )
        
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.last_summary_md)
            except Exception:
                pass

    def on_save_settings(self):
        for prov in PROVIDER_OPTIONS:
            self.cfg["api_keys"][prov] = self.key_inputs[prov].text().strip()
        self.cfg["rounds"] = self.rounds_spin.value()
        self.cfg["personas"] = [row.to_dict() for row in self.persona_rows]
        save_config(self.cfg)
        QMessageBox.information(self, "Başarılı", "Ayarlar kaydedildi.")

    def append_message(self, entry):
        idx_map = {row.to_dict()["name"]: i for i, row in enumerate(self.persona_rows)}
        color = "#888888"
        if entry["speaker"] == "Sen":
            color = "#444444"
        elif entry["speaker"] in idx_map:
            color = COLORS[idx_map[entry["speaker"]] % len(COLORS)]
        round_txt = f"Tur {entry['round']}" if entry["round"] else ""
        html = (
            f"<p><b style='color:{color}'>{entry['speaker']}</b> "
            f"<span style='color:#999; font-size:11px'>{round_txt}</span><br>"
            f"{entry['text'].replace(chr(10), '<br>')}</p><hr>"
        )
        self.transcript_view.append(html)

    def on_send_user_msg(self):
        text = self.user_input.text().strip()
        if not text:
            return
        self.pending_user_msgs.put(text)
        self.append_message({"speaker": "Sen", "round": 0, "text": text})
        self.user_input.clear()

    def on_start(self):
        self.on_save_settings()
        project = self.project_input.toPlainText().strip()
        if not project:
            QMessageBox.warning(self, "Eksik bilgi", "Konu veya proje açıklaması giriniz.")
            return
        personas = [row.to_dict() for row in self.persona_rows]
        rounds = self.rounds_spin.value()

        self.transcript_view.clear()
        self.summary_view.clear()
        self.last_summary_md = ""
        self.session_dir = new_session_dir(project)

        while not self.pending_user_msgs.empty():
            try:
                self.pending_user_msgs.get_nowait()
            except queue.Empty:
                break

        self.worker = DiscussionWorker(
            project=project,
            personas=personas,
            rounds=rounds,
            api_keys=self.cfg["api_keys"],
            pending_user_msgs=self.pending_user_msgs,
        )
        self.worker.message_ready.connect(self.append_message)
        self.worker.status.connect(self.status_label.setText)
        self.worker.round_paused.connect(self.on_round_paused)
        self.worker.finished_all.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()

        self.start_btn.setEnabled(False)
        self.continue_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.tabs.setCurrentIndex(0)

    def on_round_paused(self, rnd):
        self.status_label.setText(f"Tur {rnd} tamamlandı. 'Sonraki Tura Geç' butonuna bas.")
        self.continue_btn.setEnabled(True)

    def on_continue(self):
        self.continue_btn.setEnabled(False)
        if self.worker:
            self.worker.resume()

    def on_stop(self):
        if self.worker:
            self.worker.stop()
        self.start_btn.setEnabled(True)
        self.continue_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Durduruldu.")

    def on_retry_summary(self):
        if not self.worker or not self.worker.transcript:
            QMessageBox.warning(self, "Uyarı", "Yeniden özet çıkarılacak geçmiş bulunamadı.")
            return
        
        # Eski hataları temizle ve kullanıcıya çalışıyor bilgisi ver
        self.summary_view.setMarkdown("### ⏳ Özet yeniden oluşturuluyor, lütfen bekleyin...")
        self.status_label.setText("Özet yeniden oluşturuluyor...")
        
        prov = self.summary_provider_combo.currentData()
        model = self.summary_model_input.text().strip()
        
        try:
            summary = self.worker.generate_summary_only(provider=prov, model=model)
            self.last_summary_md = summary
            self.summary_view.setMarkdown(summary)
            self.status_label.setText("Özet başarıyla oluşturuldu.")
            
            project = self.project_input.toPlainText().strip()
            if self.session_dir:
                save_summary_md(self.session_dir, project, self.worker.transcript, summary)
                self.load_history_list()
        except Exception as e:
            self.summary_view.setMarkdown(f"### ❌ Hata Oluştu:\n```text\n{str(e)}\n```")
            QMessageBox.critical(self, "Hata", f"Özet oluşturulamadı:\n{str(e)}")
            self.status_label.setText("Özet oluşturulamadı.")

    def on_finished(self, summary, transcript):
        self.last_summary_md = summary
        self.summary_view.setMarkdown(summary)
        self.tabs.setCurrentIndex(1)
        self.status_label.setText("Tamamlandı.")
        project = self.project_input.toPlainText().strip()
        
        save_transcript_json(self.session_dir, project, transcript)
        save_summary_md(self.session_dir, project, transcript, summary)
        
        self.load_history_list()
        
        self.start_btn.setEnabled(True)
        self.continue_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)

    def on_error(self, msg):
        QMessageBox.critical(self, "Hata", msg)
        self.status_label.setText("Hata oluştu.")
        self.start_btn.setEnabled(True)
        self.continue_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)

def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()