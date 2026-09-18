# 🤖 Kişisel Telegram Asistanı (Python)

Telefonunuzdan 7/24 erişebileceğiniz, görevlerinizi ve notlarınızı tutan, hava durumu ve piyasaları anlık bildiren, zaman ayarlı hatırlatmalar gönderen **kişisel Telegram botu**.

---

## 🌟 Özellikler

- 🌤️ **Anlık Hava Durumu:** Open-Meteo açık kaynak API'si ile Türkiye ve dünyanın her şehri için canlı sıcaklık, nem, rüzgar ve hava durumu ikonu.
- 💹 **Piyasa & Kurlar:** Dolar (USD), Euro (EUR), Sterlin (GBP), Bitcoin (BTC), Ethereum (ETH) ve Solana (SOL) anlık fiyatları.
- 📋 **Görev Takibi (To-Do):** Telegram içinden yapılacak işleri listeleme, tek tıkla `[✅ Tamamla]` veya `[🗑️ Sil]` butonları.
- 📝 **Hızlı Not Defteri:** Aklınıza gelen fikir veya notları anında kaydetme ve listeleme.
- ⏰ **Zaman Ayarlı Hatırlatıcı:** `/hatirlat 15 Çayı ocaktan al` dediğinizde, tam 15 dakika sonra bot size bildirim gönderir.
- 💾 **Kalıcı veri desteği:** PostgreSQL (`DATABASE_URL`) veya kalıcı disk üzerindeki SQLite (`DB_PATH`) ile bot yeniden başlasa bile kayıtlar korunur.
- 🎛️ **İnteraktif Menü:** Mesaj yazmadan butonlarla yönetebileceğiniz modern Inline Keyboard arayüzü.
- 🧭 **Sade ana ekran:** Brifing, Haberler, Takvim ve Ayarlar dışında dikkat dağıtan öğe göstermez; Gemini için doğrudan mesaj yazılır.
- 👋 **İlk kullanım tanıtımı:** Yeni kullanıcıya botun amacını birkaç saniyede anlatan kısa bir karşılama gösterir; tanıtım daha sonra “Diğer” menüsünden tekrar açılabilir.
- 🆕 **Güncelleme notları:** Son sürümde gelen yenilikleri bot içinden okunabilir şekilde listeler.
- ✨ **Yetenek Rehberi:** “Diğer > Bot neler yapar?” ekranı bütün özellikleri tek yerde açıklar.
- 📅 **Telefon Takvimi:** Google Takvim'deki etkinlikleri salt okunur iCal akışıyla gösterir ve yaklaşınca Telegram bildirimi yollar.
- 🤖 **Gemini Asistan:** Soruları yanıtlar, fikir üretir ve bekleyen görevler ile yakın takvimden yararlanarak gün planlamasına yardım eder.
- 🌅 **Karar Odaklı Sabah Brifingi:** Her sabah hava, takvim ve önceliklerden kısa bir kişisel eylem planı çıkarır.
- 🏃 **Sabah Koşusu Havası:** Koşudan önce sıcaklık, hissedilen sıcaklık, yağış ve rüzgâra göre kıyafet/yağmurluk tavsiyesi yollar.
- 📰 **İsteğe Bağlı Haber Özeti:** Türkiye ve dünyadan beşer önemli, doğrulanmış başlığı yalnızca istendiğinde Gemini + Google Search ile sunar.
- 🧭 **Sessiz Akıllı Kontrol:** Öğlen kontrolü, akşam özeti, haftalık değerlendirme ve etkinlik sonrası takip varsayılan olarak kapalıdır; Ayarlar'dan açılabilir.
- 🧠 **Etkinlik Hazırlığı:** Toplantı, doktor, seyahat ve ödeme gibi etkinliklere uygun hazırlık önerisi ve tek dokunuşlu erteleme sunar.
- 🌙 **Gün ve Hafta Kapanışı:** Akşam açık döngüleri gösterir; pazar günü tamamlanan işleri ve yaklaşan haftayı değerlendirir.

---

## 🚀 1 Dakikada Kurulum ve Başlatma

### 1. Ücretsiz Bot Tokenı Alın (30 Saniye)
1. Telegram uygulamanızda arama kısmına **@BotFather** yazın ve resmi bota girin.
2. `/newbot` komutunu gönderin.
3. Botunuza bir isim (örn: `Mustafa Asistan`) ve kullanıcı adı (örn: `mustafa_asistan_bot`) belirleyin.
4. BotFather'ın size verdiği uzun kırmızı/mavi **HTTP API Token** kodunu kopyalayın.

### 2. Tokenı `.env` Dosyasına Yapıştırın
Proje klasöründeki `.env` dosyasını açın ve tokenınızı ekleyin:
```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuvWxyz
DEFAULT_CITY=Istanbul
DATABASE_URL=postgresql://kullanici:sifre@sunucu/veritabani
# Railway Volume kullanırken PostgreSQL yerine:
# DB_PATH=/data/assistant.db
```

