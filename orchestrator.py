import re
import time
import litellm
import os
import traceback
from PyQt6.QtCore import QThread, pyqtSignal
from boardroom_utils import track_cost

# LiteLLM tamamen sessiz
litellm.suppress_debug_info = True
litellm.set_verbose = False

META_BLOCK_MARKER = "---META---"
META_LINE_RE = re.compile(r"^(ACIK|AÇIK|COZULDU|ÇÖZÜLDÜ|KARAR|IPTAL|İPTAL|GEREKCE|GEREKÇE)\s*:\s*(.*)$", re.IGNORECASE)

# Bazı sağlayıcıların kendi native model adları vendor öneki taşımaz
# (örn. Gemini: "gemini-flash-latest"), ama OpenRouter'ın kataloğunda aynı
# modelin karşılığı vendor önekiyle birlikte listelenir (örn.
# "google/gemini-flash-latest"). Groq zaten "vendor/model" formatında model
# adları kullandığı için burada yer almıyor.
OPENROUTER_VENDOR_PREFIX = {
    "gemini": "google",
    "anthropic": "anthropic",
    "openai": "openai",
}

# Bir modelin "boş değil ama aslında hiçbir katkısı olmayan" bir ret
# cevabı verip vermediğini kabaca yakalamak için. Kesin bir sınıflandırıcı
# değil - sezgisel bir kontrol; yanlış pozitif/negatif verebilir ama hiç
# kontrol etmemekten iyidir (önceki hâlde ret cevapları "başarılı"
# sayılıp bir sonraki modele hiç geçilmiyordu).
REFUSAL_MARKERS = [
    "i'm sorry, but i can't",
    "i'm sorry, but i cannot",
    "i cannot assist",
    "i can't help with that",
    "i won't be able to help",
    "i am not able to help",
    "as an ai, i cannot",
    "üzgünüm, bu konuda yardımcı olamam",
    "bu talebi yerine getiremem",
    "bu konuda yardımcı olamıyorum",
    "bu içeriği oluşturamam",
]


def _is_refusal(text):
    if not text:
        return True
    low = text.strip().lower()
    # Kısa bir metin (< 200 karakter) + bilinen bir ret kalıbı içeriyorsa
    # ret say. Uzun, gerçek bir cevabın içinde geçen tesadüfi bir eşleşmeyi
    # (örn. bir alıntı) ret sanmamak için uzunluk sınırı konuldu.
    if len(low) < 200 and any(marker in low for marker in REFUSAL_MARKERS):
        return True
    return False

