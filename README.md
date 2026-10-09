# Ruhun Sükûnu · Shorts takipçisi

Tek sahipli Telegram botu; yalnız Ruhun Sükûnu (UCwtUrD_YkZ7xoofBsuwzTMA) için salt okunur YouTube analizleri. Eski kişisel asistan, Almanca, takvim ve günlük bildirim kodları kaldırıldı. Eski uygulama verileri bu kod değişikliğiyle otomatik silinmez; aşağıdaki canlı geçiş uygulanmalıdır.

## Yerel doğrulama

Python 3.12+ kullan. requirements.txt bağımlılıklarını kur. Repo .venv/Scripts/python.exe -m unittest discover -s tests -q ile fixture testlerini çalıştır. Testler work/tests altında kendi SQLite dosyalarını kullanır; canlı anahtar veya veri kullanmaz. bot.py yalnız ruhun_bot.main girişidir.

## Yapılandırma

.env.example değişkenlerini incele. RUHUN_OWNER_ID ve RUHUN_CHAT_ID sahibin özel sohbeti için açıkça tanımlanmalıdır. Bunlar yoksa erişim ve zamanlanmış görevler kapalıdır. Eski CALENDAR_USER_ID/CALENDAR_CHAT_ID alanlarına otomatik bağımlılık yoktur.

SQLite: mevcut kalıcı /data volume korunur, temiz /data/ruhun.db kullanılır. PostgreSQL: mevcut DATABASE_URL korunur; başka uygulama tabloları asla silinmez. Yeni tablolar ruhun_records ve ruhun_leases; JSON alanlarındaki namespace ayrımı videos/daily/summaries/production/experiments/reports/ai/meta/deliveries/alerts için kullanılır.

Varsayılan RUHUN_JOBS_ENABLED=false. Etkinleştirilince İstanbul saati 10:00 sessiz toplama, pazartesi 11:00 haftalık rapor, salı 11:15 yalnız önceki gün başarısız AI için bir yeniden deneme. Aynı raporu görüntülemek AI çağrısı yapmaz. İlk aktarım ve gerçek sorgu doğrulanmadan işleri açma.

## Google bağlantısı

Desktop OAuth istemcisini Google Cloud projesinde hazırla; YouTube Data ve Analytics API'leri açık olmalı. tools/connect_youtube.py ABSOLUTE_OAUTH_CLIENT_JSON çalıştır. Kullanıcı tarayıcıda doğru kanalı seçer. Yalnız youtube.readonly + yt-analytics.readonly kabul edilir; eski geniş yetkili uploader oturumu reddedilir. Yardımcı doğrulama sonrası sırları gitignore kapsamındaki .ruhun-youtube-secrets.json dosyasına yazar; terminale yazmaz. Sırları Railway değişkenlerine taşı ve yerel sır dosyasını gerektiğinde temizle. OAuth Testing modunda yenileme anahtarı yedi günde sona erebilir; kalıcılığı doğrula ve kurulum kaydına yaz.

## Ücretsiz Gemini

Yeni özellik sadece RUHUN_GEMINI_API_KEY kullanır; eski GEMINI_API_KEY otomatik alınmaz. AI Studio'da anahtarın projesini, Free Tier durumunu ve faturalandırma bağlı olmadığını gözle doğrula; tarihi/sır içermeyen proje kimliğini RUHUN_GEMINI_FREE_TIER_EVIDENCE içine kaydet, ardından RUHUN_GEMINI_FREE_TIER_VERIFIED=true yap. Bu bayrak faturalandırma kontrolünün yerine geçmez. Ücretli proje anahtarı kullanılmaz; faturalandırma açılmaz, ücretli fallback yoktur. gemini-2.5-flash kullanılır; erişilemezse AI bekler. Ücretsiz katmanda Google gönderilen içerikleri ürün geliştirmesinde kullanabilir. Yalnız kanalın gerekli sayısal sonuçları ve üretim notları gönderilir.

AI son yirmi uygun videoyu nitel yorumlar; beş uygun örnek yoksa çağrı yapılmaz. Rakamları kod hesaplar, model metninde rakamsal iddialar reddedilir. Şema ve video referansları doğrulanır. Serbest metin ve eski komutlar modele aktarılmaz.

