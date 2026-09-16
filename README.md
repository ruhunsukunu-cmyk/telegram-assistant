# 🤖 Kişisel Telegram Asistanı (Python)

Telefonunuzdan 7/24 erişebileceğiniz, görevlerinizi ve notlarınızı tutan, hava durumu ve piyasaları anlık bildiren, zaman ayarlı hatırlatmalar gönderen **kişisel Telegram botu**.

---

## 🌟 Özellikler (Tamamen Ücretsiz, 0 TL Maliyet)

- 🌤️ **Anlık Hava Durumu:** Open-Meteo açık kaynak API'si ile Türkiye ve dünyanın her şehri için canlı sıcaklık, nem, rüzgar ve hava durumu ikonu.
- 💹 **Piyasa & Kurlar:** Dolar (USD), Euro (EUR), Sterlin (GBP), Bitcoin (BTC), Ethereum (ETH) ve Solana (SOL) anlık fiyatları.
- 📋 **Görev Takibi (To-Do):** Telegram içinden yapılacak işleri listeleme, tek tıkla `[✅ Tamamla]` veya `[🗑️ Sil]` butonları.
- 📝 **Hızlı Not Defteri:** Aklınıza gelen fikir veya notları anında kaydetme ve listeleme.
- ⏰ **Zaman Ayarlı Hatırlatıcı:** `/hatirlat 15 Çayı ocaktan al` dediğinizde, tam 15 dakika sonra bot size bildirim gönderir.
- 💾 **Kalıcı veri desteği:** `DATABASE_URL` tanımlandığında notlar, görevler ve bekleyen hatırlatıcılar PostgreSQL'de saklanır; bot yeniden başlasa bile geri yüklenir.
- 🎛️ **İnteraktif Menü:** Mesaj yazmadan butonlarla yönetebileceğiniz modern Inline Keyboard arayüzü.
- ✨ **Yetenek Rehberi:** Ana menüdeki “Bu bot ne işe yarar?” ekranı bütün özellikleri tek yerde açıklar.

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
```

`DATABASE_URL` yerel geliştirmede isteğe bağlıdır. Render üzerinde kalıcı kullanım için
harici bir PostgreSQL bağlantısı tanımlayın; aksi halde geçici SQLite dosyası kullanılır.

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
| `/hakkinda` | Botun yapabildiği bütün işleri kategoriler halinde gösterir | `/hakkinda` |
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
| `/takvimindir` | Takvimi Google/Outlook uyumlu ICS olarak indirir | `/takvimindir` |
| `/disaaktar` | Kişisel verileri JSON olarak indirir | `/disaaktar` |
| `/verilerimisil` | Tüm kişisel verileri onayla siler | `/verilerimisil` |

Doğal dil örnekleri: `yarın saat 10 doktoru hatırlat`, `250 TL market haftalık alışveriş`, `alışkanlık ekle Kitap oku`.

## Mini App

`miniapp/index.html` statik bir HTTPS adresinde yayınlanıp `MINI_APP_URL` ortam değişkenine yazıldığında ana menüde görsel panel açılır. Panel Bugün, Görevler, Alışkanlıklar ve Harcamalar ekranlarını Telegram botuna bağlar.
| `/help` | Tüm komutları ve yardım rehberini gösterir | `/help` |