`DATABASE_URL` yerel geliştirmede isteğe bağlıdır. Render üzerinde kalıcı kullanım için
harici bir PostgreSQL bağlantısı tanımlayın; aksi halde geçici SQLite dosyası kullanılır.

## Railway Hobby kurulumu

1. GitHub deposunu Railway'de yeni bir projeye bağlayın.
2. Servise bir Volume ekleyip bağlama yolunu `/data` olarak ayarlayın.
3. Aşağıdaki değişkenleri tanımlayın:

```env
TELEGRAM_BOT_TOKEN=BotFather_tokeni
DB_PATH=/data/assistant.db
WEBHOOK_URL=https://railway-servis-alan-adiniz.up.railway.app
DEFAULT_CITY=Istanbul
TIMEZONE=Europe/Istanbul
CALENDAR_ICAL_URL=https://calendar.google.com/calendar/ical/.../basic.ics
CALENDAR_USER_ID=Telegram_kullanici_kimliginiz
CALENDAR_CHAT_ID=Telegram_sohbet_kimliginiz
# Takvim bildirimleri 24 saat ve 2 saat önce gönderilir.
GEMINI_API_KEY=Google_AI_Studio_anahtariniz
GEMINI_MODEL=gemini-2.5-flash
MORNING_BRIEFING_TIME=06:00
RUNNING_WEATHER_TIME=06:10
MORNING_RUN_TIME=07:00
MIDDAY_CHECK_TIME=13:30
EVENING_SUMMARY_TIME=21:00
WEEKLY_REVIEW_TIME=18:00
```

`DATABASE_URL` ve `DB_PATH` birlikte tanımlanırsa PostgreSQL kullanılır. Kalıcı Volume
ile düşük trafikli kişisel kullanımda yalnızca `DB_PATH` tanımlamak daha ekonomiktir.
Render PostgreSQL'den ilk geçişte eski verileri bir kez kopyalamak için geçici olarak
`SOURCE_DATABASE_URL` tanımlanabilir. Başarılı geçişten sonra bu değişken kaldırılmalıdır.

### Google Takvim bağlantısı

1. Telegram'da bota `/takvimbagla` yazıp kullanıcı ve sohbet kimliklerinizi görün.
2. Bilgisayarda Google Takvim'i açın; **Ayarlar > Takvimimin ayarları > Takvimi entegre et** bölümüne gidin.
3. **iCal biçiminde gizli adres** değerini kopyalayın ve Railway'de `CALENDAR_ICAL_URL` olarak saklayın.
4. `/takvimbagla` çıktısındaki değerleri `CALENDAR_USER_ID` ve `CALENDAR_CHAT_ID` olarak ekleyin.
5. Bot etkinlikleri otomatik olarak 24 saat ve 2 saat önce iki kez hatırlatır.

Gizli iCal adresini Telegram mesajına, GitHub'a veya `.env.example` dosyasına yazmayın.
Bağlantı salt okunurdur; bot takviminizde etkinlik değiştiremez veya silemez.

### Gemini bağlantısı

1. Google AI Studio'da bir API anahtarı oluşturun.
2. Anahtarı Railway servis değişkenlerine `GEMINI_API_KEY` adıyla ekleyin.
3. İsteğe bağlı olarak `GEMINI_MODEL` değerini değiştirin; varsayılan model `gemini-2.5-flash`tır.
4. Telegram'da `/sor Bugün neye öncelik vermeliyim?` yazarak bağlantıyı deneyin.

Gemini kullanıldığında yazdığınız soru ile yalnızca bekleyen görevleriniz, yaklaşan
hatırlatıcılarınız, önünüzdeki 7 günlük takvim ve varsayılan şehriniz Google'a gönderilir.
Notlar ve harcamalar bağlama eklenmez. Google'ın ücretsiz Gemini API katmanındaki içerikleri
ürün geliştirme amacıyla kullanabileceğini hesaba katarak hassas bilgi göndermeyin.

### Haber seçimi

Haber özeti Google Search ile son 24 saati tarar. Geniş toplumsal etki, güvenlik,
ekonomi, kamu yaşamı, diplomasi, afet ve Türkiye'ye olası etki ölçütleriyle sıralama yapar.
Resmî/ilk el kaynaklara ve Reuters, AP, AFP gibi ajanslara öncelik verir; önemli iddiaları
mümkünse birden fazla güvenilir kaynakla doğrular. Magazin, spor, görüş yazıları, söylentiler
ve aynı olayın tekrarları alınmaz. Bu seçim editoryal bir yapay zekâ özetidir; kesin ve nesnel
bir “en önemli” sıralaması değildir.