class DiscussionWorker(QThread):
    message_ready = pyqtSignal(dict)
    status = pyqtSignal(str)
    round_paused = pyqtSignal(int)
    finished_all = pyqtSignal(str, list, str)
    error = pyqtSignal(str)

    def __init__(self, project, personas, rounds, api_keys, pending_user_msgs,
                 summary_provider=None, summary_model=None, context_data=None):
        super().__init__()
        self.project = project
        self.personas = personas
        self.rounds = rounds
        self.api_keys = api_keys
        self.pending_user_msgs = pending_user_msgs
        self.summary_provider = summary_provider
        self.summary_model = summary_model
        self.context_data = context_data 
        self.transcript = []
        self.round_summaries = {}
        self.is_running = True
        self.is_paused = False
        self.issues = []
        self.decisions = []
        # Kullanıcının araya girdiği mesajlar burada kalıcı olarak birikir.
        # Sadece bir sonraki turun moderatör özetine güvenmek yerine, ham
        # hâliyle her turda tüm katılımcılara doğrudan gönderilir - böylece
        # bir talimat moderatörün özetlemesine bağlı kalıp kaybolmaz.
        self.active_user_notes = []

    def run(self):
        try:
            # API anahtarlarını yükle
            for prov, key in self.api_keys.items():
                if key:
                    os.environ[f"{prov.upper()}_API_KEY"] = key
                    print(f"[API] {prov.upper()} anahtarı yüklendi.")

            for r in range(1, self.rounds + 1):
                if not self.is_running: break
                
                self.status.emit(f"Tur {r} başladı...")
                moderator_note = self.round_summaries.get(r-1, "")

                for p in self.personas:
                    if not self.is_running: break
                    self.status.emit(f"Tur {r}: {p['name']} ({p['provider']}) konuşuyor...")

                    while not self.pending_user_msgs.empty():
                        u_msg = self.pending_user_msgs.get_nowait()
                        self.transcript.append({"speaker": "Sen", "round": r, "text": u_msg})
                        self.active_user_notes.append(u_msg)

                    response_text = self.safe_completion_loop(p, r, moderator_note)
                    
                    if response_text:
                        clean_text, meta = self._parse_meta_block(response_text)
                        self._apply_meta(meta, p["name"], r)
                        entry = {"speaker": p["name"], "round": r, "text": clean_text}
                        self.transcript.append(entry)
                        self.message_ready.emit(entry)
                    else:
                        hata_mesaji = f"⚠️ {p['name']} yanıt vermedi."
                        entry = {"speaker": p["name"], "round": r, "text": hata_mesaji}
                        self.transcript.append(entry)
                        self.message_ready.emit(entry)

                if self.is_running:
                    self.round_summaries[r] = self._generate_moderation(r)

                if r < self.rounds and self.is_running:
                    self.round_paused.emit(r)
                    self.is_paused = True
                    while self.is_paused and self.is_running:
                        self.msleep(200)

            if self.is_running:
                self.status.emit("Nihai rapor hazırlanıyor...")
                summary = self._final_synthesis()
                self.finished_all.emit(summary, self.transcript, "Elite Boardroom")

        except Exception as e:
            self.error.emit(f"Kritik Hata: {str(e)}")

    def safe_completion_loop(self, persona, rnd, mod_note):
        """
        Kullanıcının seçtiği provider'ı ÖNCE dene, başarısız olursa yedeklere geç.
        """
        ui_prov = persona["provider"].lower()
        ui_model = (persona.get("model") or "").strip()
        
        if not ui_model:
            ui_model = self._get_default_model(ui_prov)
            persona["model"] = ui_model
        
        print(f"\n{'='*50}")
        print(f"🔵 {persona['name']} -> Provider: {ui_prov}, Model: {ui_model}")
        print(f"{'='*50}")
        
        # ============ ANA MODEL ============
        # LiteLLM kuralı: model adı kendi içinde "/" içerse bile
        # (Groq'un "vendor/model" kataloğu gibi), LiteLLM'e giden string
        # HER ZAMAN "{provider}/{model}" olmalı. Aksi halde LiteLLM,
        # modelin kendi içindeki ilk parçayı (örn. "openai/") kendi
        # sağlayıcı yönlendirmesi sanıp yanlış API'ye gider.
        primary_model = f"{ui_prov}/{ui_model}"
        if "/" in ui_model:
            model_prov = ui_model.split('/')[0]
            if model_prov == ui_prov:
                print(f"   ⚠️ UYARI: model adı zaten '{ui_prov}/' ile başlıyor, "
                      f"önek tekrar eklenmedi.")
                primary_model = ui_model
        
        # ============ YEDEK MODELLER ============
        fallback_models = []

        # OpenRouter anahtarı varsa yedekleri ekle
        if self.api_keys.get("openrouter"):
            # 1. Aynı modeli OpenRouter üzerinden dene. OpenRouter kataloğu
            #    "vendor/model" ister; Groq'un model adları zaten bu formatta
            #    ama Gemini/Anthropic/OpenAI'nin kendi native adları (örn.
            #    "gemini-flash-latest") vendor öneki taşımıyor — bu yüzden
            #    provider'a göre doğru vendor önekini eklemek gerekiyor.
            vendor_prefix = OPENROUTER_VENDOR_PREFIX.get(ui_prov)
            if vendor_prefix and "/" not in ui_model:
                or_same = f"openrouter/{vendor_prefix}/{ui_model}"
            else:
                or_same = f"openrouter/{ui_model}"
            fallback_models.append(or_same)

            # 2. Ücretsiz modeller — sabit liste yerine OpenRouter'ın o anki
            #    canlı :free listesinden çekiliyor (sabit ID'ler haftalar
            #    içinde kaldırılabiliyor, bu yüzden çalışma anında sorulmalı).
            fallback_models.extend(self._get_live_free_openrouter_models())

        # Tüm modelleri birleştir (önce ana, sonra yedekler)
        models_to_try = [primary_model] + fallback_models
        
        print(f"   📋 Denenecek modeller:")
        for i, m in enumerate(models_to_try):
            print(f"      {i+1}. {m}")
        
        # ============ API ANAHTARINI AL ============
        api_key = self.api_keys.get(ui_prov)
        
        if not api_key and self.api_keys.get("openrouter"):
            api_key = self.api_keys.get("openrouter")
            print(f"   ⚠️ {ui_prov} anahtarı yok, OpenRouter kullanılacak")
        
        if not api_key:
            print(f"   ❌ Hiçbir API anahtarı yok!")
            self.error.emit(f"❌ {persona['name']} için API anahtarı bulunamadı!")
            return None
        
        # ============ PROMPT ============
        sys_prompt = (
            f"Sen {persona['role']} rolündesin. Kararlarını GEREKÇE ile açıkla.\n"
            f"Cevabının EN SONUNA, aşağıdaki formatta, tam olarak bu şekilde bir blok ekle "
            f"(bu blok kullanıcıya gösterilmez, sadece sistem tarafından okunur):\n\n"
            f"{META_BLOCK_MARKER}\n"
            f"KARAR: <bu turda aldığın somut karar, tek cümle>\n"
            f"GEREKÇE: <kararının kısa gerekçesi>\n"
            f"AÇIK: <varsa hâlâ çözülmemiş/tartışmalı bir konu, yoksa bu satırı hiç yazma>\n\n"
            f"Bir karar almadıysan KARAR satırını hiç yazma - boş/uydurma karar yazma."
        )
        user_content = f"Konu: {self.project}\n"
        if self.active_user_notes:
            notes = "\n".join(f"- {n}" for n in self.active_user_notes)
            user_content += (
                f"\nKULLANICININ DOĞRUDAN TALİMATLARI (bunlara mutlaka uy, "
                f"özet/moderatör notu beklemeden dikkate al):\n{notes}\n"
            )
        if mod_note:
            user_content += f"Başkan Notu: {mod_note}\n"
        if self.context_data:
            user_content += f"Bağlam: {self.context_data[:500]}...\n"
        user_content += f"Tur: {rnd}\nGörüşün:"
        
        # ============ SIRALI DENE ============
        for idx, model in enumerate(models_to_try):
            try:
                model_prov = model.split('/')[0]
                model_key = self.api_keys.get(model_prov)
                
                if not model_key:
                    model_key = api_key
                
                print(f"   🔄 [{idx+1}/{len(models_to_try)}] {model} deneniyor...")
                
                response = litellm.completion(
                    model=model,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    api_key=model_key,
                    timeout=35,
                    temperature=0.7
                )
                
                track_cost(response)
                content = response.choices[0].message.content
                
                if content and len(content.strip()) > 0 and not _is_refusal(content):
                    print(f"   ✅ {model} BAŞARILI!")
                    
                    # Kullanıcıya hangi modelin kullanıldığını bildir
                    if model != primary_model:
                        self.error.emit(f"🔄 {persona['name']}: {primary_model} başarısız, {model} kullanılıyor")
                    else:
                        print(f"   ✅ {persona['name']} kendi provider'ı ile çalışıyor: {ui_prov}")
                    
                    return content
                else:
                    if content and _is_refusal(content):
                        print(f"   ⚠️ {model} isteği reddetti: \"{content.strip()[:80]}\"")
                    else:
                        print(f"   ⚠️ {model} boş yanıt verdi")
                    
            except Exception as e:
                error_msg = str(e)
                
                # Rate limit - bekle ve tekrar dene
                if "rate" in error_msg.lower() or "quota" in error_msg.lower() or "429" in error_msg:
                    wait_time = 5
                    print(f"   ⚠️ {model} RATE LIMIT! {wait_time} saniye bekleniyor...")
                    time.sleep(wait_time)
                    # Aynı modeli tekrar dene
                    try:
                        print(f"   🔄 {model} tekrar deneniyor (bekleme sonrası)...")
                        model_prov = model.split('/')[0]
                        model_key = self.api_keys.get(model_prov) or api_key
                        
                        response = litellm.completion(
                            model=model,
                            messages=[
                                {"role": "system", "content": sys_prompt},
                                {"role": "user", "content": user_content}
                            ],
                            api_key=model_key,
                            timeout=35,
                            temperature=0.7
                        )
                        
                        track_cost(response)
                        content = response.choices[0].message.content
                        
                        if content and len(content.strip()) > 0 and not _is_refusal(content):
                            print(f"   ✅ {model} BAŞARILI (tekrar denemede)!")
                            if model != primary_model:
                                self.error.emit(f"🔄 {persona['name']}: {primary_model} başarısız, {model} kullanılıyor (rate limit sonrası)")
                            return content
                    except Exception as e2:
                        print(f"   ❌ {model} tekrar denemede başarısız: {str(e2)[:80]}")
                        continue
                        
                elif "auth" in error_msg.lower() or "api key" in error_msg.lower() or "incorrect" in error_msg.lower():
                    print(f"   ⚠️ {model} AUTH HATASI (anahtar geçersiz): {error_msg[:80]}")
                    # Auth hatasında diğer modelleri dene
                    continue
                else:
                    print(f"   ❌ {model} hatası: {error_msg[:100]}")
                    continue
        
        # ============ HİÇBİR MODEL ÇALIŞMADI ============
        print(f"   ❌ {persona['name']} için TÜM MODELLER BAŞARISIZ!")
        self.error.emit(f"❌ {persona['name']} için tüm modeller başarısız oldu!")
        return None

    def _generate_moderation(self, rnd):
        """Özet - Rate limit ile"""
        try:
            prov = self.summary_provider.lower()
            model = (self.summary_model or "").strip()
            
            if not model:
                model = self._get_default_model(prov)
                self.summary_model = model
            
            print(f"\n{'='*50}")
            print(f"🔵 ÖZET -> Provider: {prov}, Model: {model}")
            print(f"{'='*50}")
            
            primary = f"{prov}/{model}"
            if "/" in model and model.split('/')[0] == prov:
                primary = model  # zaten prov/ ile başlıyorsa tekrar ekleme
            fallbacks = []
            if self.api_keys.get("openrouter"):
                fallbacks.extend(self._get_live_free_openrouter_models())
            
            models_to_try = [primary] + fallbacks
            api_key = self.api_keys.get(prov) or self.api_keys.get("openrouter")
            
            if not api_key:
                print("   ❌ Özet için API anahtarı yok!")
                return "Tartışmaya devam edelim."
            
            txt = "\n".join([f"{t['speaker']}: {t['text']}" for t in self.transcript if t['round'] == rnd])
            
            for idx, model in enumerate(models_to_try):
                try:
                    model_prov = model.split('/')[0]
                    model_key = self.api_keys.get(model_prov) or api_key
                    
                    print(f"   🔄 [{idx+1}/{len(models_to_try)}] Özet {model} deneniyor...")
                    
                    response = litellm.completion(
                        model=model,
                        messages=[{"role": "user", "content": f"Sen kurul başkanısın. Özetle ve yönlendir:\n{txt}"}],
                        api_key=model_key,
                        timeout=25
                    )
                    
                    content = response.choices[0].message.content
                    if _is_refusal(content):
                        print(f"   ⚠️ Özet {model} isteği reddetti, sıradaki modele geçiliyor.")
                    else:
                        print(f"   ✅ Özet {model} BAŞARILI!")

                        if model != primary:
                            self.error.emit(f"🔄 Özet: {primary} başarısız, {model} kullanılıyor")

                        return content
                    
                except Exception as e:
                    error_msg = str(e)
                    if "rate" in error_msg.lower() or "quota" in error_msg.lower() or "429" in error_msg:
                        print(f"   ⚠️ Özet {model} RATE LIMIT! 5 saniye bekleniyor...")
                        time.sleep(5)
                        # Tekrar dene
                        try:
                            print(f"   🔄 Özet {model} tekrar deneniyor...")
                            response = litellm.completion(
                                model=model,
                                messages=[{"role": "user", "content": f"Sen kurul başkanısın. Özetle ve yönlendir:\n{txt}"}],
                                api_key=model_key,
                                timeout=25
                            )
                            content = response.choices[0].message.content
                            if _is_refusal(content):
                                print(f"   ⚠️ Özet {model} tekrar denemede de reddetti.")
                                continue
                            print(f"   ✅ Özet {model} BAŞARILI (tekrar)!")
                            return content
                        except:
                            continue
                    else:
                        print(f"   ❌ Özet {model} hatası: {str(e)[:80]}")
                        continue
            
            return "Tartışmaya devam edelim."
            
        except Exception as e:
            print(f"   ❌ Özet genel hata: {str(e)}")
            return "Tartışmaya devam edelim."

    def _final_synthesis(self):
        """Final rapor"""
        try:
            prov = self.summary_provider.lower()
            model = (self.summary_model or "").strip()
            
            if not model:
                model = self._get_default_model(prov)
            
            print(f"\n{'='*50}")
            print(f"🔵 RAPOR -> Provider: {prov}, Model: {model}")
            print(f"{'='*50}")
            
            primary = f"{prov}/{model}"
            if "/" in model and model.split('/')[0] == prov:
                primary = model  # zaten prov/ ile başlıyorsa tekrar ekleme
            
            fallbacks = []
            if self.api_keys.get("openrouter"):
                fallbacks.extend(self._get_live_free_openrouter_models())
            
            models_to_try = [primary] + fallbacks
            api_key = self.api_keys.get(prov) or self.api_keys.get("openrouter")
            
            if not api_key:
                return "Rapor oluşturulamadı: API anahtarı eksik."
            
            decs = self._format_decisions()
            full_transcript = "\n\n".join(
                f"[Tur {t['round']}] {t['speaker']}: {t['text']}" for t in self.transcript
            )
            report_prompt = (
                f"Konu: {self.project}\n\n"
                f"Aşağıda tam tartışma dökümü var. Bunu oku ve profesyonel bir rapor yaz.\n"
                f"Rapor şunları içermeli: 1) Yönetici özeti, 2) Alınan kararlar "
                f"(varsa aşağıdaki yapılandırılmış listeyi kullan, yoksa dökümden kendin çıkar), "
                f"3) Hâlâ tartışmalı/açık kalan noktalar, 4) Somut sonraki adımlar.\n"
                f"Kısa geçme - gerçek içerik üret, 'Yok' ya da 'bilgi eksik' gibi bir cevapla "
                f"kesinlikle döndürme; döküm zaten aşağıda mevcut.\n\n"
                f"Yapılandırılmış kararlar (varsa):\n{decs}\n\n"
                f"Tam tartışma dökümü:\n{full_transcript}"
            )

            for model in models_to_try:
                try:
                    model_prov = model.split('/')[0]
                    model_key = self.api_keys.get(model_prov) or api_key
                    
                    print(f"   🔄 Rapor {model} deneniyor...")
                    
                    response = litellm.completion(
                        model=model,
                        messages=[{"role": "user", "content": report_prompt}],
                        api_key=model_key,
                        timeout=60
                    )
                    
                    content = response.choices[0].message.content
                    if _is_refusal(content):
                        print(f"   ⚠️ Rapor {model} isteği reddetti, sıradaki modele geçiliyor.")
                    else:
                        print(f"   ✅ Rapor {model} BAŞARILI!")
                        return content
                    
                except Exception as e:
                    error_msg = str(e)
                    if "rate" in error_msg.lower() or "quota" in error_msg.lower() or "429" in error_msg:
                        print(f"   ⚠️ Rapor {model} RATE LIMIT! 5 saniye bekleniyor...")
                        time.sleep(5)
                        try:
                            response = litellm.completion(
                                model=model,
                                messages=[{"role": "user", "content": report_prompt}],
                                api_key=model_key,
                                timeout=45
                            )
                            content = response.choices[0].message.content
                            if _is_refusal(content):
                                print(f"   ⚠️ Rapor {model} tekrar denemede de reddetti.")
                                continue
                            print(f"   ✅ Rapor {model} BAŞARILI (tekrar)!")
                            return content
                        except:
                            continue
                    else:
                        print(f"   ❌ Rapor {model} hatası: {str(e)[:80]}")
                        continue
            
            return f"Rapor oluşturulamadı. Alınan kararlar:\n{decs}"
            
        except Exception as e:
            return f"Rapor oluşturulamadı: {str(e)}"

    def _get_live_free_openrouter_models(self, limit=3):
        """
        OpenRouter'in o anki canli ':free' model listesini ceker.
        Sabit ID'ler haftalar icinde kaldirilabildigi icin (bkz. bu oturumdaki
        hatalar), calisma aninda sorulmasi daha kalici bir cozum. Basarisiz
        olursa (agsiz, API degismis vb.) bos liste doner - fallback zinciri
        kisalir ama program cokmez. Ayni calistirma icinde tekrar tekrar
        agdan cekmemek icin sonuc onbelleklenir.
        """
        if getattr(self, "_free_model_cache", None) is not None:
            return self._free_model_cache
        try:
            import requests
            key = self.api_keys.get("openrouter")
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            resp = requests.get(
                "https://openrouter.ai/api/v1/models", headers=headers, timeout=10
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            free_ids = [m["id"] for m in data if m.get("id", "").endswith(":free")]
            result = [f"openrouter/{mid}" for mid in free_ids[:limit]]
            print(f"[OpenRouter] Canlı ücretsiz model listesi çekildi: {result}")
        except Exception as e:
            print(f"[OpenRouter] Canlı model listesi alınamadı, yedeksiz devam: {e}")
            result = []
        self._free_model_cache = result
        return result

    def _get_default_model(self, provider):
        defaults = {
            "groq": "openai/gpt-oss-120b",
            "openrouter": "openai/gpt-oss-120b:free",
            "gemini": "gemini-2.0-flash",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-sonnet-20241022"
        }
        return defaults.get(provider, "gpt-4o-mini")

    def _parse_meta_block(self, text):
        if META_BLOCK_MARKER not in text:
            return text.strip(), {}
        clean_part, _, meta_part = text.partition(META_BLOCK_MARKER)
        meta = {}
        for line in meta_part.splitlines():
            m = META_LINE_RE.match(line.strip())
            if m:
                meta[m.group(1).lower()] = m.group(2).strip()
        return clean_part.strip(), meta

    def _apply_meta(self, meta, name, rnd):
        if meta.get("karar"):
            gerekce = meta.get("gerekce") or meta.get("gerekçe") or "Belirtilmedi"
            self.decisions.append({"ozet": meta["karar"], "gerekce": gerekce, "acan": name, "tur": rnd})
        
        acik_key = "acik" if "acik" in meta else "açık"
        if meta.get(acik_key):
            self.issues.append({"baslik": meta[acik_key], "acan": name})

    def _format_decisions(self):
        return "\n".join([f"- {d['ozet']} (Gerekçe: {d['gerekce']})" for d in self.decisions]) or "Yok"

    def resume(self):
        self.is_paused = False
        
    def stop(self):
        self.is_running = False
        self.is_paused = False