## Canlı sıfırlama — geri alınamaz, eski veri yedeği yok

1. Yerel testler geçmeli. Railway repo/branch/servis ve tüm eski bot örnekleri doğrulanmalı.
2. Eski botu durdur. Eski veriye yazan süreç kalmadığını kontrol et. SSH temizliği için aynı hizmete RUHUN_MAINTENANCE=true ile yeni kodu dağıt: bu HTTP bakım ekranı Telegram'a bağlanmaz, veritabanı veya görev açmaz. Temizlik tamamlanınca false yap; eski sürümü yeniden açma.
3. tools/reset_legacy.py --sqlite ABSOLUTE_DB ile şema/tablolar/sayılar envanteri al. Kişisel kayıt içeriklerini dışa aktarma. Render SOURCE_DATABASE_URL varsa aynı uygulamanın eski PostgreSQL kaynağı için DATABASE_URL geçici olarak işlem ortamında ayarlanarak --postgres envanterini de doğrula; URL'yi yazdırma.
4. Doğrulanmış hedefte --apply --stopped --confirm DELETE_LEGACY_NO_BACKUP çalıştır. Yalnız eski uygulama imzasına uyan tablolar silinir; CASCADE kullanılmaz. SQLite secure_delete ve VACUUM uygulanır. Başka tablolar varsa dosyanın tamamını silme. Eski uygulama SQLite dosyası ve sidecar dosyaları başka veri taşımıyorsa kesin yollar doğrulanıp kaldırılır. Yönetilebilir eski yedekleri ve yerel kopyaları ayrıca listeleyip temizle; sır içermeyen silme kayıtları tut. Sağlayıcı saklama kopyalarını anında silinmiş gösterme.
5. SOURCE_DATABASE_URL, CALENDAR_*, DEFAULT_CITY, MINI_APP_URL, MORNING_* ve artık kullanılmayan eski GEMINI_API_KEY kaldırılır; başka uygulamaların anahtarları iptal edilmez. Token/WEBHOOK_URL/PORT/PYTHON_VERSION/TIMEZONE/kalıcı volume korunur.
6. Yeni dağıtımda RUHUN_DROP_PENDING_UPDATES=true, RUHUN_JOBS_ENABLED=false. Başlangıç menüsü/komutları yenilendiğini, eski callbacklerin pasif olduğunu doğrula. İlk geçiş sonrası DROP_PENDING=false.
7. Gerçek kanal ve bir video sorgusunu Studio'nun aynı dönem değerleriyle karşılaştır. İlk toplamayı çalıştır; sonra JOBS_ENABLED=true. Yeniden başlat ve yalnız üç yeni işi kontrol et.
8. Sade sürümden eski bildirimli sürüme geri dönme. Sorunda JOBS_ENABLED=false ile sessiz tut. Eski silinen veriler geri getirilemez. Yeni analitik verilerin yedeği gelecekte alınabilir.

## Kullanım ve aktarım

/start /menu /help, /ruhun, /ruhun_rapor, /ruhun_disaaktar, /ruhun_aktar. Rapor görüntülemek yalnız kayıtlı veriyi okur. Günlük toplama mesaj göndermez. Belirsiz Telegram gönderimi sending/unknown kaydından otomatik tekrar edilmez; sahibi Telegram'da teslimi kontrol etmelidir.

İçe aktarım 256 KB altında UTF-8 JSON: schema_version=1, channel_id doğru, videos ve experiments listeleri. videos: video_id (önceden doğrulanmış), topic/hook/narration/visual_style (isteğe bağlı), source_urls HTTPS listesi. experiments: id, hypothesis, variable (tek değişken), video_ids, metric, window_days=7, status=draft|active|closed. Kaynak bağlantıları dinî doğrulama sayılmaz. Deneyler otomatik uygulanmaz.

Rapor son doksan günde yayımlanan Shorts kapsamındadır, kanalın tüm tarihi değildir. API günleri Pasifik saatidir; ilk yedi tam API günü, yayın gününü takip eder, 168 saat değildir. Eksik ölçüm sıfır olmaz; ortalamalar API toplu döneminden alınır. Küçük örneklemlerden nedensellik/gelir/viral vaat çıkarılmaz. Markdown/JSON dosyaları sonraki üretim sohbetlerine eklenebilir.