### 3. Botu Çalıştırın
- **En Kolay Yol:** Proje klasöründeki `start.bat` dosyasına çift tıklayın!
- **Terminal ile:**
  ```powershell
  cd "C:\Users\Mustafa\.gemini\antigravity\scratch\telegram-assistant"
  .\venv\Scripts\python.exe bot.py
  ```

Telegram'da kendi botunuza gidin ve **/start** yazarak asistanınızı kullanmaya başlayın! 🎉

---

## 📱 Kullanım Komutları

| Komut | Açıklama | Örnek |
|---|---|---|
| `/start` | Ana karşılama panelini ve interaktif butonları açar | `/start` |
| `/sor <soru>` | Gemini kişisel asistana soru sorar | `/sor Bugün neye öncelik vermeliyim?` |
| `/sabahozeti` | Kaynaklı akıllı sabah özetini hemen hazırlar | `/sabahozeti` |
| `/haberler` | Türkiye ve dünyadan beşer önemli haberi gösterir | `/haberler` |
| `/hakkinda` | Botun yapabildiği bütün işleri kategoriler halinde gösterir | `/hakkinda` |
| `/yenilikler` | Son sürümün güncelleme notlarını gösterir | `/yenilikler` |
| `/hava <şehir>` | İstenen şehrin canlı hava durumunu getirir | `/hava ankara` |
| `/sehir <şehir>` | Menüde kullanılacak varsayılan şehri kaydeder | `/sehir Ankara` |
| `/bugun` | Hava, görev ve sıradaki hatırlatıcı özetini gösterir | `/bugun` |
| `/piyasa` | Dolar, Euro, BTC, ETH güncel kurlarını listeler | `/piyasa` |
| `/gorev <metin>` | Yapılacaklar listesine yeni görev ekler | `/gorev Almanca tekrarını yap` |
| `/gorevler` | Aktif görevlerinizi butonlarla listeler | `/gorevler` |
| `/not <metin>` | Veritabanına hızlı not kaydeder | `/not Toplantı notları...` |
| `/notlar` | Kayıtlı notlarınızı listeler | `/notlar` |
| `/hatirlat <dk> <mesaj>` | Belirtilen dakika sonra alarmlı bildirim atar | `/hatirlat 20 Fırını kapat` |
| `/hatirlaticilar` | Bekleyen hatırlatıcıları listeler ve iptal ettirir | `/hatirlaticilar` |
| `/rutinler` | Her gün tekrarlanan rutinleri ekler, düzenler ve siler | `/rutinler` |
| `/ara <metin>` | Görev ve notlarda birlikte arama yapar | `/ara toplantı` |
| `/temizle` | Tamamlanan görevleri onayla topluca siler | `/temizle` |
| `/gorevdetay` | Öncelikli ve tarihli görev ekler | `/gorevdetay yüksek \| yarın 18:00 \| Rapor` |
| `/tekrarla` | Her gün tekrarlanan hatırlatıcı kurar | `/tekrarla 08:00 \| Su iç` |
| `/ozetsaat` | Otomatik günlük özet saatini ayarlar | `/ozetsaat 08:00` |
| `/aliskanlik` | Alışkanlık ekler ve günlük takip eder | `/aliskanlik ekle Kitap oku` |
| `/harcama` | Harcama kaydeder | `/harcama 250 market` |
| `/harcamalar` | Kategori bazlı harcama özetini gösterir | `/harcamalar` |
| `/butce` | Aylık bütçe belirler ve kalan tutarı gösterir | `/butce 10000` |
| `/harcamaindir` | Harcamaları Excel uyumlu CSV olarak indirir | `/harcamaindir` |
| `/etkinlik` | Yerel takvime etkinlik ekler | `/etkinlik yarın 14:00 \| Doktor` |
| `/takvim` | Yerel ve bağlı Google Takvim etkinliklerini gösterir | `/takvim` |
| `/takvimbagla` | Takvim bağlantısını ve gerekli kimlikleri gösterir | `/takvimbagla` |
| `/takvimindir` | Takvimi Google/Outlook uyumlu ICS olarak indirir | `/takvimindir` |
| `/disaaktar` | Kişisel verileri JSON olarak indirir | `/disaaktar` |
| `/verilerimisil` | Tüm kişisel verileri onayla siler | `/verilerimisil` |
| `/help` | Tüm komutları ve yardım rehberini gösterir | `/help` |

Doğal dil örnekleri: `yarın saat 10 doktoru hatırlat`, `250 TL market haftalık alışveriş`, `alışkanlık ekle Kitap oku`.

## Benchmark

Yerel veritabanı gecikmelerini, Türkçe niyet ayrıştırma hızını ve kod boyutu ölçümlerini
tekrarlamak için:

```powershell
python benchmarks/project_benchmark.py
```

Bu ölçüm ağ gecikmesini, Telegram API'sini, Gemini yanıt süresini ve Railway yük altı
davranışını kapsamaz; bunlar ayrı bir canlı yük testi gerektirir.
