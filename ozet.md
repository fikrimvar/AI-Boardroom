Yapay Zeka ile Ünlü Karakter Sınav Videosu Üretim Sistemi — Profesyonel Proje Raporu

1. Yönetici Özeti
Bu proje, kullanıcının belirlediği dizi ve karakter (örneğin Ramiz Dayı, Ezel) ile bir akademik soruyu alıp, yapay zeka araçlarıyla bu karaktere uygun üslubda kısa bir eğlence‑eğitim (edutainment) videosu üreten bir pipeline tasarımıdır. Hedef platformlar Instagram Reels / TikTok (dikey, 9:16) ve YouTube Shorts (yatay, 16:9) olacaktır.
Tartışma sürecinde üç ana tur gerçekleştirilmiştir:
Tur 1: Kurumsal mikro‑servis mimarisi (Kubernetes, Redis, kuyruk, GPU node pool) önerilmiş; ancak hukuki, teknik ve operasyonel riskler nedeniyle bu mimari reddedilmiş ve basitleştirilmiş bir yaklaşım benimsenmiştir.
Tur 2: Tek hatlı, serverless/Lambda tabanlı, üç API (WolframAlpha + OpenAI + ElevenLabs/Replicate) + FFmpeg montajından oluşan basit pipeline kabul edilmiş. Otomatik sosyal medya yükleme talimatları ele alınmış, ancak kullanıcı "manuel gönderim" talebi üzerine bu katman çıkarılmıştır.
Tur 3: İki farklı formatta (9:16 ve 16:9) çift FFmpeg render'ı, S3 üzerinden manuel indirme/link paylaşımı ve parodi‑sanitizer gibi güvenlik katmanları eklenerek mimari kesinleştirilmiştir.
Sonuç: MVP, tek bir Python/Node orchestration scripti + üç dış API + FFmpeg + S3/CloudFront ile iki haftada üretilebilir. Telif riskleri parodi adımları ve "no real‑person" prompt kısıtlamalarıyla sınırlandırılacaktır. Gerçek video üretimi (Runway/HeyGen/Gen‑3 gibi AI video API'leri) V2'ye ertelenebilir; MVP'de en az "Script + Ses + Görsel Prompt + Shot Listesi" hazırpaketi sunulacaktır.

2. Alınan Kararlar
#
Karar
Gerekçe
Kaynak
D1
Doğrudan telifli karakter içeren video üretimi yapılmaz; karakterler "parodi" olarak yeniden adlandırılır (örn. "Ramiz Dayı" → "Sınav Dayı", "Ezel Bayraktar" → "Strateji Ezel"). Telif hakkı uyarısı ve örnek bir sistem mimarisi sunulur.
Telifli karakterlerin izinsiz AI üretimi yasal risk taşır; sistem tasarımı ve tavsiyelerle sınırlı kalmak uygun ve güvenlidir.
Tur 1 (Kurumsal Mimari), Tur 1 (Hukuki Uyarılar)
D2
MVP'de tam video render yerine "Hazır Paket" çıktısı verilir: Script + Ses (TTS) + Görsel Promptları + Shot Listesi. Gerçek video üretimi V2'ye ertelenir.
Video üretim API'leri (Sora, Runway, Gen‑3) henüz tutarlı karakter kontrolü ve maliyet açısından ölçeklenebilir değil; içerik üreticilerinin en büyük acı noktası "ne anlatacak, nasıl anlatacak" kurgusudur; bunu çözmek tek başına yüksek değerli bir araçtır.
Tur 1 (Ürün‑UX MVP Önerisi)
D3
Projenin hukuki (telif/kişilik hakları), teknik (halüsinasyon/doğruluk) ve içerik güvenliği riskleri nedeniyle mimari revizyona yönlendirilir.
İzinsiz karakter/ses kullanımı ciddi hukuki yaptırımlar taşır; ayrıca yapay zekanın akademik soruları yanlış çözme ihtimali ve denetimsiz senaryo girdilerinin içerik güvenliği riski bulunmaktadır.
Tur 1 (Eleştirmen)
D4
MVP için tek bir serverless Lambda fonksiyonu ve dış 3‑lü API (WolframAlpha, OpenAI, ElevenLabs/Replicate) kullanılarak video oluşturma pipeline'ı önerilir.
En az kod, düşük maliyet ve hızlı prototipleme sağlarken, kullanıcı etkileşimi olmadan doğrudan hazır video üretimi mümkün olur.
Tur 2 (Mimar)
D5
Mikroservis/K8s/GPU altyapısı reddedilir; tek bir orchestration scripti (Python/Node) + Video/TTS/LLM API'leri (Runway/HeyGen, ElevenLabs, OpenAI) ile serverless/basit VM mimarisi seçilir.
Kullanıcı "basit pipeline, etkileşim yok, video çıkışı" istedi; kurumsal mimari 10x yavaşlatır, maliyeti artırır ve bakım yükü binder. Video API'leri karakter tutarlılığı ve render sorununu çözmüş durumda, kendi GPU/ControlNet kurmak ROI'siz.
Tur 2 (Ürün‑UX Karar 1)
D6
Redis ve Kubernetes gibi karmaşık yapılar mimariden çıkarılır; tek hatlı (Python + FFmpeg) otomatik sosyal medya yayın pipeline'ına geçilir.
Kullanıcının karmaşık mimari istememesi ve kullanıcı etkileşimsiz tam otomasyon talimatı doğrultusunda sistem basitleştirilmiş, insan kontrolü olmamasından doğacak telif ve ban riskleri pipeline içi otomatik filtrelerle sınırlandırılır.
Tur 2 (Eleştirmen)
D7
Serverless Lambda pipeline with external AI APIs; iki format (9:16 Reels/TikTok + 16:9 YouTube Shorts) tek seferde FFmpeg ile üretilir.
En az altyapı, düşük maliyet, istenen basitlik ve iki format gereksinimini karşılar.
Tur 2 (Mimar)
D8
Otomatik sosyal medya yükleme adımları ve OAuth mimarisi tamamen kaldırılır; video dosyaları kullanıcıya manuel indirme/link paylaşımı ile teslim edilir.
Kullanıcının "gönderim otomatik olmasın, manuel olacak" talimatı önceki otomatik upload planıyla çelişiyor. Ürün yöneticisi olarak yasal risk (API politikası değişiklikleri, token yönetimi yükü), marka güvenliği (yanlış etiket/açıklama ile paylaşım) ve kullanıcı kontrolü (son onay, hashtag/başlık düzenleme) gereksinimi nedeniyle manuel teslimat en doğru MVR (Minimum Viable Risk) yaklaşımıdır. İki format (9:16 Reels/Shorts, 16:9 YouTube) FFmpeg parametresiyle tek seferde üretilip paketlenecektir.
Tur 3 (Çelişki Analizi)
D9
FFmpeg modülü aynı kaynaktan hem 9:16 hem 16:9 formatlarında iki ayrı MP4 üretecek ve manuel indirmeye sunacak şekilde güncellenir.
Kullanıcının otomatik paylaşım istememesi ve hem dikey hem yatay iki ayrı format talep etmesi üzerine mimarideki API yükleme karmaşıklığı elenip çift render mantığına geçilmiştir.
Tur 3 (Güncellenmiş Pipeline)
D10
Parodi‑sanitizer (karakter adı dönüştürme), auto‑disclaimer (AI üretim filigrani), regex içerik filtresi ve çift‑kaynak doğrulama (Wolfram + GPT) pipeline'a dahil edilir.
Telif/deep‑fake riski, LLM halüsinasyonu ve platform politikası ihlalleri önlenir; sıfır insan etkileşimine rağmen video kalitesi ve yasal güvenlik sağlanır.
Tur 2 (Eleştirmen), Tur 3 (Safeguard'lar)


3. Hâlâ Tartışmalı / Açık Kalan Noktalar
#
Açık Sorun
Açıklama
Önerilen Aksiyon
O1
Ses klonlama mesafesi: Tur 1'de ElevenLabs "Voice Design" ile parodi ses önerildi; ancak gerçek karakter sesinin yakınlığı kullanıcı memnuniyetini doğrudan etkiler. "Ses klonlama yerine TTS + prosody ayarı" yeterli mi, yoksa "Pro katman" olarak ses klonu sunulmalı mı?
Tur 1 Ürün‑UX'te "ses klonlama Pro katmanına bırakılmalı" denilmiş; ancak kullanıcı bu konuyu açıkça talep etmemiş.
MVP'de TTS‑only yaklaşımı sabit tutulup, kullanıcı geri bildirimine göre Pro katmana alınabilir.
O2
Gerçek karakter isimlerinin parodiye dönüştürülmesi kullanıcıyı kısıtlayabilir. Kullanıcı "Ramiz Dayı" yazdığında sistemin bunu "Sınav Dayı" olarak işleymesi, kullanıcı deneyimini olumsuz etkileyebilir.
Tur 3'te hâlâ "Ramiz Dayı" doğrudan karakter girdisi olarak kullanılmaktadır; parodi‑sanitizer bu isimleri dönüştürür mi?
Giriş formunda karakter seçimi dropdown (parodi isimleri ile) yapılmalı; metin girişinde otomatik eşleme kuralı belirlenmeli.
O3
Video API maliyetinin MVP için aşırı olup olmadığı. Runway/HeyGen/Replicate saniye başına faturalama yapar; 100 video/ay için tahmini $100‑$300 arası. Bu, MVP'nin sürdürülebilirlik açısından yüksek bir kalemdir.
Tur 2'de maliyet tahmini $130‑$330/ay verilmiş; video API en büyük kalemdir.
MVP'de gerçek video API'si yerine statik görsel + parallax animasyon + TTS kombinasyonu denenmeli; maliyet %80 düşebilir.
O4
LLM halüsinasyonu için çift‑kaynak doğrulama yeterli mi? WolframAlpha matematiksel soruları çözer ancak Türkçe matematik problemlerinde sınırlı kalabilir; GPT‑4o‑mini de hatalı çözüm üretebilir.
Tur 2 ve Tur 3'te Wolfram + GPT çift doğrulama önerilmiş.
SymPy (Python) ile yerel matematik çözümü eklenmeli; WolframAPI yanıtı ile SymPy yanıtı karşılaştırılmalı.
O5
2 haftalık MVP planının gerçekçi olup olmadığı. 14 günde Docker, API entegrasyonları, FFmpeg dual‑render, güvenlik filtreleri, Lambda paketleme ve dokümantasyon tamamlanması agresif bir zaman çizelgesidir.
Tur 3'te 14 günlük plan verilmiş; ancak her bir gün birden fazla modül içeriyor.
Plan, 3 haftaya uzatılmalı veya scope küçültülerek (sadece 9:16, sadece 1 karakter, sadece matematik soruları) MVP ilk sprintte teslim edilmelidir.
O6
"Başkan Notu" ile kullanıcı talimatları arasındaki otomatik upload çelişkisinin tam çözülüp çözülmediği. Tur 3'te OAuth/Graph API katmanları çıkarıldı; ancak "otomatik upload" ifadesi bazı dokümantasyon parçalarında hâlâ geçmektedir.
Tur 3'te bu çelişki vurgulanmış, ancak tüm dokümanlarda tutarlılık sağlanmamış olabilir.
Tüm mimari dokümanlarında "manuel upload" ifadesi tek tutarlı şekilde yerleştirilmeli; otomatik upload ile ilgili tüm referanslar silinmelidir.
O7
İçerik güvenliği için regex‑tabanlı filtre yeterli mi? Nefret söylemi, siyasi propaganda ve uygunsuz içeriklerin regex ile tespiti kolay olmayan durumlar içerir.
Tur 2 ve Tur 3'te basit regex filtresi önerilmiş.
OpenAI Moderation API veya benzeri bir moderation service entegrasyonu düşünülmelidir.


4. Somut Sonraki Adımlar
A. Kısa Vadeli (Hafta 1‑2) — MVP Kurulumu
Repo ve Altyapı Kurulumu
GitHub repo oluştur (video‑pipeline).
Dockerfile (Python 3.11 + FFmpeg) ve docker-compose.yml yazılır.
.env.example dosyası: OPENAI_KEY, WOLFRAM_KEY, ELEVENLABS_KEY, REPLICATE_TOKEN, AWS_ACCESS_KEY, AWS_SECRET_KEY, S3_BUCKET_NAME.
Parodi Karakter Kütüphanesi (config.yaml)
characters:
  - key: sinav_daji
    display_name: "Sınav Dayı"
    inspired_by: "Ramiz Dayı (Kurtlar Vadisi)"
    voice_id: "elevenlabs-voice-id-xxx"
    persona_prompt: "Sakin, bilge, hafif fısıltılı, İstanbul ağzı. Matematik sorusunu güleryüzlü ama otoriter şekilde çöz."
    image_prompt: "Cartoon-style elderly Turkish man in a suit, standing in front of a green chalkboard, holding chalk."
    reference_image_url: "https://cdn.example.com/refs/sinav_daji.png"
  - key: strateji_ezel
    display_name: "Strateji Ezel"
    inspired_by: "Ezel Bayraktar (Ezel dizisi)"
    voice_id: "elevenlabs-voice-id-yyy"
    persona_prompt: "Keskin, kararlı, gizemli ton. Soruyu stratejik bir zeka oyunu gibi çözer."
    image_prompt: "Cartoon-style handsome young man in a black suit, standing in a dimly lit room, solving a equation on a digital tablet."
    reference_image_url: "https://cdn.example.com/refs/strateji_ezel.png"
Core Pipeline Kodu (main.py)
Adım 1: Girdi doğrulama (series, character, question zorunlu).
Adım 2: Parodi‑sanitizer (karakter key → config.yaml eşleme).
Adım 3: WolframAlpha + GPT‑4o‑mini ile çözüm + CoT açıklama.
Adım 4: GPT‑4 ile persona script (hook + çözüm + CTA).
Adım 5: Regex içerik filtresi + OpenAI Moderation API.
Adım 6: ElevenLabs TTS → audio.mp3.
Adım 7: Replicate/Stable Diffusion → frame.png (reference image + prompt).
Adım 8: FFmpeg dual‑render → output_9x16.mp4 + output_16x9.mp4.
Adım 9: Auto‑disclaimer watermark (FFmpeg drawtext filter).
Adım 10: S3 upload → presigned URL döndürme.
Unit Testler
Solver testi: 2x+5=13 → x=4 (Wolfram doğrulama).
Parodi sanitizer testi: "Ramiz Dayı" → "sinav_daji" key.
FFmpeg render testi: boş görsel + ses → geçerli MP4.
B. Orta Vadeli (Hafta 3‑4) — MVP Teslimi ve İlk Kullanım
Lambda Paketi ve Deploy
Docker image → AWS ECR → Lambda (2048 MB memory, 15 min timeout).
API Gateway → POST /generate endpoint.
CloudWatch alarmları (hata rate, maliyet, latency).
Kullanıcı Dokümantasyonu
Örnek cURL komutu ve JSON payload.
Manuel upload yönergesi (S3 presigned URL'yi nasıl Reels/YouTube'a yükleyeceğine dair adım adım ekran görüntüleri).
İlk 10 Kullanıcı Testi
5 farklı karakter + 10 farklı soru ile pipeline çalıştırılır.
Video kalitesi, ses tutarlılığı, çözüm doğruluğu ve kullanıcı geri bildirimi toplanır.
C. Uzun Vadeli (V2 — 4‑6 Hafta Sonrası)
Tam Video Render Entegrasyonu
Runway Gen‑3 / HeyGen / Luma API'si ile gerçek karakter sahnesi üretimi.
VTT/word‑level timestamps ile ses‑görsel senkronizasyonu.
Otomatik Sosyal Medya Yükleme (İsteğe Bağlı Modül)
TikTok/Instagram Graph API OAuth flow.
Kullanıcı onay ekranı (preview → onay → upload).
Hashtag/title/description düzenleme UI.
Pro Katman: Ses Klonlama
Kullanıcı kendi ses dosyasını yükleyebilir; RVC/SoVITS ile fine‑tuned parodi sesi üretilir.
Bu modül yalnızca Pro plan kullanıcısı için açılır.
Analytics Dashboard
Video başarıları (görüntüleme, etkileşim) → S3 log + Google Analytics/Plausible entegrasyonu.
Maliyet optimizasyon raporu (hangi karakter‑sorü kombinasyonları en pahalı?).

Rapor Sonu