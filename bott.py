# bott.py (tam hazır sürüm)
import time
import random
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask
from threading import Thread
import os

# === AYARLAR ===
BOT_TOKEN = "8116276773:AAHoSQAthKmijTE62bkqtGQNACf0zi0JuCs"
URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# === TELEGRAM ===
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

# === SAYI BİÇİMLENDİRME ===
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

# === YAHOO FİNANCE VERİSİ ===
def get_price(symbol):
    try:
        time.sleep(random.uniform(0.5, 1.2))
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

# === BASİT RSI (yfinance fallback) ===
def get_rsi_fallback(symbol: str, period: int = 14, lookback_months: int = 3):
    """yfinance kullanarak RSI hesaplar — her zaman sonuç döner."""
    import numpy as np
    import pandas as pd
    sym = symbol.upper() + ".IS"

    try:
        df = yf.download(sym, period=f"{lookback_months}mo", interval="1d", progress=False)
        if df is None or df.empty or "Close" not in df.columns:
            return "📊 RSI: veri alınamadı (yfinance)."

        close = df["Close"].dropna()
        if len(close) < period + 1:
            return "📊 RSI: veri yetersiz."

        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()

        # Son değerleri güvenli çek
        last_gain = avg_gain.iloc[-1]
        last_loss = avg_loss.iloc[-1]

        # Eğer bunlar bir Series veya NaN ise güvenli şekilde sıfırla
        try:
            last_gain = float(last_gain) if np.isfinite(last_gain) else 0.0
        except:
            last_gain = 0.0
        try:
            last_loss = float(last_loss) if np.isfinite(last_loss) and last_loss != 0 else 1e-9
        except:
            last_loss = 1e-9

        rs = last_gain / (last_loss if last_loss != 0 else 1e-9)
        rsi = 100 - (100 / (1 + rs))
        rsi = round(float(rsi), 2)

        # Yorum
        if rsi >= 70:
            rec = "Sat"
        elif rsi <= 30:
            rec = "Al"
        else:
            rec = "Nötr"

        return f"📊 RSI: {rsi} ({rec})"

    except Exception as e:
        print("RSI fallback error:", e, flush=True)
        return "📊 RSI: hesaplanamadı."


# === TRADINGVIEW (RapidAPI) + fallback to RSI ===
def get_tradingview_analysis(symbol):
    # İlk adım: RapidAPI TradingView (eğer ayarlıysa)
    url = "https://tradingview-real-time.p.rapidapi.com/technicalSummary"
    query = {"symbol": f"{symbol}:BIST"}
    headers = {
        "x-rapidapi-key": "1749e090ffmsh612a371009ddbcap1c2f2cjsnaa23aba94831",
        "x-rapidapi-host": "tradingview-real-time.p.rapidapi.com"
    }

    try:
        print(f"📡 TradingView isteği -> {symbol}:BIST", flush=True)
        r = requests.get(url, headers=headers, params=query, timeout=8)
        print("TradingView raw response (prefix):", r.text[:1000], flush=True)  # logu çok uzatma
        data = r.json()
        summary = data.get("data", {}).get("technical_summary")
        if summary:
            return f"📊 TradingView: {summary}"
        alt = data.get("summary") or data.get("signal") or data.get("recommendation")
        if alt:
            return f"📊 TradingView: {alt}"
        print("TradingView: teknik alan yok, fallback RSI.", flush=True)
    except Exception as e:
        print("TradingView API error:", e, flush=True)

    # Fallback: yfinance ile RSI
    return get_rsi_fallback(symbol)

# === HABERLER (GOOGLE RSS) ===
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
            pub = item.find("pubDate").text[:16] if item.find("pubDate") is not None else ""
            haberler.append(f"🔹 <a href='{link}'>{title}</a> ({pub})")
        return "\n".join(haberler)
    except Exception as e:
        print("News error:", e, flush=True)
        return "📰 Haberler alınamadı."

# === MESAJ OLUŞTUR ===
def build_message(symbol):
    symbol = symbol.strip().upper()
    info = get_price(symbol)
    news = get_news(symbol)
    analysis = get_tradingview_analysis(symbol)

    if not info:
        return f"⚠️ {symbol} için veri alınamadı veya desteklenmiyor."

    lines = [f"📈 <b>{symbol}</b> Hisse Özeti (BIST)"]

    if info.get("fiyat") is not None:
        lines.append(f"💰 Fiyat: {info['fiyat']} TL")
    if info.get("degisim") and info["degisim"] != "0.00%":
        lines.append(f"📉 Değişim: {info['degisim']}")
    if info.get("acilis") is not None or info.get("kapanis") is not None:
        satir = []
        if info.get("acilis") is not None:
            satir.append(f"Açılış: {info['acilis']}")
        if info.get("kapanis") is not None:
            satir.append(f"Kapanış: {info['kapanis']}")
        lines.append("📊 " + " | ".join(satir))
    if info.get("tavan") is not None or info.get("taban") is not None:
        satir = []
        if info.get("tavan") is not None:
            satir.append(f"🔼 Tavan: {info['tavan']}")
        if info.get("taban") is not None:
            satir.append(f"🔽 Taban: {info['taban']}")
        lines.append(" | ".join(satir))
    if info.get("hacim"):
        lines.append(f"💸 Hacim: {info['hacim']}")
    if info.get("piyasa"):
        lines.append(f"🏢 Piyasa Değeri: {info['piyasa']}")
    if info.get("fk") or info.get("pddd"):
        detay = []
        if info.get("fk"):
            detay.append(f"📗 F/K: {info['fk']}")
        if info.get("pddd"):
            detay.append(f"📘 PD/DD: {info['pddd']}")
        if detay:
            lines.append(" | ".join(detay))

    # Teknik analiz (TradingView veya RSI fallback)
    lines.append("\n" + analysis)
    # Haberler
    lines.append("\n" + news)
    # Kaynak
    lines.append(f"\n📎 <a href='{info['url']}'>Kaynak: Yahoo Finance</a>")
    return "\n".join(lines)

# === ANA DÖNGÜ (duplicate engelleme, offset doğru kullanımı) ===
def main():
    print("🚀 Borsa İstanbul Botu çalışıyor...", flush=True)
    last_update_id = None
    processed_updates = set()
    while True:
        updates = get_updates(last_update_id)
        if not updates:
            time.sleep(1)
            continue

        results = updates.get("result", [])
        # sıralı işleme
        results.sort(key=lambda x: x.get("update_id", 0))
        for item in results:
            uid = item.get("update_id")
            if uid in processed_updates:
                continue
            processed_updates.add(uid)
            last_update_id = uid + 1

            message = item.get("message", {}) or {}
            chat_id = message.get("chat", {}).get("id")
            text = (message.get("text") or "").strip()
            if not text:
                continue

            print(f"Gelen istek: {text}", flush=True)
            # sadece komut/sembol kısmını al (örn: "SASA" veya "/sasa" vs.)
            symbol = text.split()[0].lstrip("/")
            reply = build_message(symbol)
            send_message(chat_id, reply)
            time.sleep(1.0)  # Telegram rate kontrolü

        time.sleep(0.5)

# === KEEP ALIVE (Flask) ===
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot aktif, Render portu açık!", 200

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# Başlat
Thread(target=run).start()

if __name__ == "__main__":
    main()
