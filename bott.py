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
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
import matplotlib.pyplot as plt
import matplotlib

matplotlib.use("Agg")


# =============== KALICI DİSK (Render Disk) ===============
DATA_DIR = "/opt/render/project/src/data"
os.makedirs(DATA_DIR, exist_ok=True)

FAVORI_FILE = os.path.join(DATA_DIR, "favoriler.json")
ALARM_FILE = os.path.join(DATA_DIR, "alarmlar.json")
PORTFOY_FILE = os.path.join(DATA_DIR, "portfoy.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

def load_users():
    if not os.path.exists(USERS_FILE):
        return []
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_users(users):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
    except:
        pass


openai.api_key = os.getenv("OPENAI_API_KEY")
print("DEBUG OPENAI KEY:", openai.api_key[:10] if openai.api_key else "YOK", flush=True)

BOT_TOKEN = os.getenv("BOT_TOKEN")
URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# Istanbul time helper (UTC+3). Fully timezone-aware.
IST_UTC_OFFSET_HOURS = 3


def now_istanbul():
    tr_tz = timezone(timedelta(hours=IST_UTC_OFFSET_HOURS))
    return datetime.now(timezone.utc).astimezone(tr_tz)


# =============== TELEGRAM ===============
def get_updates(offset=None):
    try:
        r = requests.get(
            URL + "getUpdates",
            params={"timeout": 100, "offset": offset},
            timeout=100,
        )
        return r.json()
    except Exception as e:
        print("get_updates error:", e, flush=True)
        return {}


def send_message(chat_id, text):
    try:
        requests.post(
            URL + "sendMessage",
            params={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
    except Exception as e:
        print("Send error:", e, flush=True)


def send_photo(chat_id, path):
    try:
        with open(path, "rb") as img:
            requests.post(
                URL + "sendPhoto",
                files={"photo": img},
                data={"chat_id": chat_id},
            )
    except Exception as e:
        print("Foto gönderme hatası:", e)


# =============== FAVORİ SİSTEMİ ===============
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


# =============== PORTFÖY SİSTEMİ ===============
def load_portfoy():
    try:
        if not os.path.exists(PORTFOY_FILE):
            return {}
        with open(PORTFOY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_portfoy(data):
    try:
        with open(PORTFOY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


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


def format_price(num):
    """Fiyatları 2 basamaklı (182.34) göstermek için."""
    try:
        if num is None:
            return "—"
        return f"{float(num):.2f}"
    except Exception:
        return str(num)


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
            pub = (
                (item.find("pubDate").text or "").split("+")[0].strip()
                if item.find("pubDate") is not None
                else ""
            )
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
            "Yanıtını '🤖 <b>Kriptos AI Haber Analizi</b>' etiketiyle başlat.\n\n"
            f"{news_text}"
        )

        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 120,
            },
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


# =============== YAHOO FİYAT (Açık/Kapalı Akıllı Sistem – Hatasız) ===============
# =================== BIST UYUMLU — TAM FALLOUGHLU GET_PRICE ===================
def get_price(symbol):
    """
    BIST için en doğru fiyat çekme yöntemi.
    Borsa açıksa anlık,
    kapalıysa gün içi son fiyat,
    veri bozuksa fallback -> regularMarketPrice -> currentPrice -> previousClose.
    """
    try:
        time.sleep(random.uniform(0.15, 0.35))

        sym = symbol.upper() + ".IS"
        t = yf.Ticker(sym)

        # --- Fiyat kaynakları ---
        fi = t.fast_info or {}
        info = t.info or {}

        # Emniyetli float converter
        def sf(x):
            try:
                return float(x) if x not in [None, ""] else None
            except:
                return None

        # --- 1) Birincil fiyat (her zaman en doğru kaynak) ---
        fiyat = sf(fi.get("last_price"))

        # Eğer last_price None veya 0 gelirse -> fallback
        if not fiyat or fiyat <= 0:
            fiyat = sf(info.get("regularMarketPrice"))

        # Hâlâ yoksa -> fallback 2
        if not fiyat or fiyat <= 0:
            fiyat = sf(info.get("currentPrice"))

        # Hâlâ yoksa -> fallback 3 (kapalıysa previousClose)
        if not fiyat or fiyat <= 0:
            fiyat = sf(fi.get("previous_close") or info.get("previousClose"))

        # SON çare: fiyat hâlâ yoksa -> güvenli dönüş
        if fiyat is None:
            return {
                "fiyat": None,
                "acilis": None,
                "kapanis": None,
                "tavan": None,
                "taban": None,
                "borsa_acik": None,
            }

        # --- Açılış, kapanış, tavan, taban ---
        acilis = sf(fi.get("open") or info.get("open"))
        kapanis = sf(fi.get("previous_close") or info.get("previousClose"))
        tavan = sf(fi.get("day_high") or info.get("dayHigh"))
        taban = sf(fi.get("day_low") or info.get("dayLow"))

        # --- Borsa açık mı? ---
        # Yahoo bazen "market_open" verir, bazen vermez
        if fi.get("market_open") is not None:
            borsa_acik = bool(fi.get("market_open"))
        else:
            # fallback: fiyat güncel mi kontrolü
            if fiyat and kapanis:
                borsa_acik = abs(fiyat - kapanis) > 0.0005
            else:
                borsa_acik = None

        return {
            "fiyat": fiyat,
            "acilis": acilis,
            "kapanis": kapanis,
            "tavan": tavan,
            "taban": taban,
            "borsa_acik": borsa_acik,
        }

    except Exception as e:
        print("get_price HATA:", e)
        return {
            "fiyat": None,
            "acilis": None,
            "kapanis": None,
            "tavan": None,
            "taban": None,
            "borsa_acik": None,
        }

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# BURANIN HEMEN ALTINA HACİM ANALİZİ FONKSİYONUNU EKLE
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

def get_volume_analysis(symbol):
    try:
        sym = symbol.upper() + ".IS"
        h = yf.Ticker(sym).history(period="1mo")

        if h is None or len(h) == 0:
            return None

        vol_today = h["Volume"].iloc[-1]
        vol_3g = h["Volume"].iloc[-3:].mean()
        vol_5g = h["Volume"].iloc[-5:].mean()

        trend = ((vol_today - vol_5g) / vol_5g) * 100 if vol_5g > 0 else 0
        money_flow = "Para Girişi" if vol_today >= vol_5g else "Para Çıkışı"

        return {
            "today": int(vol_today),
            "avg3": int(vol_3g),
            "avg5": int(vol_5g),
            "month_trend": round(trend, 2),
            "trend_dir": "Yükseliş" if trend >= 0 else "Düşüş",
            "flow_score": min(max(int((vol_today / (vol_5g + 1)) * 10), 0), 100),
            "change": round(((vol_today - vol_5g) / (vol_5g + 1)) * 100, 2)
        }

    except Exception:
        return None

# =============== BIST100 TUM LISTE (BURAYA EKLENECEK) ===============
BIST100_TICKERS = [
    "ACSEL.IS","AEFES.IS","AGHOL.IS","AHGAZ.IS","AKBNK.IS","AKCNS.IS","AKFGY.IS",
    "AKSA.IS","AKSEN.IS","ALARK.IS","ALBRK.IS","ALCAR.IS","ALKA.IS","ARCLK.IS",
    "ASELS.IS","ASTOR.IS","ASUZU.IS","BAGFS.IS","BASGZ.IS","BERA.IS","BIMAS.IS",
    "BIOEN.IS","BRSAN.IS","BRYAT.IS","CCOLA.IS","CEMTS.IS","COSMO.IS","DEVA.IS",
    "DOAS.IS","DOHOL.IS","ECILC.IS","ECZYT.IS","EGEEN.IS","EGGUB.IS","EKSUN.IS",
    "ENJSA.IS","ENKAI.IS","ERCB.IS","EREGL.IS","EUPWR.IS","FENER.IS","FROTO.IS",
    "GARAN.IS","GENTS.IS","GUBRF.IS","GWIND.IS","HALKB.IS","HEKTS.IS","HKTM.IS",
    "ICBCT.IS","IEYHO.IS","ISCTR.IS","ISDMR.IS","ISFIN.IS","ISGYO.IS","ISMEN.IS",
    "KCHOL.IS","KGYO.IS","KMPUR.IS","KONTR.IS","KONYA.IS","KORDS.IS",
    "KOZAA.IS","KOZAL.IS","KRDMD.IS","KZBGY.IS","MAVI.IS","MGROS.IS","ODAS.IS",
    "OTKAR.IS","OYAKC.IS","PARSN.IS","PGSUS.IS","PSGYO.IS","PETKM.IS",
    "QUAGR.IS","SAHOL.IS","SASA.IS","SELEC.IS","SISE.IS","SKBNK.IS","SMART.IS",
    "SMRTG.IS","SOKM.IS","TAVHL.IS","TCELL.IS","THYAO.IS","TKFEN.IS","TOASO.IS",
    "TSKB.IS","TTKOM.IS","TTRAK.IS","TUPRS.IS","TURSG.IS","ULKER.IS","VAKBN.IS",
    "VESTL.IS","YKBNK.IS","ZOREN.IS"
]

# =============== TRADINGVIEW (RSI, EMA50/EMA200) ===============
TV_URL = "https://tradingview-real-time.p.rapidapi.com/technicals/summary"
TV_HEADERS = {
    "x-rapidapi-key": "1749e090ffmsh612a371009ddbcap1c2f2cjsnaa23aba94831",
    "x-rapidapi-host": "tradingview-real-time.p.rapidapi.com",
}


def get_tv_analysis(symbol):
    try:
        r = requests.get(
            TV_URL,
            headers=TV_HEADERS,
            params={"query": symbol.upper()},
            timeout=8,
        )
        data = r.json().get("data", {})
        return {
            "rsi": data.get("RSI"),
            "ema50": data.get("EMA50"),
            "ema200": data.get("EMA200"),
        }
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
    except Exception:
        return "NÖTR"


def map_ema_signal(ema50, ema200):
    try:
        return "AL" if float(ema50) >= float(ema200) else "SAT"
    except Exception:
        return "NÖTR"


def combine_recommendation(ema_sig, rsi_label):
    """EMA ve RSI sinyallerine göre Kriptos AI genel yorumu üretir."""
    if ("AL" in rsi_label or "GÜÇLÜ AL" in rsi_label) and ema_sig == "AL":
        return "AL"
    if ("SAT" in rsi_label or "GÜÇLÜ SAT" in rsi_label) and ema_sig == "SAT":
        return "SAT"
    return "NÖTR"


# --- BİLANÇO ÖZETİ (PASİF - Placeholder Versiyonu) ---
def get_balance_summary(symbol):
    """Bilanço özeti şu anda pasif."""
    return {"summary": "🤖 <b>Bilanço Özeti</b>\n<b>Kriptos AI:</b> Çok yakında"}


# ------------------------MESAJ OLUŞTURMA------------------------- #
def build_message(symbol):
    symbol = symbol.strip().upper()
    info = get_price(symbol)
    tech = get_tv_analysis(symbol)
    lines = [f"💹 <b>{symbol}</b> Hisse Özeti (BIST100)"]

    # --- Fiyat ---
    if info:
        lines.append(f"💰 Fiyat: {format_price(info['fiyat'])} TL")
        if info.get("acilis") is not None:
            lines.append(f"📈 Açılış: {format_price(info['acilis'])} TL")
        if info.get("kapanis") is not None:
            lines.append(f"📉 Kapanış: {format_price(info['kapanis'])} TL")
        if info.get("tavan") is not None:
            lines.append(f"🔼 Tavan: {format_price(info['tavan'])} TL")
        if info.get("taban") is not None:
            lines.append(f"🔽 Taban: {format_price(info['taban'])} TL")

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

    # --- Hacim Analizi ---
    vol = get_volume_analysis(symbol)
    if vol:
        lines.append("\n📊 <b>Hacim Analizi</b>")
        lines.append(f"📌 Günlük Hacim: {format_number(vol['today'])}")
        lines.append(f"📌 3G Ortalama: {format_number(vol['avg3'])}")
        lines.append(f"📌 5G Ortalama: {format_number(vol['avg5'])}")
        lines.append(f"📌 1 Ay Trend: %{vol['month_trend']} ({vol['trend_dir']})")
        lines.append(f"📌 Para Akışı Skoru: {vol['flow_score']}/100")


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


def build_favorite_line(sym):
    info = get_price(sym)
    tech = get_tv_analysis(sym)
    vol = get_volume_analysis(sym)  # <-- HACİM ANALİZİ EKLENDİ

    if not info:
        return f"• {sym}: veri yok"

    fiyat_txt = format_price(info.get("fiyat"))
    rsi_val = tech.get("rsi") if tech else None
    rsi_label = map_rsi_label(rsi_val) if rsi_val is not None else "N/A"
    ema_sig = map_ema_signal(tech.get("ema50"), tech.get("ema200")) if tech else "N/A"

    # --- Hacim Mini-Özet ---
    if vol:
        vol_txt = (
            f"Hacim: G:{format_number(vol['today'])} | "
            f"3G:{format_number(vol['avg3'])} | "
            f"5G:{format_number(vol['avg5'])} | "
            f"Trend:%{vol['month_trend']} {vol['trend_dir']} | "
            f"Skor:{vol['flow_score']}/100"
        )
    else:
        vol_txt = "Hacim: veri yok"

    return (
        f"• <b>{sym}</b> — {fiyat_txt} TL\n"
        f"   RSI: {rsi_label} | EMA(50/200): {ema_sig}\n"
        f"   📊 {vol_txt}"
    )



# ============== OTOMATİK FAVORİ GÖNDERİCİ ===============
_last_sent_marker = {"morning": None, "evening": None}


def send_favorite_summaries_loop():
    """Her gün 10:00 ve 17:00 (İstanbul) favori hisseleri gönderir."""
    while True:
        try:
            now = now_istanbul()
            hhmm = now.strftime("%H:%M")
            # duplicate engeli: aynı dakika içinde bir kez
            if (
                hhmm == "10:00"
                and _last_sent_marker["morning"] != now.strftime("%Y-%m-%d 10:00")
            ):
                _last_sent_marker["morning"] = now.strftime("%Y-%m-%d 10:00")
                _broadcast_favorites(now_label="Sabah")
            if (
                hhmm == "17:00"
                and _last_sent_marker["evening"] != now.strftime("%Y-%m-%d 17:00")
            ):
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


# =============== 09:00 GÜNLÜK BIST100 + DÖVİZ + EMTİA + GAINERS/LOSERS + AI ÖZET ===============

def get_bist100_summary():
    data = yf.Ticker("XU100.IS").history(period="1d")
    close = data["Close"].iloc[-1]
    open_ = data["Open"].iloc[-1]
    change = (close - open_) / open_ * 100
    return close, change


def get_top_movers(limit=5):
    results = []
    for sym in BIST100_TICKERS:
        try:
            h = yf.Ticker(sym).history(period="2d")
            if len(h) < 2:
                continue
            prev = h["Close"].iloc[-2]
            last = h["Close"].iloc[-1]
            change = (last - prev) / prev * 100
            results.append((sym, last, change))
        except:
            continue

    sorted_list = sorted(results, key=lambda x: x[2], reverse=True)
    top_gainers = sorted_list[:limit]
    top_losers = sorted_list[-limit:][::-1]
    return top_gainers, top_losers


def generate_daily_ai_comment(bist_change):

    prompt = f"""
Aşağıdaki veriyle profesyonel bir Türkçe piyasa özeti oluştur.
Yatırım tavsiyesi verme.

BIST100 günlük değişim: %{bist_change:.2f}

Format:
📌 Genel görünüm (BIST100)
📊 Son değerlendirme <b>(Kriptos AI)</b>
    """

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": "Bearer " + os.getenv("OPENAI_API_KEY")},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
            }
        )
        return r.json()["choices"][0]["message"]["content"]

    except Exception as e:
        print("AI yorum hatası:", e)
        return "⚠️ AI yorumu alınamadı."


def build_daily_summary():
    bist_price, bist_change = get_bist100_summary()
    gainers, losers = get_top_movers()

    ai_text = generate_daily_ai_comment(bist_change)

    msg = (
        "📊 <b>Günlük Borsa Özeti</b>\n"
        "───────\n\n"
        f"📈 <b>BIST100:</b> {bist_price:.2f} (%{bist_change:.2f})\n\n"
        "🟢 <b>En Çok Artan 5 Hisse</b>\n"
    )

    # ==================== TOP GAINERS ====================
    for s, p, c in gainers:
        sym = s.replace(".IS", "")
        msg += f"• {sym}: {p:.2f} (%{c:.2f})\n"

        vol = get_volume_analysis(sym)
        if vol:
            msg += (
                f"   📊 Hacim: G:{format_number(vol['today'])} | "
                f"5G:{format_number(vol['avg5'])} | "
                f"Trend:%{vol['month_trend']} {vol['trend_dir']} | "
                f"Skor:{vol['flow_score']}/100\n"
            )
        else:
            msg += "   📊 Hacim: veri yok\n"

    # ==================== TOP LOSERS ====================
    msg += "\n🔴 <b>En Çok Düşen 5 Hisse</b>\n"
    for s, p, c in losers:
        sym = s.replace(".IS", "")
        msg += f"• {sym}: {p:.2f} (%{c:.2f})\n"

        vol = get_volume_analysis(sym)
        if vol:
            msg += (
                f"   📊 Hacim: G:{format_number(vol['today'])} | "
                f"5G:{format_number(vol['avg5'])} | "
                f"Trend:%{vol['month_trend']} {vol['trend_dir']} | "
                f"Skor:{vol['flow_score']}/100\n"
            )
        else:
            msg += "   📊 Hacim: veri yok\n"

    msg += (
        "\n🤖 <b>Kriptos AI Yorumu</b>\n\n"
        f"{ai_text}"
    )

    return msg

_last_daily_send = ""

def daily_report_loop():
    global _last_daily_send
    while True:
        try:
            now = now_istanbul()

            # === 09:00 Sabah Raporu ===
            if now.strftime("%H:%M") == "09:00":
                if _last_daily_send != now.strftime("%Y-%m-%d"):
                    _last_daily_send = now.strftime("%Y-%m-%d")
                    report = build_daily_summary()

                    targets = set()
                    users = load_users()
                    for uid in users:
                        targets.add(uid)

                    for uid in targets:
                        send_message(uid, report)
                        time.sleep(0.5)

            # === 18:10 Akşam Raporu ===
            if now.strftime("%H:%M") == "18:10":
                if _last_daily_send != now.strftime("%Y-%m-%d-18"):
                    _last_daily_send = now.strftime("%Y-%m-%d-18")
                    report = build_daily_summary()

                    targets = set()
                    users = load_users()
                    for uid in users:
                        targets.add(uid)

                    for uid in targets:
                        send_message(uid, report)
                        time.sleep(0.5)

        except Exception as e:
            print("Daily error:", e)

        time.sleep(20)


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

    Thread(target=send_favorite_summaries_loop, daemon=True).start()
    Thread(target=alarm_check_loop, daemon=True).start()
    Thread(target=daily_report_loop, daemon=True).start()


    last_update_id = None    
    processed = set()
    favorites = load_favorites()
    alarms = load_alarms()
    portföy = load_portfoy()

    # ----------------- GEÇERLİ HİSSE DOGRULAMA -----------------
    def is_valid_symbol(sym):
        sym = sym.upper()
        return sym.isalpha() and 2 <= len(sym) <= 5


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
            # =============== KULLANICI KAYDI (HERKES 09:00 RAPORU ALSIN) ===============
            users = load_users()
            if str(chat_id) not in users:
                users.append(str(chat_id))
                save_users(users)

            # ========================= /start =========================
            if text.lower() == "/start":
                msg = (
                    "👋 <b>Kriptos BIST100 Takip Botu'na Hoş Geldin!</b>\n\n"
                    "💬 Sadece hisse kodunu yaz: <b>ASELS/asels</b>, <b>THYAO/thyao</b>...\n"
                    "🤖 <b>Kriptos AI</b> destekli botumuz sorulan hissenin teknik-temel ve haber analizini yapar.\n\n"
                    
                    "⭐ Favori komutları:\n"
                    "<code>/favori</code> ekle ASELS\n"
                    "<code>/favori</code> sil ASELS\n"
                    "<code>/favori</code> liste\n\n"
                    "👉 Favorilenen hisselerin bilgileri her gün sabah 10:00 ve akşam 17:00'da size otomatik Kriptos AI tarafından iletilir.\n\n"
                    
                    "🔔 Alarm komutları:\n"
                    "<code>/alarm</code> ekle ASELS 190\n"
                    "<code>/alarm</code> sil ASELS 190\n"
                    "<code>/alarm</code> liste\n\n"
                    
                    "📦 Portföy komutları:\n"
                    "<code>/portföy</code> ekle ASELS 100 (LOT) 54.80 (Maliyet). Şeklinde giriniz.\n"
                    "<code>/portföy</code> göster\n"
                    "<code>/portföy</code> sil ASELS\n\n"

                    "❗❗ Unutmayın Yapay zeka ve Botlar yanılabilir. Bu bot Yatırım Tavsiyesi Vermez! Tüm sorumluluk kullanıcıya aittir!"                    
                )
                send_message(chat_id, msg)
                continue


            # ========================= FAVORİ =========================
            if text.lower().startswith("/favori"):
                parts = text.split()
                cmd = parts[1] if len(parts) > 1 else None

                if cmd == "ekle" and len(parts) >= 3:
                    sym = parts[2].upper()

                    if not is_valid_symbol(sym):
                        send_message(chat_id, "⚠️ Lütfen hisse kodunu doğru giriniz. Örnek: ASELS / asels")
                        continue

                    favs = favorites.get(str(chat_id), [])
                    if sym not in favs:
                        favs.append(sym)
                        favorites[str(chat_id)] = favs
                        save_favorites(favorites)
                        send_message(chat_id, f"✅ <b>{sym}</b> favorilere eklendi.")
                    else:
                        send_message(chat_id, f"ℹ️ <b>{sym}</b> zaten favorilerde.")
                    continue

                elif cmd == "sil" and len(parts) >= 3:
                    sym = parts[2].upper()
                    favs = favorites.get(str(chat_id), [])

                    if sym in favs:
                        favs.remove(sym)
                        favorites[str(chat_id)] = favs
                        save_favorites(favorites)
                        send_message(chat_id, f"🗑️ <b>{sym}</b> favorilerden silindi.")
                    else:
                        send_message(chat_id, f"⚠️ <b>{sym}</b> favorilerde bulunamadı.")
                    continue

                elif cmd in ["liste", "goster"]:
                    favs = favorites.get(str(chat_id), [])
                    if not favs:
                        send_message(chat_id, "⭐ Favorin yok. Örnek:\n<code>/favori</code> ekle ASELS")
                    else:
                        fav_text = "\n".join([f"• {s}" for s in favs])
                        send_message(chat_id, f"⭐ <b>Favoriler:</b>\n{fav_text}")
                    continue

                else:
                    send_message(chat_id,
                        "⚙️ Kullanım:\n"
                        "<code>/favori</code> ekle ASELS\n"
                        "<code>/favori</code> sil ASELS\n"
                        "<code>/favori</code> liste"
                    )
                    continue


            # ========================= ALARM =========================
            if text.lower().startswith("/alarm"):
                parts = text.split()
                cmd = parts[1] if len(parts) > 1 else None

                if cmd == "ekle" and len(parts) >= 4:
                    sym = parts[2].upper()

                    if not is_valid_symbol(sym):
                        send_message(chat_id, "⚠️ Lütfen hisse kodunu doğru giriniz. Örnek: ASELS / asels")
                        continue

                    try:
                        target = float(parts[3].replace(",", "."))
                    except:
                        send_message(chat_id, "⚠️ Hedef fiyat sayı olmalı.")
                        continue

                    info = get_price(sym)
                    if not info:
                        send_message(chat_id, f"⚠️ {sym} fiyat bulunamadı.")
                        continue

                    current = float(info["fiyat"])
                    direction = "up" if target > current else "down"
                    dir_text = "üzeri" if direction == "up" else "altı"

                    uid_key = str(chat_id)
                    user_alarms = alarms.get(uid_key, [])

                    exists = any(a["symbol"] == sym and float(a["target"]) == target for a in user_alarms)
                    if exists:
                        send_message(chat_id, f"ℹ️ Bu alarm zaten kayıtlı.")
                        continue

                    user_alarms.append({"symbol": sym, "target": target, "direction": direction})
                    alarms[uid_key] = user_alarms
                    save_alarms(alarms)

                    send_message(chat_id, f"🔔 <b>{sym}</b> için {target} TL ({dir_text}) alarmı kaydedildi.")
                    continue


                elif cmd in ["liste", "goster"]:
                    uid_key = str(chat_id)
                    user_alarms = alarms.get(uid_key, [])

                    if not user_alarms:
                        send_message(chat_id, "🔔 Aktif alarm yok.")
                    else:
                        lines = ["🔔 <b>Alarmların:</b>"]
                        for a in user_alarms:
                            sym = a["symbol"]
                            t = a["target"]
                            d = "üzeri" if a["direction"] == "up" else "altı"
                            lines.append(f"• {sym} — {t} TL ({d})")
                        send_message(chat_id, "\n".join(lines))
                    continue


                elif cmd == "sil" and len(parts) >= 4:
                    sym = parts[2].upper()
                    target = float(parts[3].replace(",", "."))
                    uid_key = str(chat_id)

                    user_alarms = alarms.get(uid_key, [])
                    new_list = [a for a in user_alarms if not (a["symbol"] == sym and float(a["target"]) == target)]

                    if len(new_list) == len(user_alarms):
                        send_message(chat_id, f"⚠️ Alarm bulunamadı.")
                    else:
                        alarms[uid_key] = new_list
                        save_alarms(alarms)
                        send_message(chat_id, "🗑️ Alarm silindi.")
                    continue


                else:
                    send_message(chat_id,
                        "🔔 Kullanım:\n"
                        "<code>/alarm</code> ekle ASELS 190\n"
                        "<code>/alarm</code> sil ASELS 190\n"
                        "<code>/alarm</code> liste"
                    )
                    continue


            # ========================= PORTFÖY =========================
            low = text.lower()
            if low.startswith("/portfoy") or low.startswith("/portföy"):

                clean = text.replace("PORTFOY","portföy").replace("portfoy","portföy")
                parts = clean.split()
                cmd = parts[1] if len(parts) > 1 else None
                uid_key = str(chat_id)

                # -------- EKLE --------
                if cmd == "ekle" and len(parts) >= 5:
                    sym = parts[2].upper()

                    if not is_valid_symbol(sym):
                        send_message(chat_id, "⚠️ Lütfen hisse kodunu doğru giriniz. Örnek: ASELS / asels")
                        continue

                    try:
                        adet = float(parts[3].replace(",", "."))
                        maliyet = float(parts[4].replace(",", "."))
                    except:
                        send_message(chat_id, "⚠️ Kullanım: <code>/portföy</code> ekle ASELS 100 54.8")
                        continue

                    if adet <= 0 or maliyet <= 0:
                        send_message(chat_id, "⚠️ Adet ve maliyet pozitif olmalı.")
                        continue

                    user_p = portföy.get(uid_key, {})
                    pos = user_p.get(sym, {"adet": 0, "maliyet": 0})

                    yeni_adet = pos["adet"] + adet
                    toplam = pos["adet"] * pos["maliyet"] + adet * maliyet
                    yeni_maliyet = toplam / yeni_adet

                    user_p[sym] = {"adet": yeni_adet, "maliyet": yeni_maliyet}
                    portföy[uid_key] = user_p
                    save_portfoy(portföy)

                    send_message(chat_id, f"📦 <b>{sym}</b> güncellendi.\nLot: <b>{yeni_adet:.0f}</b>\nMaliyet: <b>{yeni_maliyet:.2f} TL</b>")
                    continue

                # -------- LİSTE / GÖSTER --------
                elif cmd in ["liste", "goster", "göster"]:
                    user_p = portföy.get(uid_key, {})

                    if not user_p:
                        send_message(
                            chat_id,
                            "📦 Portföy boş. Örnek:\n<code>/portföy</code> ekle ASELS 100 54.8"
                        )
                        continue

                    lines = ["📦 <b>Portföyün:</b>\n"]

                    genel_maliyet = 0
                    genel_deger = 0
                    kz_list = []

                    for sym, pos in user_p.items():
                        adet = pos["adet"]
                        maliyet = pos["maliyet"]
                        toplam = adet * maliyet

                        info = get_price(sym)
                        fiyat = info["fiyat"] if info else None

                        if fiyat:
                            anlik = fiyat * adet
                            kz = anlik - toplam
                            genel_maliyet += toplam
                            genel_deger += anlik
                            kz_list.append((sym, kz))

                            yuzde = (kz / toplam) * 100 if toplam > 0 else 0
                            kz_emoji = "🟢" if kz >= 0 else "🔴"

                            lines.append(
                                f"📌 <b>{sym}</b>\n"
                                f"   • Lot: <b>{adet:.0f}</b>\n"
                                f"   • Maliyet: <b>{maliyet:.2f} TL</b>\n"
                                f"   • Anlık: <b>{format_price(fiyat)} TL</b>\n"
                                f"   • Değer: <b>{format_price(anlik)} TL</b>\n"
                                f"   • {kz_emoji} K/Z: <b>{kz:.2f} TL (%{yuzde:.2f})</b>\n"
                            )

                            vol = get_volume_analysis(sym)
                            if vol:
                                lines.append(
                                    f"   📊 Hacim: G:{format_number(vol['today'])} | "
                                    f"3G:{format_number(vol['avg3'])} | "
                                    f"5G:{format_number(vol['avg5'])} | "
                                    f"Trend:%{vol['month_trend']} {vol['trend_dir']} | "
                                    f"Skor:{vol['flow_score']}/100\n"
                                )
                            else:
                                lines.append("   📊 Hacim: veri yok\n")

                        else:
                            lines.append(f"📌 <b>{sym}</b> — ❌ Fiyat alınamadı\n")

                    # ========= GENEL TOPLAM =========
                    genel_kz = genel_deger - genel_maliyet
                    genel_yuzde = (genel_kz / genel_maliyet * 100) if genel_maliyet > 0 else 0
                    gemoji = "🟢" if genel_kz >= 0 else "🔴"

                    lines.append("——————————————")
                    lines.append(f"💰 Toplam Maliyet: {format_price(genel_maliyet)} TL")
                    lines.append(f"📊 Portföy Değeri: {format_price(genel_deger)} TL")
                    lines.append(f"{gemoji} Genel K/Z: {genel_kz:.2f} TL (%{genel_yuzde:.2f})")

                    # ---------------- AI PORTFÖY YORUMU ----------------
                    ai_prompt = (
                        "Aşağıdaki verileri kullanarak Borsa İstanbul portföyü için çok kısa, net ve "
                        "yalnızca analitik bir değerlendirme yap. Profesyonel bir ton kullan, "
                        "Metin 8-10 kısa cümleden oluşsun, sade ve anlaşılır olsun.\n\n"
                        f"Toplam maliyet: {genel_maliyet:.2f} TL\n"
                        f"Güncel değer: {genel_deger:.2f} TL\n"
                        f"Kar/Zarar: {genel_kz:.2f} TL (%{genel_yuzde:.2f})\n\n"
                        "Yorum formatı:\n"
                        "📌 Genel Durum\n"
                        "⚠️ Risk Görünümü\n"
                        "💠 Portföy Yapısı\n"
                        "📝 Sonuç"
                    )

                    try:
                        r = requests.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers={"Authorization": "Bearer " + os.getenv("OPENAI_API_KEY")},
                            json={
                                "model": "gpt-4o-mini",
                                "messages": [{"role": "user", "content": ai_prompt}],
                                "max_tokens": 600,
                            }
                        )
                        ai_comment = r.json()["choices"][0]["message"]["content"]
                    except:
                        ai_comment = "⚠️ AI portföy yorumu oluşturulamadı."

                    lines.append("\n🤖 <b>Kriptos AI Portföy Yorumu</b>\n" + ai_comment)

                    # ---------------- PNG — PROFESYONEL ----------------
                    try:
                        names = [x[0] for x in kz_list]
                        values = [x[1] for x in kz_list]

                        if names:
                            plt.figure(figsize=(10, 5), dpi=160)
                            ax = plt.gca()

                            ax.set_facecolor("white")
                            ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)

                            colors = ["#27ae60" if v >= 0 else "#c0392b" for v in values]

                            bars = plt.bar(names, values, color=colors, edgecolor="#333", linewidth=0.8)

                            today = datetime.now().strftime("%d.%m.%Y")
                            plt.title(f"Hisse Bazlı Kar/Zarar — {today}", fontsize=14, fontweight="bold")

                            plt.ylabel("TL")

                            for bar, val in zip(bars, values):
                                plt.text(
                                    bar.get_x() + bar.get_width()/2,
                                    bar.get_height(),
                                    f"{val:.0f}",
                                    ha="center",
                                    va="bottom",
                                    fontsize=9,
                                    fontweight="bold"
                                )

                            plt.tight_layout()

                            graph_path = f"data/portfoy_graph_{uid_key}.png"
                            plt.savefig(graph_path, bbox_inches="tight")
                            plt.close()

                            with open(graph_path, "rb") as img:
                                requests.post(URL + "sendPhoto", data={"chat_id": chat_id}, files={"photo": img})
                    except Exception as e:
                        print("Grafik hatası:", e)

                    send_message(chat_id, "\n".join(lines))
                    continue

                # -------- SİL --------
                elif cmd == "sil" and len(parts) >= 3:
                    sym = parts[2].upper()
                    user_p = portföy.get(uid_key, {})

                    if sym in user_p:
                        del user_p[sym]
                        portföy[uid_key] = user_p
                        save_portfoy(portföy)
                        send_message(chat_id, f"🗑️ {sym} silindi.")
                    else:
                        send_message(chat_id, f"⚠️ Portföyde {sym} yok.")
                    continue

                # -------- HATALI KULLANIM --------
                else:
                    send_message(
                        chat_id,
                        "📦 Kullanım:\n"
                        "<code>/portföy</code> ekle ASELS 100(LOT Adedi) 54.8(Maliyet)\n"
                        "<code>/portföy</code> sil ASELS\n"
                        "<code>/portföy</code> göster"
                    )
                    continue


            # ========================= HİSSE SORGUSU =========================
            symbol = text.split()[0].lstrip("/").upper()

            if not is_valid_symbol(symbol):
                send_message(chat_id, "⚠️ Lütfen hisse kodunu doğru giriniz. Örnek: ASELS / asels")
                continue

            reply = build_message(symbol)
            send_message(chat_id, reply)
            time.sleep(0.8)


# =============== FLASK (Render Portu) ===============
from flask import Flask, request

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot aktif, Render portu açık!", 200


# ======== BROADCAST ROUTE (Tüm kullanıcılara mesaj) ========
@app.route("/broadcast")
def broadcast_route():
    key = request.args.get("key")
    
    # Güvenlik: ADMIN_KEY ile doğrulama
    if key != os.getenv("ADMIN_KEY"):
        return "❌ Yetkisiz erişim", 403

    msg = request.args.get("msg", "🚀 Kriptos AI güncellendi! Yeni özellikler aktif!")

    try:
        users = load_users()
        if not users:
            return "Kayıtlı kullanıcı yok!", 200

        for uid in users:
            send_message(uid, msg)
            time.sleep(0.3)

        return "✔️ BROADCAST gönderildi", 200

    except Exception as e:
        return f"HATA: {e}", 500


def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


Thread(target=run).start()

if __name__ == "__main__":
    main()
