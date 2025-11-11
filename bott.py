# bistbot.py
import time, random, requests, yfinance as yf, os
from flask import Flask
from threading import Thread
import xml.etree.ElementTree as ET

# === AYARLAR ===
BOT_TOKEN = "8116276773:AAHoSQAthKmijTE62bkqtGQNACf0zi0JuCs"
URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# === TELEGRAM ===
def get_updates(offset=None):
    try:
        r = requests.get(URL + "getUpdates", params={"timeout": 100, "offset": offset}, timeout=100)
        return r.json()
    except Exception as e:
        print("get_updates error:", e, flush=True)
        return {}

def send_message(chat_id, text):
    try:
        r = requests.post(
            URL + "sendMessage",
            params={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
        if r.status_code != 200:
            print("SendMessage error:", r.status_code, r.text, flush=True)
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

# === FİYAT VERİSİ (YAHOO) ===
def get_price(symbol):
    try:
        ticker = yf.Ticker(symbol.upper() + ".IS")
        fi = ticker.fast_info  # daha hafif API
        fiyat = fi.get("last_price", None)
        degisim = fi.get("regular_market_percent_change", None)
        if fiyat is None:
            return None
        return {
            "fiyat": fiyat,
            "degisim": f"{degisim:.2f}%" if degisim else "0.00%",
            "url": f"https://finance.yahoo.com/quote/{symbol}.IS",
        }
    except Exception as e:
        print("Price error:", e, flush=True)
        return None


# === TRADINGVIEW ANALİZİ ===
def get_tv_analysis(symbol):
    url = "https://tradingview-real-time.p.rapidapi.com/technicals/summary"
    query = {"query": symbol.upper()}
    headers = {
        "x-rapidapi-key": "1749e090ffmsh612a371009ddbcap1c2f2cjsnaa23aba94831",
        "x-rapidapi-host": "tradingview-real-time.p.rapidapi.com"
    }
    try:
        print(f"📡 TV /technicals/summary -> {query}", flush=True)
        r = requests.get(url, headers=headers, params=query, timeout=10)
        print("TV raw (prefix):", r.text[:300], flush=True)
        data = r.json()

        if not data or "data" not in data or not isinstance(data["data"], dict):
            print("⚠️ TV format hatası:", data, flush=True)
            return "📊 Teknik analiz alınamadı (TradingView)."

        d = data["data"]
        rsi = round(d.get("RSI", 0), 2)
        macd = round(d.get("MACD.macd", 0), 2)
        rec = d.get("Recommend.All", "—")

        if (rsi == 0 and macd == 0) or rec in ("", "—", None):
            print("⚠️ Boş teknik veri geldi.", flush=True)
            return "📊 Teknik analiz alınamadı (TradingView)."

        return f"📊 RSI: {rsi} | MACD: {macd} | Öneri: {rec}"

    except Exception as e:
        print("TradingView error:", e, flush=True)
        return "📊 Teknik analiz alınamadı (TradingView)."

# === HABERLER ===
def get_news(symbol):
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+Borsa+İstanbul+OR+hisse&hl=tr&gl=TR&ceid=TR:tr"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return "📰 Haberler alınamadı."

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
    info = get_price(symbol)
    analysis = get_tv_analysis(symbol)
    news = get_news(symbol)

    if not info:
        return f"⚠️ {symbol} için veri alınamadı veya desteklenmiyor."

    lines = [f"📈 <b>{symbol}</b> Hisse Özeti (BIST)"]
    lines.append(f"💰 Fiyat: {info['fiyat']} TL")
    if info.get("degisim"):
        lines.append(f"📉 Değişim: {info['degisim']}")

    detaylar = []
    if info.get("acilis"):
        detaylar.append(f"Açılış: {info['acilis']}")
    if info.get("kapanis"):
        detaylar.append(f"Kapanış: {info['kapanis']}")
    if detaylar:
        lines.append("📊 " + " | ".join(detaylar))

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
        fk_pd = []
        if info.get("fk"):
            fk_pd.append(f"📗 F/K: {info['fk']}")
        if info.get("pddd"):
            fk_pd.append(f"📘 PD/DD: {info['pddd']}")
        if fk_pd:
            lines.append(" | ".join(fk_pd))

    lines.append("\n" + analysis)
    lines.append("\n" + news)
    lines.append(f"\n📎 <a href='{info['url']}'>Kaynak: Yahoo Finance</a>")

    return "\n".join(lines)

# === ANA DÖNGÜ ===
def main():
    print("🚀 Borsa İstanbul Botu (TradingView Entegre) çalışıyor...", flush=True)
    last_update_id = None
    processed = set()

    while True:
        updates = get_updates(last_update_id)
        if not updates:
            time.sleep(1)
            continue

        for item in updates.get("result", []):
            uid = item.get("update_id")
            if uid in processed:
                continue
            processed.add(uid)
            last_update_id = uid + 1

            msg = item.get("message", {})
            chat_id = msg.get("chat", {}).get("id")
            text = (msg.get("text") or "").strip().upper()
            if not text:
                continue

            print(f"Gelen istek: {text}", flush=True)
            send_message(chat_id, build_message(text))
        time.sleep(1)

# === KEEP ALIVE ===
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot aktif!", 200

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run).start()

if __name__ == "__main__":
    main()
