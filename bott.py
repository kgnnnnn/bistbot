# bott.py
import os
import time
import random
import requests
import yfinance as yf
from flask import Flask
from threading import Thread

# =========================
# AYARLAR
# =========================
BOT_TOKEN = "8116276773:AAHoSQAthKmijTE62bkqtGQNACf0zi0JuCs"
URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# RapidAPI anahtarı (ENV > sabit)
RAPID_KEY = os.environ.get(
    "RAPIDAPI_KEY",
    "1749e090ffmsh612a371009ddbcap1c2f2cjsnaa23aba94831"
)
RAPID_HOST = "tradingview-real-time.p.rapidapi.com"

# =========================
# TELEGRAM
# =========================
def get_updates(offset=None):
    try:
        params = {"timeout": 100, "offset": offset}
        r = requests.get(URL + "getUpdates", params=params, timeout=120)
        return r.json()
    except Exception as e:
        print("get_updates error:", e, flush=True)
        return {}

def send_message(chat_id, text):
    try:
        r = requests.post(
            URL + "sendMessage",
            params={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if r.status_code != 200:
            print("SendMessage non-200:", r.status_code, r.text, flush=True)
    except Exception as e:
        print("Send error:", e, flush=True)

# =========================
# FİYAT (Yahoo Finance)
# =========================
def format_number(num):
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

def get_price(symbol):
    """Anlık fiyatı Yahoo Finance'tan çeker."""
    try:
        time.sleep(random.uniform(0.4, 1.0))
        ticker = yf.Ticker(symbol.upper() + ".IS")
        info = ticker.info
        if not info or "currentPrice" not in info:
            return None

        return {
            "url": f"https://finance.yahoo.com/quote/{symbol}.IS",
            "fiyat": info.get("currentPrice"),
            "degisim": f"{info.get('regularMarketChangePercent', 0):.2f}%",
            "acilis": info.get("open"),
            "kapanis": info.get("previousClose"),
            "tavan": info.get("dayHigh"),
            "taban": info.get("dayLow"),
            "hacim": format_number(info.get("volume")),
            "fk": info.get("trailingPE"),
            "pddd": info.get("priceToBook"),
            "piyasa": format_number(info.get("marketCap")),
        }
    except Exception as e:
        print("Price error:", e, flush=True)
        return None

# =========================
# TEKNİK (TradingView Real-Time via RapidAPI)
# Endpoint: GET /technicals/summary?query=<SYMBOL>
# =========================
def get_tradingview_analysis(symbol: str) -> str:
    try:
        params = {"query": symbol.upper()}
        headers = {
            "x-rapidapi-key": RAPID_KEY,
            "x-rapidapi-host": RAPID_HOST,
        }
        print(f"📡 TV /technicals/summary -> {params}", flush=True)
        r = requests.get(
            f"https://{RAPID_HOST}/technicals/summary",
            params=params,
            headers=headers,
            timeout=8,
        )
        raw = r.text
        print("TV raw (prefix):", raw[:600], flush=True)

        # Beklenen yanıt esnek: bazen data list/dict olabilir.
        data = r.json()

        entry = None
        if isinstance(data, dict):
            # Örn: {"data":[{...}]} veya {"data":{"symbols":[{...}]}}
            d = data.get("data")
            if isinstance(d, list) and d:
                entry = d[0]
            elif isinstance(d, dict):
                syms = d.get("symbols")
                if isinstance(syms, list) and syms:
                    entry = syms[0]
            # Bazı varyantlarda doğrudan alanlar üst düzeyde olabilir
            if entry is None and any(k in data for k in ("RSI", "MACD.macd", "Recommend.All")):
                entry = data

        if not isinstance(entry, dict):
            return "📊 Teknik analiz bulunamadı (TradingView)."

        rsi = entry.get("RSI")
        macd = entry.get("MACD.macd")
        macd_signal = entry.get("MACD.signal")
        rec = entry.get("Recommend.All") or entry.get("Recommend.All".lower()) or entry.get("recommendation")

        # RSI metni
        if isinstance(rsi, (int, float)):
            if rsi > 70:
                rsi_txt = f"RSI: {rsi:.2f} (Aşırı Alım)"
            elif rsi < 30:
                rsi_txt = f"RSI: {rsi:.2f} (Aşırı Satım)"
            else:
                rsi_txt = f"RSI: {rsi:.2f} (Nötr)"
        else:
            rsi_txt = "RSI: —"

        # MACD yönü
        if isinstance(macd, (int, float)) and isinstance(macd_signal, (int, float)):
            macd_dir = "Al" if macd > macd_signal else "Sat"
            macd_txt = f"MACD: {macd_dir}"
        else:
            macd_txt = "MACD: —"

        rec_txt = f"Öneri: {rec}" if rec else "Öneri: —"
        return f"📊 {rsi_txt} | {macd_txt} | {rec_txt}"

    except Exception as e:
        print("TradingView API error:", e, flush=True)
        return "📊 Teknik analiz alınamadı (TradingView)."

# =========================
# HABERLER (Google RSS)
# =========================
def get_news(symbol):
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+Borsa+İstanbul+OR+hisse&hl=tr&gl=TR&ceid=TR:tr"
        r = requests.get(url, timeout=8)
        if r.status_code != 200:
            return "📰 Haberler alınamadı."
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.text)
        items = root.findall(".//item")[:3]
        if not items:
            return "📰 Yeni haber bulunamadı."
        haberler = ["🗞️ <b>Son Haberler</b>"]
        for item in items:
            title = item.find("title").text
            link = item.find("link").text
            pub_el = item.find("pubDate")
            pub = pub_el.text[:16] if pub_el is not None and pub_el.text else ""
            haberler.append(f"🔹 <a href='{link}'>{title}</a> ({pub})")
        return "\n".join(haberler)
    except Exception as e:
        print("News error:", e, flush=True)
        return "📰 Haberler alınamadı."

# =========================
# MESAJ OLUŞTUR
# =========================
def build_message(symbol):
    symbol = symbol.strip().upper()
    info = get_price(symbol)
    if not info:
        return f"⚠️ {symbol} için veri alınamadı veya desteklenmiyor."

    lines = [f"📈 <b>{symbol}</b> Hisse Özeti (BIST)"]

    if info.get("fiyat") is not None:
        lines.append(f"💰 Fiyat: {info['fiyat']} TL")
    if info.get("degisim") and info["degisim"] != "0.00%":
        lines.append(f"📉 Değişim: {info['degisim']}")

    satir = []
    if info.get("acilis") is not None:
        satir.append(f"Açılış: {info['acilis']}")
    if info.get("kapanis") is not None:
        satir.append(f"Kapanış: {info['kapanis']}")
    if satir:
        lines.append("📊 " + " | ".join(satir))

    hi_lo = []
    if info.get("tavan") is not None:
        hi_lo.append(f"🔼 Tavan: {info['tavan']}")
    if info.get("taban") is not None:
        hi_lo.append(f"🔽 Taban: {info['taban']}")
    if hi_lo:
        lines.append(" | ".join(hi_lo))

    if info.get("hacim"):
        lines.append(f"💸 Hacim: {info['hacim']}")
    if info.get("piyasa"):
        lines.append(f"🏢 Piyasa Değeri: {info['piyasa']}")
    if info.get("fk") or info.get("pddd"):
        det = []
        if info.get("fk"):
            det.append(f"📗 F/K: {info['fk']}")
        if info.get("pddd"):
            det.append(f"📘 PD/DD: {info['pddd']}")
        if det:
            lines.append(" | ".join(det))

    # Teknik analiz (TradingView)
    tech = get_tradingview_analysis(symbol)
    lines.append("\n" + tech)

    # Haberler
    news = get_news(symbol)
    lines.append("\n" + news)

    # Kaynak
    lines.append(f"\n📎 <a href='{info['url']}'>Kaynak: Yahoo Finance</a>")

    return "\n".join(lines)

# =========================
# ANA DÖNGÜ — ÇİFT MESAJ ENGELLEME
# =========================
def main():
    print("🚀 Borsa İstanbul Botu çalışıyor...", flush=True)
    last_update_id = None
    processed = set()

    while True:
        data = get_updates(last_update_id)
        results = data.get("result", [])
        if not results:
            time.sleep(0.5)
            continue

        # Günceli öncele, sırala
        results.sort(key=lambda x: x.get("update_id", 0))

        max_uid = last_update_id or 0
        for item in results:
            uid = item.get("update_id")
            if uid in processed:
                continue

            processed.add(uid)
            if uid and uid > max_uid:
                max_uid = uid

            msg = item.get("message") or {}
            chat_id = (msg.get("chat") or {}).get("id")
            text = (msg.get("text") or "").strip()
            if not chat_id or not text:
                continue

            symbol = text.split()[0].lstrip("/").upper()
            print(f"Gelen istek: {symbol}", flush=True)

            try:
                reply = build_message(symbol)
                send_message(chat_id, reply)
            except Exception as e:
                print("build/send error:", e, flush=True)

            # Telegram rate
            time.sleep(0.8)

        # offset’i ileri al — aynı batch tekrar gelmesin
        if max_uid:
            last_update_id = max_uid + 1

        # processed kümesini şişirmemek için ara sıra temizleyebilirsin
        if len(processed) > 2000:
            processed = set(list(processed)[-1000:])

        time.sleep(0.3)

# =========================
# KEEP ALIVE (Flask)
# =========================
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot aktif, Render portu açık!", 200

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

Thread(target=run).start()

if __name__ == "__main__":
    main()
