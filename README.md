# AI-Boardroom (Yapay Zeka Tartışma Paneli)

AI-Boardroom, PyQt6 kullanılarak geliştirilmiş, yerel bilgisayarınızda çalışan bir yapay zeka tartışma simülasyonudur. Farklı yapay zeka modellerine (Google Gemini, OpenAI GPT, Anthropic Claude, Meta Llama - Groq, vb.) spesifik roller vererek bir proje veya fikir etrafında tartışmalarını, birbirlerini eleştirmelerini ve sonunda ortak bir özet/plan çıkarmalarını sağlar.

## Özellikler
*   **Farklı Sağlayıcılar:** OpenAI, Google Gemini, Anthropic, Groq ve OpenRouter üzerinden modelleri bir araya getirin.
*   **Rol (Persona) Şablonları:** Mimar, Eleştirmen, Ürün-UX, Sanatçı, Müzisyen gibi hazır alan şablonları.
*   **Dinamik Sıralama:** Tartışma akışını yönetmek için katılımcıların konuşma sırasını kolayca değiştirin.
*   **Açık Konu / Karar Takibi:** Tartışma ilerledikçe her turda açılan ve çözülen konular, alınan kararlar ayrı olarak tutulur; böylece round sayısı arttıkça modele gönderilen metin şişmez ve final özet, ham geçmişi yeniden yorumlamak yerine bu yapılandırılmış veriden üretilir.
*   **Geçmiş ve Dışa Aktarma:** Önceki tartışma geçmişlerini tutma, inceleme, JSON veya Markdown olarak dışa aktarma ve toplu silme.
*   **Asenkron Çalışma:** PyQt6 arayüzü donmadan arka planda çalışan AI çağrıları.

## Kurulum (sanal ortam ile)

Bağımlılıkları sisteme değil, projeye özel bir sanal ortama (venv) kurmanız önerilir.

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

Sanal ortamdan çıkmak için: `deactivate`

Bir sonraki çalıştırmada sadece ilgili `activate` komutunu tekrar çalıştırmanız yeterli — `pip install` adımını tekrarlamanıza gerek yok.

Uygulama açıldıktan sonra "Ayarlar" sekmesine giderek kullanmak istediğiniz platformların API anahtarlarını girin ve kaydedin.

---

## 💡 Tavsiye: En Verimli Sıralama Stratejileri

Yapay zeka modelleri **"Çıpalama Etkisi" (Anchoring Effect)** ile çalışır. İlk konuşan modelin ürettiği metin, tartışmanın sınırlarını ve ana odağını belirler. Arkadan gelen modeller bu temele tepki verir. Bu nedenle **1. sıraya koyduğunuz katılımcı, toplantının başkanıdır.**

### 1. Mühendislik ve Yazılım Projeleri İçin (Teknik Odaklı)
Eğer bir uygulama, veritabanı veya sistem mimarisi tartışılacaksa:
*   **1. Mimar:** Temeli atar, teknolojileri seçer.
*   **2. Eleştirmen:** Mimarın kurduğu sistemdeki güvenlik açıklarını ve darboğazları bulur.
*   **3. Ürün-UX:** Teknik kararların son kullanıcıya nasıl yansıyacağını düzenler.

### 2. Tasarım, İçerik ve Fikir Projeleri İçin (Kreatif Odaklı)
Eğer bir senaryo, arayüz tasarımı veya pazarlama fikri tartışılacaksa:
*   **1. Sanatçı / Yazar:** Fikri ve estetik vizyonu ortaya koyar.
*   **2. Ürün-UX:** Fikrin kullanılabilirliğini, akışını ve müşteri tarafını tartışır.
*   **3. Eleştirmen:** Fikirdeki mantık hatalarını, tutarsızlıkları ve marka risklerini arar.
