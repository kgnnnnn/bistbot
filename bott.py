import time
import random
import os
import re
import json
import requests
import yfinance as yf
from flask import Flask
from threading import Thread
import openai
import xml.etree.ElementTree as ET
import html
from datetime import datetime, timedelta
from urllib.parse import quote


openai.api_key = os.getenv("OPENAI_API_KEY")
print("DEBUG OPENAI KEY:", openai.api_key[:10] if openai.api_key else "YOK", flush=True)

BOT_TOKEN = "8116276773:AAHoSQAthKmijTE62bkqtGQNACf0zi0JuCs"
URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# Istanbul time helper (UTC+3). If your server is UTC, this aligns with TR time.
IST_UTC_OFFSET_HOURS = 3
def now_istanbul():
    return datetime.utcnow() + timedelta(hours=IST_UTC_OFFSET_HOURS)

# =============== TELEGRAM ===============
def get_updates(offset=None):
    try:
        r = requests.get(URL + "getUpdates", params={"timeout": 100, "offset": offset}, timeout=100)
        return r.json()
    except Exception as e:
        print("get_updates error:", e, flush=True)
        return {}

def send_message(chat_id, text):
    try:
        requests.post(
            URL + "sendMessage",
            params={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
    except Exception as e:
        print("Send error:", e, flush=True)

# =============== FAVORİ SİSTEMİ ===============
FAVORI_FILE = "favoriler.json"

def load_favorites():
    try:
        if not os.path.exists(FAVORI_FILE):
            return {}
        with open(FAVORI_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("Favori yükleme hatası:", e, flush=True)
        return {}

def save_favorites(data):
    try:
        with open(FAVORI_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("Favori kaydetme hatası:", e, flush=True)

# =============== ALARM SİSTEMİ ===============
ALARM_FILE = "alarmlar.json"

def load_alarms():
    try:
        if not os.path.exists(ALARM_FILE):
            return {}
        with open(ALARM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("Alarm yükleme hatası:", e, flush=True)
        return {}

def save_alarms(data):
    try:
        with open(ALARM_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("Alarm kaydetme hatası:", e, flush=True)

# =============== SAYI BİÇİMLENDİRME ===============
def format_number(num):
    """Sayıları 12.345.678 formatında döndürür."""
    try:
        if num in (None, "—"):
            return None
        if isinstance(num, str):
            num = num.replace(".", "").replace(",", "")
            if not num.isdigit():
                return None
            num = int(num)
        return f"{int(num):,}".replace(",", ".")
    except Exception:
        return None

# =============== HABERLER (Google RSS) ===============
import xml.etree.ElementTree as ET

def get_news(symbol):
    """Google News RSS üzerinden hisseye ait son 3 haberi döndürür."""
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+Borsa+İstanbul+OR+hisse&hl=tr&gl=TR&ceid=TR:tr"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return "📰 Haberler alınamadı."

        xml_data = r.text.encode("utf-8", "ignore").decode("utf-8", "ignore")
        xml_data = xml_data.replace("&", "&amp;")

        root = ET.fromstring(xml_data)
        items = root.findall(".//item")[:3]
        if not items:
            return "📰 Lütfen hisse kodunu doğru giriniz. (Örn: ASELS)"

        haberler = ["🗞️ <b>Son Haberler</b>"]
        for item in items:
            title = (item.find("title").text or "").strip()
            link = (item.find("link").text or "").strip()
            pub = (item.find("pubDate").text or "").split("+")[0].strip() if item.find("pubDate") is not None else ""
            haberler.append(f"🔹 <a href='{link}'>{title}</a> ({pub})")

        return "\n".join(haberler)

    except Exception as e:
        print("get_news hata:", e, flush=True)
        return "📰 Haberler alınamadı."

# =============== HABER ANALİZİ (OpenAI - Kriptos AI) ===============
def analyze_news_with_ai(news_text):
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return "⚠️ AI yorum yapılamadı (API anahtarı eksik)."
        if "Haberler alınamadı" in news_text or "Lütfen" in news_text:
            return "⚠️ Geçerli haber bulunamadı."

        prompt = (
            "Aşağıda Borsa İstanbul'da işlem gören bir hisseye ait son haber başlıkları bulunuyor.\n"
            "Bu başlıkları analiz et; 1-2 cümlelik kısa bir Türkçe özet oluştur ve genel piyasa hissiyatını belirt (pozitif / negatif / nötr).\n"
            "Yatırım tavsiyesi verme.\n"
            "Yanıtını '🤖 <b>Kriptos AI Haber Analizi:</b>' etiketiyle başlat.\n\n"
            f"{news_text}"
        )

        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "max_tokens": 120},
            timeout=15,
        )
        if r.status_code != 200:
            return "⚠️ AI yorum alınamadı."
        data = r.json()
        msg = data.get("choices", [{}])[0].get("message", {}).get("content")
        return msg.strip() if msg else "⚠️ AI yorum alınamadı."
    except Exception as e:
        print("AI yorum hatası:", e, flush=True)
        return "⚠️ AI yorum alınamadı."

# =============== YAHOO FİYAT ===============
def get_price(symbol):
    """Yahoo Finance üzerinden fiyat, açılış, kapanış, tavan, taban bilgilerini çeker."""
    try:
        time.sleep(random.uniform(0.3, 0.6))
        ticker = yf.Ticker(symbol.upper() + ".IS")
        info = ticker.info
        if not info or not info.get("currentPrice"):
            return None
        return {
            "fiyat": info.get("currentPrice"),
            "acilis": info.get("open"),
            "kapanis": info.get("previousClose"),
            "tavan": info.get("dayHigh"),
            "taban": info.get("dayLow"),
        }
    except Exception as e:
        print("get_price hata:", e, flush=True)
        return None

# =============== TRADINGVIEW (RSI, EMA50/EMA200) ===============
TV_URL = "https://tradingview-real-time.p.rapidapi.com/technicals/summary"
TV_HEADERS = {
    "x-rapidapi-key": "1749e090ffmsh612a371009ddbcap1c2f2cjsnaa23aba94831",
    "x-rapidapi-host": "tradingview-real-time.p.rapidapi.com",
}

def get_tv_analysis(symbol):
    try:
        r = requests.get(TV_URL, headers=TV_HEADERS, params={"query": symbol.upper()}, timeout=8)
        data = r.json().get("data", {})
        return {"rsi": data.get("RSI"), "ema50": data.get("EMA50"), "ema200": data.get("EMA200")}
    except Exception as e:
        print("get_tv_analysis hata:", e, flush=True)
        return None

def map_rsi_label(rsi):
    """RSI değerine göre sinyal döndürür."""
    try:
        r = float(rsi)
        r = round(r, 2)
        if r < 20:
            return f"{r} (GÜÇLÜ AL)"
        elif r < 30:
            return f"{r} (AL)"
        elif r > 85:
            return f"{r} (GÜÇLÜ SAT)"
        elif r > 70:
            return f"{r} (SAT)"
        else:
            return f"{r} (NÖTR)"
    except:
        return "NÖTR"

def map_ema_signal(ema50, ema200):
    try:
        return "AL" if float(ema50) >= float(ema200) else "SAT"
    except:
        return "NÖTR"

def combine_recommendation(ema_sig, rsi_label):
    """EMA ve RSI sinyallerine göre Kriptos AI genel yorumu üretir."""
    if ("AL" in rsi_label or "GÜÇLÜ AL" in rsi_label) and ema_sig == "AL":
        return "AL"
    if ("SAT" in rsi_label or "GÜÇLÜ SAT" in rsi_label) and ema_sig == "SAT":
        return "SAT"
    return "NÖTR"

# --- BILANÇO ÖZETİ (PASİF - Placeholder Versiyonu) ---
def get_balance_summary(symbol):
    """Bilanço özeti şu anda pasif."""
    return {"summary": "🤖 <b>Bilanço Özeti</b>\n<b>Kriptos AI:</b> Çok yakında"}

##-------------------------MESAJ OLUŞTURMA-------------------------##
def build_message(symbol):
    symbol = symbol.strip().upper()
    info = get_price(symbol)
    tech = get_tv_analysis(symbol)
    lines = [f"💹 <b>{symbol}</b> Hisse Özeti (BIST100)"]

    # --- Fiyat ---
    if info:
        fiyat_fmt = format_number(info['fiyat'])
        lines.append(f"💰 Fiyat: {fiyat_fmt if fiyat_fmt is not None else info['fiyat']} TL")
        if info.get("acilis"):
            lines.append(f"📈 Açılış: {info['acilis']}")
        if info.get("kapanis"):
            lines.append(f"📉 Kapanış: {info['kapanis']}")
        if info.get("tavan"):
            lines.append(f"🔼 Tavan: {info['tavan']}")
        if info.get("taban"):
            lines.append(f"🔽 Taban: {info['taban']}")

    # --- Teknik Analiz ---
    if tech:
        rsi_val = tech.get("rsi")
        ema50, ema200 = tech.get("ema50"), tech.get("ema200")
        rsi_label = map_rsi_label(rsi_val)
        ema_sig = map_ema_signal(ema50, ema200)
        overall = combine_recommendation(ema_sig, rsi_label)
        lines.append("\n📊 <b>Teknik Analiz</b>")
        lines.append(f"⚡ RSI: {rsi_label}")
        lines.append(f"🔄 EMA(50/200): {ema_sig}")
        lines.append(f"🤖 <b>Kriptos AI:</b> {overall}")

    # --- Bilanço Özeti ---
    fin = get_balance_summary(symbol)
    if fin and fin.get("summary"):
        lines.append("\n🏦 <b>Bilanço Özeti</b>")
        lines.append(fin["summary"])

    # --- Haberler ---
    news_text = get_news(symbol)
    lines.append("\n" + news_text)
    ai_comment = analyze_news_with_ai(news_text)
    lines.append("\n" + ai_comment)

    lines.append("\n<b>💬 Görüş & Öneri:</b> @kriptosbtc")
    return "\n".join(lines)

# --------------- FAVORİ ÖZETİ (TEKRAR KULLANILABİLİR) ---------------
def build_favorite_line(sym):
    info = get_price(sym)
    tech = get_tv_analysis(sym)
    if not info:
        return f"• {sym}: veri yok"
    fiyat_fmt = format_number(info.get("fiyat"))
    rsi_val = tech.get("rsi") if tech else None
    rsi_label = map_rsi_label(rsi_val) if rsi_val is not None else "N/A"
    ema_sig = map_ema_signal(tech.get("ema50"), tech.get("ema200")) if tech else "N/A"
    return f"• <b>{sym}</b> — {fiyat_fmt if fiyat_fmt is not None else info.get('fiyat')} TL | RSI: {rsi_label} | EMA(50/200): {ema_sig}"

# =============== OTOMATİK FAVORİ GÖNDERİCİ ===============
_last_sent_marker = {"morning": None, "evening": None}

def send_favorite_summaries_loop():
    """Her gün 10:00 ve 17:00 (İstanbul) favori hisseleri gönderir."""
    while True:
        try:
            now = now_istanbul()
            hhmm = now.strftime("%H:%M")
            # duplicate engeli: aynı dakika içinde bir kez
            if hhmm == "10:00" and _last_sent_marker["morning"] != now.strftime("%Y-%m-%d 10:00"):
                _last_sent_marker["morning"] = now.strftime("%Y-%m-%d 10:00")
                _broadcast_favorites(now_label="Sabah")
            if hhmm == "17:00" and _last_sent_marker["evening"] != now.strftime("%Y-%m-%d 17:00"):
                _last_sent_marker["evening"] = now.strftime("%Y-%m-%d 17:00")
                _broadcast_favorites(now_label="Akşam")
        except Exception as e:
            print("Favori döngü hatası:", e, flush=True)
        time.sleep(20)  # 20 sn’de bir kontrol

def _broadcast_favorites(now_label="Özet"):
    favorites = load_favorites()
    if not favorites:
        print("Favori listesi boş, yayın yok.", flush=True)
        return
    ts = now_istanbul().strftime("%d.%m.%Y %H:%M")
    for uid, fav_list in favorites.items():
        if not fav_list:
            continue
        send_message(uid, f"📊 <b>Favori Hisselerin {now_label} Özeti</b> — {ts}")
        for sym in fav_list[:20]:  # güvenlik: kullanıcı başına ilk 20 hisse
            try:
                msg = build_message(sym.upper())
                send_message(uid, msg)
                time.sleep(1)  # API limit nazikliği
            except Exception as e:
                send_message(uid, f"⚠️ {sym} gönderilirken hata oluştu: {e}")

# =============== ALARM KONTROL DÖNGÜSÜ ===============
def alarm_check_loop():
    """Her 60 sn'de bir aktif alarmları kontrol eder."""
    while True:
        try:
            alarms = load_alarms()
            if not alarms:
                time.sleep(60)
                continue

            # Tüm alarmlardaki sembolleri topla (her sembol için tek fiyat sorgusu)
            symbols = set()
            for _, alist in alarms.items():
                for a in alist:
                    symbols.add(a.get("symbol", "").upper())

            prices = {}
            for sym in symbols:
                info = get_price(sym)
                prices[sym] = info["fiyat"] if info else None
                time.sleep(0.3)  # Yahoo'ya nazik olalım

            changed = False
            # Kullanıcı bazlı alarmları dolaş
            for uid, alist in list(alarms.items()):
                remaining = []
                for a in alist:
                    sym = a.get("symbol", "").upper()
                    target = a.get("target")
                    direction = a.get("direction", "up")
                    price = prices.get(sym)

                    if price is None or target is None:
                        remaining.append(a)
                        continue

                    triggered = False
                    if direction == "up" and price >= target:
                        triggered = True
                    elif direction == "down" and price <= target:
                        triggered = True

                    if triggered:
                        msg = (
                            "🚨 <b>Fiyat Alarmı Tetiklendi!</b>\n"
                            f"Hisse: <b>{sym}</b>\n"
                            f"Hedef: <b>{target} TL</b>\n"
                            f"Anlık: <b>{round(price, 2)} TL</b>"
                        )
                        send_message(uid, msg)
                        changed = True
                    else:
                        remaining.append(a)

                alarms[uid] = remaining

            if changed:
                save_alarms(alarms)

        except Exception as e:
            print("Alarm döngü hatası:", e, flush=True)

        time.sleep(60)  # 1 dakika

# =============== ANA DÖNGÜ ===============
def main():
    print("🚀 Kriptos Borsa Botu aktif!", flush=True)
    # otomatik favori thread'i
    Thread(target=send_favorite_summaries_loop, daemon=True).start()
    # alarm kontrol thread'i
    Thread(target=alarm_check_loop, daemon=True).start()

    last_update_id = None
    processed = set()
    favorites = load_favorites()
    alarms = load_alarms()

    while True:
        updates = get_updates(last_update_id)
        if not updates:
            time.sleep(0.8)
            continue
        results = updates.get("result", [])
        results.sort(key=lambda x: x.get("update_id", 0))
        for item in results:
            uid = item.get("update_id")
            if uid in processed:
                continue
            processed.add(uid)
            last_update_id = uid + 1
            msg_data = item.get("message", {})
            chat_id = msg_data.get("chat", {}).get("id")
            text = (msg_data.get("text") or "").strip()
            if not chat_id or not text:
                continue

            # ---- /start ----
            if text.lower() == "/start":
                msg = (
                    "👋 <b>Kriptos BIST100 Takip Botu'na Hoş Geldin!</b>\n\n"
                    "💬 Sadece hisse kodunu (örnek: ASELS, THYAO...) yazın.\n\n"
                    "💡 Algoritmamız fiyat, güncel haberler, hacim vb. bilgileri iletir.\n\n"
                    "🤖 Yapay zeka destekli algoritmamız RSI ve EMA indikatör analizleri yapar ve (al-sat-vb.) önermeler üretir.\n\n"
                    "⚙️ Veriler: TradingView & Yahoo Finance'den sağlanmaktadır.\n\n"
                    "❗️  UYARI: Bilgiler kesinlikle YATIRIM TAVSİYESİ kapsamında değildir!\n\n"
                    "📊 Komut örneği: <b>ASELS/asels</b>\n\n"
                    "⭐ Favori komutları:\n"
                    "/favori ekle ASELS\n"
                    "/favori sil ASELS\n"
                    "/favori liste\n\n"
                    "🔔 Alarm komutları:\n"
                    "/alarm ekle ASELS 190\n"
                    "/alarm sil ASELS 190\n"
                    "/alarm liste\n\n"
                    "⏰ Otomatik özet: Favori hisselerin her gün 10:00 ve 17:00'de iletilir."
                )
                send_message(chat_id, msg)
                continue

            # ---- /favori komutları ----
            if text.lower().startswith("/favori"):
                parts = text.split()
                cmd = parts[1] if len(parts) > 1 else None

                if cmd == "ekle" and len(parts) >= 3:
                    sym = parts[2].upper()
                    if not sym.isalpha():
                        send_message(chat_id, "⚠️ Lütfen geçerli bir hisse kodu girin. (Örn: ASELS)")
                        continue
                    favs = favorites.get(str(chat_id), [])
                    if sym not in favs:
                        favs.append(sym)
                        favorites[str(chat_id)] = favs
                        save_favorites(favorites)
                        send_message(chat_id, f"✅ <b>{sym}</b> favorilerine eklendi.")
                    else:
                        send_message(chat_id, f"ℹ️ <b>{sym}</b> zaten favorilerinde mevcut.")
                    continue

                elif cmd == "sil" and len(parts) >= 3:
                    sym = parts[2].upper()
                    favs = favorites.get(str(chat_id), [])
                    if sym in favs:
                        favs.remove(sym)
                        favorites[str(chat_id)] = favs
                        save_favorites(favorites)
                        send_message(chat_id, f"🗑️ <b>{sym}</b> favorilerinden kaldırıldı.")
                    else:
                        send_message(chat_id, f"⚠️ <b>{sym}</b> favorilerinde bulunamadı.")
                    continue

                elif cmd in ["liste", "goster"]:
                    favs = favorites.get(str(chat_id), [])
                    if not favs:
                        send_message(chat_id, "⭐ Henüz hiç favorin yok. Örnek: /favori ekle ASELS")
                    else:
                        fav_text = "\n".join([f"• {s}" for s in favs])
                        send_message(chat_id, f"⭐ <b>Favori Hisselerin:</b>\n{fav_text}")
                    continue

                else:
                    send_message(chat_id, "⚙️ Kullanım:\n/favori ekle ASELS\n/favori sil ASELS\n/favori liste")
                    continue

            # ---- /alarm komutları ----
            if text.lower().startswith("/alarm"):
                parts = text.split()
                cmd = parts[1] if len(parts) > 1 else None

                # /alarm ekle ASELS 190
                if cmd == "ekle" and len(parts) >= 4:
                    sym = parts[2].upper()
                    try:
                        target = float(parts[3].replace(",", "."))
                    except ValueError:
                        send_message(chat_id, "⚠️ Hedef fiyatı sayısal olarak giriniz. Örn: /alarm ekle ASELS 190")
                        continue

                    info = get_price(sym)
                    if not info or not info.get("fiyat"):
                        send_message(chat_id, f"⚠️ {sym} için anlık fiyat alınamadı.")
                        continue

                    current = float(info["fiyat"])
                    if target > current:
                        direction = "up"
                        dir_text = "üzeri"
                    elif target < current:
                        direction = "down"
                        dir_text = "altı"
                    else:
                        direction = "up"
                        dir_text = "seviyesi"

                    uid_key = str(chat_id)
                    user_alarms = alarms.get(uid_key, [])
                    # aynı sembol + target varsa tekrar ekleme
                    exists = any(a.get("symbol") == sym and float(a.get("target")) == target for a in user_alarms)
                    if exists:
                        send_message(chat_id, f"ℹ️ <b>{sym}</b> için {target} TL alarmı zaten kayıtlı.")
                        continue

                    user_alarms.append({
                        "symbol": sym,
                        "target": target,
                        "direction": direction
                    })
                    alarms[uid_key] = user_alarms
                    save_alarms(alarms)
                    send_message(chat_id, f"🔔 <b>{sym}</b> için <b>{target} TL</b> ({dir_text}) alarmı kaydedildi.")
                    continue

                # /alarm sil ASELS 190
                elif cmd == "sil" and len(parts) >= 4:
                    sym = parts[2].upper()
                    try:
                        target = float(parts[3].replace(",", "."))
                    except ValueError:
                        send_message(chat_id, "⚠️ Hedef fiyatı sayısal olarak giriniz. Örn: /alarm sil ASELS 190")
                        continue

                    uid_key = str(chat_id)
                    user_alarms = alarms.get(uid_key, [])
                    new_list = [a for a in user_alarms if not (a.get("symbol") == sym and float(a.get("target")) == target)]
                    if len(new_list) == len(user_alarms):
                        send_message(chat_id, f"⚠️ <b>{sym}</b> için {target} TL alarmı bulunamadı.")
                    else:
                        alarms[uid_key] = new_list
                        save_alarms(alarms)
                        send_message(chat_id, f"🗑️ <b>{sym}</b> {target} TL alarmı silindi.")
                    continue

                # /alarm liste
                elif cmd in ["liste", "goster"]:
                    uid_key = str(chat_id)
                    user_alarms = alarms.get(uid_key, [])
                    if not user_alarms:
                        send_message(chat_id, "🔔 Aktif alarmın yok. Örnek: /alarm ekle ASELS 190")
                    else:
                        lines = ["🔔 <b>Aktif Alarmların:</b>"]
                        for a in user_alarms:
                            sym = a.get("symbol", "")
                            target = a.get("target", "")
                            direction = a.get("direction", "up")
                            if direction == "up":
                                dir_text = "üzeri"
                            elif direction == "down":
                                dir_text = "altı"
                            else:
                                dir_text = "seviyesi"
                            lines.append(f"• {sym} — {target} TL ({dir_text})")
                        send_message(chat_id, "\n".join(lines))
                    continue

                else:
                    send_message(chat_id, "🔔 Kullanım:\n/alarm ekle ASELS 190\n/alarm sil ASELS 190\n/alarm liste")
                    continue

            # ---- Hisse sorgusu ----
            symbol = text.split()[0].lstrip("/").upper()
            print(f"Gelen istek: {symbol}", flush=True)
            reply = build_message(symbol)
            send_message(chat_id, reply)
            time.sleep(0.8)
        time.sleep(0.5)

# =============== FLASK (Render Portu) ===============
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot aktif, Render portu açık!", 200

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run).start()

if __name__ == "__main__":
    main()
