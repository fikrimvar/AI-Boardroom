import queue
import time

from PyQt6.QtCore import QThread, pyqtSignal

from google import genai
from anthropic import Anthropic
from openai import OpenAI

# --- Ayarlanabilir sabitler ---
CALL_DELAY_SECONDS = 3       # her API cagrisindan once bu kadar bekle (free-tier limitine takilmamak icin)
MAX_RETRIES = 2               # rate-limit hatasinda ayni saglayiciyi kac kez daha dene
RETRY_BACKOFF_SECONDS = 10    # yeniden denemeden once ek bekleme
SUMMARY_FALLBACK_ORDER = ["gemini", "groq", "openai", "anthropic", "openrouter"]

RATE_LIMIT_MARKERS = ["429", "rate limit", "ratelimit", "quota", "resource_exhausted", "resource exhausted"]

DEFAULT_MODELS = {
    "gemini": "gemini-2.0-flash",
    "anthropic": "claude-3-5-sonnet-20241022",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "deepseek/deepseek-chat",
}

PROVIDER_LABELS = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI (GPT)",
    "gemini": "Google (Gemini)",
    "groq": "Groq (Llama vb.)",
    "openrouter": "OpenRouter (Cesitli)",
}


class DiscussionWorker(QThread):
    message_ready = pyqtSignal(dict)
    status = pyqtSignal(str)
    round_paused = pyqtSignal(int)
    finished_all = pyqtSignal(str, list, str)
    error = pyqtSignal(str)

    def __init__(self, project, personas, rounds, api_keys, pending_user_msgs,
                 summary_provider=None, summary_model=None):
        super().__init__()
        self.project = project
        self.personas = personas
        self.rounds = rounds
        self.api_keys = api_keys
        self.pending_user_msgs = pending_user_msgs
        self.summary_provider = summary_provider
        self.summary_model = summary_model
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
                    model_used = p.get("model") or DEFAULT_MODELS.get(p["provider"], p["provider"])
                    entry = {
                        "speaker": p["name"],
                        "round": r,
                        "text": resp_text,
                        "provider": p["provider"],
                        "model": model_used,
                    }
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
            summary, used_prov, used_model = self.synthesize(
                history_context, provider=self.summary_provider, model=self.summary_model
            )
            source_label = f"{PROVIDER_LABELS.get(used_prov, used_prov)} · {used_model}"
            self.finished_all.emit(summary, self.transcript, source_label)
        except Exception as e:
            self.error.emit(str(e))

    def resume(self):
        self.is_paused = False

    def stop(self):
        self.is_running = False
        self.is_paused = False

    def generate_summary_only(self, provider=None, model=None):
        history_context = []
        for entry in self.transcript:
            history_context.append(f"{entry['speaker']}: {entry['text']}")
        provider = provider or self.summary_provider
        model = model or self.summary_model
        summary, used_prov, used_model = self.synthesize(history_context, provider=provider, model=model)
        source_label = f"{PROVIDER_LABELS.get(used_prov, used_prov)} · {used_model}"
        return summary, source_label

    # ------------------------------------------------------------------
    # Alt seviye: tek bir saglayiciya ham cagri
    # ------------------------------------------------------------------
    def _raw_call(self, prov, model, prompt, key, system_prompt=None):
        if prov == "gemini":
            client = genai.Client(api_key=key) if key else genai.Client()
            config = {"system_instruction": system_prompt} if system_prompt else {}
            response = client.models.generate_content(
                model=model if model else DEFAULT_MODELS["gemini"],
                contents=prompt,
                config=config,
            )
            return response.text

        elif prov == "anthropic":
            client = Anthropic(api_key=key)
            kwargs = {
                "model": model if model else DEFAULT_MODELS["anthropic"],
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                kwargs["system"] = system_prompt
            response = client.messages.create(**kwargs)
            return response.content[0].text

        elif prov in ["openai", "groq", "openrouter"]:
            base_urls = {
                "openai": None,
                "groq": "https://api.groq.com/openai/v1",
                "openrouter": "https://openrouter.ai/api/v1",
            }
            client = OpenAI(api_key=key, base_url=base_urls.get(prov))
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(
                model=model if model else DEFAULT_MODELS[prov],
                messages=messages,
            )
            return response.choices[0].message.content

        else:
            raise ValueError(f"Bilinmeyen sağlayıcı: {prov}")

    # ------------------------------------------------------------------
    # Orta seviye: gecikme + rate-limit'te otomatik yeniden deneme
    # ------------------------------------------------------------------
    def _call_provider_with_retry(self, prov, model, prompt, key, system_prompt=None):
        last_err = None
        for attempt in range(MAX_RETRIES + 1):
            time.sleep(CALL_DELAY_SECONDS)
            try:
                return self._raw_call(prov, model, prompt, key, system_prompt=system_prompt)
            except Exception as e:
                last_err = e
                err_text = str(e).lower()
                is_rate_limit = any(marker in err_text for marker in RATE_LIMIT_MARKERS)
                if is_rate_limit and attempt < MAX_RETRIES:
                    self.status.emit(
                        f"{prov} hız limitine takıldı, {RETRY_BACKOFF_SECONDS}sn bekleyip yeniden denenecek "
                        f"({attempt + 1}/{MAX_RETRIES})..."
                    )
                    time.sleep(RETRY_BACKOFF_SECONDS)
                    continue
                raise
        raise last_err

    # ------------------------------------------------------------------
    # Persona konuşma turu
    # ------------------------------------------------------------------
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

        return self._call_provider_with_retry(prov, model, prompt, key, system_prompt=sys_prompt)

    # ------------------------------------------------------------------
    # Özet: istenirse belirli sağlayıcı/model, başarısız olursa otomatik yedek zincir
    # Donen deger: (ozet_metni, kullanilan_saglayici, kullanilan_model)
    # ------------------------------------------------------------------
    def synthesize(self, history, provider=None, model=None):
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

        order = []
        if provider:
            order.append((provider, model))
        for p in SUMMARY_FALLBACK_ORDER:
            if p == provider:
                continue
            if self.api_keys.get(p) or p == "gemini":
                order.append((p, None))

        if not order:
            order = [(p, None) for p in SUMMARY_FALLBACK_ORDER if self.api_keys.get(p) or p == "gemini"]

        last_err = None
        for prov, mdl in order:
            key = self.api_keys.get(prov, "")
            if not key and prov != "gemini":
                continue
            try:
                self.status.emit(f"Özet '{PROVIDER_LABELS.get(prov, prov)}' ile deneniyor...")
                resolved_model = mdl if mdl else DEFAULT_MODELS.get(prov, prov)
                text = self._call_provider_with_retry(prov, mdl, prompt, key)
                return text, prov, resolved_model
            except Exception as e:
                last_err = e
                self.status.emit(f"Özet '{prov}' ile başarısız oldu, sıradaki sağlayıcı deneniyor...")
                continue

        return (
            f"Özet oluşturulamadı, denenen tüm sağlayıcılar başarısız oldu. Son hata: {last_err}",
            provider or "bilinmiyor",
            model or "-",
        )
