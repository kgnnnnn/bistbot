# bistbot
import time
import random
import datetime as dt
import requests
import yfinance as yf

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
    """Büyük sayıları 1.234.567 biçiminde döndürür."""
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
    """Yalnızca Yahoo Finance'tan güvenilir veri çeker"""
    try:
        time.sleep(random.uniform(1.0, 2.0))
        ticker = yf.Ticker(symbol.upper() + ".IS")
        info = ticker.info

        if not info or "currentPrice" not in info:
            return None

        fiyat = info.get("currentPrice")
        degisim = info.get("regularMarketChangePercent")
        acilis = info.get("open")
        kapanis = info.get("previousClose")
        tavan = info.get("dayHigh")
        taban = info.get("dayLow")
        hacim = info.get("volume")
        fk = info.get("trailingPE")
        pddd = info.get("priceToBook")
        piyasa = info.get("marketCap")

        return {
            "url": f"https://finance.yahoo.com/quote/{symbol}.IS",
            "fiyat": fiyat,
            "degisim": f"{degisim:.2f}%" if degisim is not None else None,
            "acilis": acilis,
            "kapanis": kapanis,
            "tavan": tavan,
            "taban": taban,
            "hacim": format_number(hacim),
            "fk": fk,
            "pddd": pddd,
            "piyasa": format_number(piyasa),
        }

    except Exception as e:
        print("Price error:", e)
        return None

# === TRADINGVIEW TEKNİK ANALİZ (RSI, MACD, ÖNERİ) ===
from tradingview_ta import TA_Handler, Interval

def get_tradingview_analysis(symbol: str) -> str:
    """
    TradingView'den anlık teknik analiz: RSI, MACD yönü ve genel öneri.
    Hata olsa bile kullanıcıya düzgün bir satır döner (mesaj kırılmaz).
    """
    try:
        sym = symbol.upper()
        handler = TA_Handler(
            symbol=f"{sym}.IS",     # örn: ASELS.IS
            screener="turkey",      # BIST için doğru screener
            exchange="BIST",        # Borsa İstanbul
            interval=Interval.INTERVAL_5_MINUTES  # daha "anlık" analiz
        )
        analysis = handler.get_analysis()
        summary = analysis.summary  # {"RECOMMENDATION": "BUY" | "SELL" | "NEUTRAL" | "STRONG_BUY"...}

        # bazı göstergeler dictionary'de olmayabilir; güvenle al
        indicators = analysis.indicators or {}
        rsi = indicators.get("RSI")
        macd = indicators.get("MACD.macd")
        macd_signal = indicators.get("MACD.signal")

        # RSI metni
        rsi_txt = f"{round(rsi,2)}" if isinstance(rsi, (int, float)) else "—"
        # MACD yönü
        if isinstance(macd, (int, float)) and isinstance(macd_signal, (int, float)):
            macd_dir = "Al" if macd > macd_signal else "Sat"
        else:
            macd_dir = "—"

        rec = summary.get("RECOMMENDATION", "—")
        return f"📊 RSI: {rsi_txt} | MACD: {macd_dir} | Öneri: {rec}"
    except Exception as e:
        print("TradingView error:", e)
        return "📊 Teknik analiz alınamadı."

# === HABERLER (OPSİYONEL: Google News RSS) ===
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
        if detay:
            lines.append(" | ".join(detay))

    # === TRADINGVIEW TEKNİK ANALİZİ ===
    tech = get_tradingview_analysis(symbol)
    lines.append("\n" + tech)

    # === HABERLER ===
    lines.append("\n" + news)

    # === KAYNAK ===
    lines.append(f"\n📎 <a href='{info['url']}'>Kaynak: Yahoo Finance</a>")

    return "\n".join(lines)

# === ANA DÖNGÜ ===
def main():
    print("🚀 Borsa İstanbul Botu (PytonAnywhere Sürümü) çalışıyor...")
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
from flask import Flask
from threading import Thread
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot aktif, Render portu açık!", 200

def run():
    # Render bazen farklı port verir, bunu otomatik algılayalım
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run).start()

if __name__ == "__main__":
    main()

