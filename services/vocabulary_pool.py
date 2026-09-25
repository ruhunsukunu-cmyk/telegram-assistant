"""Editorial A2 starter selection; original Turkish glosses and examples.

Level reference: https://www.goethe.de/ins/tr/tr/spr/prf/ueb/pa2.html
Not an official or exhaustive Goethe list; A1/A2 vocabulary overlaps.
Stable IDs must not change when the pool grows.
"""

DATA = '''
Eğitim|die Prüfung – die Prüfungen|sınav|Die Prüfung beginnt morgen.
Eğitim|die Aufgabe – die Aufgaben|görev, alıştırma|Diese Aufgabe ist nicht schwer.
Eğitim|erklären – hat erklärt|açıklamak|Die Lehrerin erklärt die Aufgabe.
Eğitim|üben – hat geübt|alıştırma yapmak|Ich übe jeden Morgen Deutsch.
Eğitim|wiederholen – hat wiederholt|tekrar etmek|Wir wiederholen die neuen Wörter.
Eğitim|bestehen – hat bestanden|sınavı geçmek|Sie hat die Prüfung bestanden.
Eğitim|der Fehler – die Fehler|hata|Ich finde einen Fehler im Text.
Eğitim|die Lösung – die Lösungen|çözüm|Wir suchen eine Lösung.
İş|die Bewerbung – die Bewerbungen|iş başvurusu|Ich schreibe eine Bewerbung.
İş|die Erfahrung – die Erfahrungen|deneyim|Sie hat Erfahrung im Verkauf.
İş|der Beruf – die Berufe|meslek|Welchen Beruf möchtest du lernen?
İş|verdienen – hat verdient|para kazanmak|Er verdient genug Geld.
İş|sich bewerben um + Akk. – hat sich beworben|bir işe başvurmak|Ich bewerbe mich um diese Stelle.
İş|die Stelle – die Stellen|iş pozisyonu|Diese Stelle ist noch frei.
İş|der Termin – die Termine|randevu|Ich habe am Montag einen Termin.
İş|vereinbaren – hat vereinbart|kararlaştırmak|Wir vereinbaren einen Termin.
Ulaşım|umsteigen – ist umgestiegen|aktarma yapmak|In Berlin müssen wir umsteigen.
Ulaşım|die Verspätung – die Verspätungen|gecikme|Der Zug hat zehn Minuten Verspätung.
Ulaşım|die Verbindung – die Verbindungen|ulaşım bağlantısı|Es gibt eine direkte Verbindung.
Ulaşım|verpassen – hat verpasst|kaçırmak|Ich habe den Bus verpasst.
Ulaşım|die Richtung – die Richtungen|yön|Wir fahren in Richtung Bahnhof.
Ulaşım|die Haltestelle – die Haltestellen|durak|Die Haltestelle ist neben der Schule.
Ulaşım|abfahren – ist abgefahren|hareket etmek|Der Zug fährt um acht Uhr ab.
Ulaşım|ankommen – ist angekommen|varmak|Wir kommen heute Abend an.
Sağlık|die Untersuchung – die Untersuchungen|muayene, inceleme|Die Untersuchung dauert zwanzig Minuten.
Sağlık|das Rezept – die Rezepte|reçete, yemek tarifi|Der Arzt gibt mir ein Rezept.
Sağlık|die Schmerzen (çoğul)|ağrılar|Ich habe Schmerzen im Rücken.
Sağlık|sich erholen – hat sich erholt|dinlenip toparlanmak|Am Wochenende erhole ich mich.
Sağlık|sich bewegen – hat sich bewegt|hareket etmek|Ich möchte mich mehr bewegen.
Sağlık|untersuchen – hat untersucht|muayene etmek, incelemek|Die Ärztin untersucht meinen Arm.
Sağlık|die Gesundheit (çoğul kullanılmaz)|sağlık|Bewegung ist gut für die Gesundheit.
Sağlık|regelmäßig|düzenli olarak|Ich gehe regelmäßig spazieren.
Günlük yaşam|die Rechnung – die Rechnungen|fatura, hesap|Ich bezahle die Rechnung morgen.
Günlük yaşam|die Quittung – die Quittungen|ödeme makbuzu|Bitte geben Sie mir eine Quittung.
Günlük yaşam|umtauschen – hat umgetauscht|satın alınanı değiştirmek|Ich möchte diese Jacke umtauschen.
Günlük yaşam|sparen – hat gespart|tasarruf etmek|Ich spare jeden Monat etwas Geld.
Günlük yaşam|sich entscheiden für + Akk. – hat sich entschieden|bir şeyi seçmeye karar vermek|Ich entscheide mich für das blaue Hemd.
Günlük yaşam|vergleichen – hat verglichen|karşılaştırmak|Wir vergleichen die Preise.
Günlük yaşam|das Angebot – die Angebote|teklif, indirimli ürün|Dieses Angebot gilt bis Freitag.
Günlük yaşam|günstig|uygun fiyatlı, elverişli|Das Zimmer ist günstig.
İletişim|die Meinung – die Meinungen|görüş, fikir|Deine Meinung ist mir wichtig.
İletişim|der Vorschlag – die Vorschläge|öneri|Ich habe einen Vorschlag.
İletişim|zustimmen + Dat. – hat zugestimmt|katılmak, onaylamak|Ich stimme dir zu.
İletişim|sich erinnern an + Akk. – hat sich erinnert|hatırlamak|Ich erinnere mich an den Ausflug.
İletişim|sich interessieren für + Akk. – hat sich interessiert|ilgi duymak|Ich interessiere mich für Geschichte.
İletişim|sich freuen auf + Akk. – hat sich gefreut|gelecekteki bir şeyi sevinçle beklemek|Wir freuen uns auf die Ferien.
İletişim|wahrscheinlich|muhtemelen|Morgen regnet es wahrscheinlich.
İletişim|trotzdem|yine de|Es regnet, trotzdem gehen wir spazieren.
'''

WORDS = [dict(id=str(i), topic=p[0], german=p[1], turkish=p[2], example=p[3])
         for i, line in enumerate(DATA.strip().splitlines(), 1)
         for p in [line.split('|')]]
BY_ID = {w['id']: w for w in WORDS}
