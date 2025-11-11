# === BISTBOT ===
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
    params = {"timeout": 100, "offset": offset}
    return requests.get(URL + "getUpdates", params=params).json()

def send_message(chat_id, text):
    requests.post(
        URL + "sendMessage",
        params={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )

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
        time.sleep(random.uniform(3.0, 6.0))
        ticker = yf.Ticker(symbol.upper() + ".IS")
        data = ticker.history(period="1d")
        if data.empty:
            return None

        fiyat = data["Close"].iloc[-1]
        acilis = data["Open"].iloc[-1]
        tavan = data["High"].iloc[-1]
        taban = data["Low"].iloc[-1]
        hacim = data["Volume"].iloc[-1]

        return {
            "url": f"https://finance.yahoo.com/quote/{symbol}.IS",
            "fiyat": round(fiyat, 2),
            "degisim": None,
            "acilis": round(acilis, 2),
            "kapanis": round(fiyat, 2),
            "tavan": round(tavan, 2),
            "taban": round(taban, 2),
            "hacim": format_number(hacim),
            "fk": None,
            "pddd": None,
            "piyasa": None,
        }
    except Exception as e:
        print("Price error:", e)
        return None

# === TEKNİK ANALİZ ===
def get_technical_analysis(symbol):
    """Anlık RSI, MACD ve Hareketli Ortalama (5 dakikalık veriden)."""
    try:
        # 5 dakikalık veriler, 1 günlük aralıkta
        data = yf.download(symbol + ".IS", period="1d", interval="5m", progress=False)
        if data.empty:
            return "📊 Teknik veri alınamadı."

        close = data["Close"]

        # RSI Hesapla (14 periyotluk)
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        last_rsi = round(rsi.iloc[-1], 2)

        # MACD Hesapla (EMA 12-26)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        macd_signal = "Al" if macd.iloc[-1] > signal.iloc[-1] else "Sat"

        # Hareketli Ortalamalar (5m veriden)
        ma20 = round(close.rolling(20).mean().iloc[-1], 2)
        ma50 = round(close.rolling(50).mean().iloc[-1], 2)

        return f"📊 RSI: {last_rsi} | MACD: {macd_signal} | MA20: {ma20} | MA50: {ma50}"

    except Exception as e:
        print("Technical error:", e)
        return "📊 Teknik analiz hesaplanamadı."


# === HABERLER ===
def get_news(symbol):
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+Borsa+İstanbul+OR+hisse&hl=tr&gl=TR&ceid=TR:tr"
        r = requests.get(url, timeout=10)
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
            pub = item.find("pubDate").text[:16]
            haberler.append(f"🔹 <a href='{link}'>{title}</a> ({pub})")

        return "\n".join(haberler)
    except Exception as e:
        print("News error:", e)
        return "📰 Haberler alınamadı."

# === MESAJ OLUŞTUR ===
def build_message(symbol):
    info = get_price(symbol)
    news = get_news(symbol)

    if not info:
        return f"⚠️ {symbol} için veri alınamadı veya desteklenmiyor."

    lines = [f"📈 <b>{symbol}</b> Hisse Özeti (BIST100)"]

    if info.get("fiyat"):
        lines.append(f"💰 Fiyat: {info['fiyat']} TL")

    if info.get("degisim") and info["degisim"] != "0.00%":
        lines.append(f"📉 Değişim: {info['degisim']}")

    fiyat_bilgileri = []
    if info.get("acilis"):
        fiyat_bilgileri.append(f"Açılış: {info['acilis']}")
    if info.get("kapanis"):
        fiyat_bilgileri.append(f"Kapanış: {info['kapanis']}")
    if fiyat_bilgileri:
        lines.append("📊 " + " | ".join(fiyat_bilgileri))

    if info.get("tavan") or info.get("taban"):
        satir = []
        if info.get("tavan"):
            satir.append(f"🔼 Tavan: {info['tavan']}")
        if info.get("taban"):
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
        lines.append(" | ".join(detay))

    # === 📊 TEKNİK ANALİZ ===
    tech = get_technical_analysis(symbol)
    lines.append("\n" + tech)

    # === 📰 HABERLER ===
    lines.append("\n" + news)

    # === 🔗 KAYNAK ===
    lines.append(f"\n📎 <a href='{info['url']}'>Kaynak: Yahoo Finance</a>")

    return "\n".join(lines)

# === ANA DÖNGÜ ===
def main():
    print("🚀 Borsa İstanbul Botu çalışıyor...")
    last_update_id = None
    while True:
        updates = get_updates(last_update_id)
        if "result" in updates and updates["result"]:
            for item in updates["result"]:
                last_update_id = item["update_id"] + 1
                message = item.get("message", {})
                chat_id = message.get("chat", {}).get("id")
                text = message.get("text", "").strip().upper()

                if text:
                    print(f"Gelen istek: {text}")
                    reply = build_message(text)
                    send_message(chat_id, reply)
                time.sleep(2)

# === KEEP ALIVE ===
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
