import queue
from PyQt6.QtCore import QThread, pyqtSignal
from google import genai
from anthropic import Anthropic
from openai import OpenAI

class DiscussionWorker(QThread):
    message_ready = pyqtSignal(dict)
    status = pyqtSignal(str)
    round_paused = pyqtSignal(int)
    finished_all = pyqtSignal(str, list)
    error = pyqtSignal(str)

    def __init__(self, project, personas, rounds, api_keys, pending_user_msgs):
        super().__init__()
        self.project = project
        self.personas = personas
        self.rounds = rounds
        self.api_keys = api_keys
        self.pending_user_msgs = pending_user_msgs
        self.is_running = True
        self.is_paused = False
        self.transcript = []

    def run(self):
        try:
            self.status.emit("Tartışma başlatılıyor...")
            history_context = []

            for r in range(1, self.rounds + 1):
                if not self.is_running:
                    break
                
                self.status.emit(f"Tur {r} yürütülüyor...")
                
                for p in self.personas:
                    if not self.is_running:
                        break
                    
                    while not self.pending_user_msgs.empty():
                        u_msg = self.pending_user_msgs.get_nowait()
                        entry = {"speaker": "Sen", "round": r, "text": u_msg}
                        self.transcript.append(entry)
                        self.message_ready.emit(entry)
                        history_context.append(f"Sen (Kullanıcı): {u_msg}")

                    resp_text = self.call_llm(p, history_context, r)
                    entry = {"speaker": p["name"], "round": r, "text": resp_text}
                    self.transcript.append(entry)
                    self.message_ready.emit(entry)
                    history_context.append(f"{p['name']} ({p['role']}): {resp_text}")

                if not self.is_running:
                    break

                if r < self.rounds:
                    self.round_paused.emit(r)
                    self.is_paused = True
                    while self.is_paused and self.is_running:
                        self.msleep(100)

            if not self.is_running:
                return

            while not self.pending_user_msgs.empty():
                u_msg = self.pending_user_msgs.get_nowait()
                entry = {"speaker": "Sen", "round": 0, "text": u_msg}
                self.transcript.append(entry)
                self.message_ready.emit(entry)
                history_context.append(f"Sen (Kullanıcı): {u_msg}")

            self.status.emit("Nihai özet ve plan raporu hazırlanıyor...")
            summary = self.synthesize(history_context)
            self.finished_all.emit(summary, self.transcript)

        except Exception as e:
            self.error.emit(str(e))

    def resume(self):
        self.is_paused = False

    def stop(self):
        self.is_running = False
        self.is_paused = False

    def generate_summary_only(self):
        history_context = []
        for entry in self.transcript:
            speaker = entry["speaker"]
            text = entry["text"]
            history_context.append(f"{speaker}: {text}")
        return self.synthesize(history_context)

    def call_llm(self, persona, history, current_round):
        prov = persona["provider"]
        model = persona["model"]
        key = self.api_keys.get(prov, "")
        name = persona["name"]
        role = persona["role"]

        sys_prompt = (
            f"Sen planlama ve tartışma kurulunda görev yapan bir uzmansın.\n"
            f"Adın: {name}\n"
            f"Rolün ve Bakış Açın: {role}\n"
            f"Konu/Proje: {self.project}\n\n"
            f"Kurallar:\n"
            f"1. Kesinlikle rolüne sadık kal.\n"
            f"2. Önceki konuşmaları dikkate alarak yapıcı ve doğrudan eleştiriler/katkılar sun.\n"
            f"3. Gereksiz dolgu kelimelerden kaçın, net ve somut önerilerde bulun."
        )

        hist_str = "\n".join(history) if history else "Henüz tartışma yeni başlıyor. İlk fikirleri sen sun."
        prompt = f"Şu ana kadarki tartışma geçmişi:\n{hist_str}\n\nLütfen {current_round}. tur için görüşünü belirt."

        if prov == "gemini":
            client = genai.Client(api_key=key) if key else genai.Client()
            response = client.models.generate_content(
                model=model if model else "gemini-2.0-flash",
                contents=prompt,
                config={"system_instruction": sys_prompt}
            )
            return response.text

        elif prov == "anthropic":
            client = Anthropic(api_key=key)
            response = client.messages.create(
                model=model if model else "claude-3-5-sonnet-20241022",
                max_tokens=1024,
                system=sys_prompt,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text

        elif prov in ["openai", "groq", "openrouter"]:
            base_urls = {
                "openai": None,
                "groq": "https://api.groq.com/openai/v1",
                "openrouter": "https://openrouter.ai/api/v1"
            }
            default_models = {
                "openai": "gpt-4o-mini",
                "groq": "llama-3.3-70b-versatile",
                "openrouter": "deepseek/deepseek-chat"
            }
            client = OpenAI(api_key=key, base_url=base_urls.get(prov))
            response = client.chat.completions.create(
                model=model if model else default_models[prov],
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content

        else:
            raise ValueError(f"Bilinmeyen sağlayıcı: {prov}")

    def synthesize(self, history):
        key = self.api_keys.get("gemini", "") or self.api_keys.get("openai", "")
        hist_str = "\n".join(history)
        prompt = (
            f"Aşağıdaki tartışma transkriptini incele ve profesyonel bir Özet çıkar.\n\n"
            f"Konu: {self.project}\n\n"
            f"Transkript:\n{hist_str}\n\n"
            f"Lütfen şu formatta Markdown raporu oluştur:\n"
            f"1. **Üzerinde Mutabık Kalınan Kararlar**\n"
            f"2. **Hâlâ Tartışmalı / Açık Kalan Noktalar**\n"
            f"3. **Somut Sonraki Adımlar ve Yol Haritası**"
        )
        try:
            if self.api_keys.get("gemini"):
                client = genai.Client(api_key=self.api_keys.get("gemini"))
                res = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                return res.text
            elif self.api_keys.get("openai"):
                client = OpenAI(api_key=self.api_keys.get("openai"))
                res = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                return res.choices[0].message.content
            else:
                client = genai.Client()
                res = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                return res.text
        except Exception as e:
            return f"Özet oluşturulamadı: {str(e)}"
