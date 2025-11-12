import time
import random
import os
import re
import requests
import yfinance as yf
from io import BytesIO
from flask import Flask, request
from threading import Thread
from PyPDF2 import PdfReader
import openai
import xml.etree.ElementTree as ET
import pandas as pd
from bs4 import BeautifulSoup
import html
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

openai.api_key = os.getenv("OPENAI_API_KEY")
print("DEBUG OPENAI KEY:", openai.api_key[:10] if openai.api_key else "YOK", flush=True)

BOT_TOKEN = "8116276773:AAHoSQAthKmijTE62bkqtGQNACf0zi0JuCs"
URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

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
            "Yanıtını '🤖 <b>Kriptos AI Yorum:</b>' etiketiyle başlat.\n\n"
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


### BILANCO OZET ###
def get_balance_summary(symbol):
    """Şimdilik pasif: bilanço özeti yakında eklenecek."""
    return {"summary": "🤖 <b>Kriptos AI:</b> ÇOK YAKINDA"}


##-------------------------MESAJ OLUŞTURMA-------------------------##
def build_message(symbol):
    symbol = symbol.strip().upper()
    info = get_price(symbol)
    tech = get_tv_analysis(symbol)
    lines = [f"💹 <b>{symbol}</b> Hisse Özeti (BIST100)"]

    # --- Fiyat ---
    if info:
        lines.append(f"💰 Fiyat: {info['fiyat']} TL")
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


# =============== ANA DÖNGÜ ===============
def main():
    print("🚀 Kriptos Borsa Botu aktif!", flush=True)
    last_update_id = None
    processed = set()
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
            if text.lower() == "/start":
                msg = (
                    "👋 <b>Kriptos BIST100 Takip Botu'na Hoş Geldin!</b>\n\n"
                    "💬 Sadece hisse kodunu (örnek: ASELS, THYAO...) yazın.\n\n"
                    "💡  Algoritmamız fiyat, güncel haberler, hacim vb. bilgileri iletir.\n\n"
                    "🤖 Yapay zeka destekli algoritmamız RSI ve EMA indikatör analizleri yapar ve (al-sat-vb.) önermeler üretir.\n\n"
                    "⚙️ Veriler: TradingView & Yahoo Finance'den sağlanmaktadır.\n\n"
                    "❗️  UYARI: Bilgiler kesinlikle YATIRIM TAVSİYESİ kapsamında değildir!\n\n"
                    "📊 Komut örneği: <b>ASELS/asels</b>\n\n"
                    "📩 Sorun veya öneriler için @kriptosbtc ile iletişime geçebilirsiniz."
                )
                send_message(chat_id, msg)
                continue
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
