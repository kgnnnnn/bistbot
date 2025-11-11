# bistbot.py
import time, requests, yfinance as yf, random, os
from flask import Flask
from threading import Thread

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
        requests.post(
            URL + "sendMessage",
            params={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
        )
    except Exception as e:
        print("Send error:", e, flush=True)

# === FİYAT VERİSİ ===
def get_price(symbol):
    try:
        ticker = yf.Ticker(symbol.upper() + ".IS")
        info = ticker.info
        if not info or "currentPrice" not in info:
            return None
        return {
            "fiyat": info.get("currentPrice"),
            "degisim": f"{info.get('regularMarketChangePercent', 0):.2f}%",
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
        if "data" in data and isinstance(data["data"], dict):
            d = data["data"]
            rsi = round(d.get("RSI", 0), 2)
            macd = round(d.get("MACD.macd", 0), 2)
            rec = data.get("data", {}).get("Recommend.All", "")
            return f"📊 RSI: {rsi} | MACD: {macd} | Öneri: {rec}"
        return "📊 Teknik analiz alınamadı (TradingView)."
    except Exception as e:
        print("TradingView error:", e, flush=True)
        return "📊 Teknik analiz alınamadı (TradingView)."

# === MESAJ OLUŞTUR ===
def build_message(symbol):
    info = get_price(symbol)
    analysis = get_tv_analysis(symbol)
    if not info:
        return f"⚠️ {symbol} için fiyat verisi alınamadı."

    return (
        f"📈 <b>{symbol}</b> Hisse Özeti\n"
        f"💰 Fiyat: {info['fiyat']} TL\n"
        f"📉 Değişim: {info['degisim']}\n\n"
        f"{analysis}\n\n"
        f"📎 <a href='{info['url']}'>Kaynak: Yahoo Finance</a>"
    )

# === ANA DÖNGÜ ===
def main():
    print("🚀 Borsa İstanbul Botu çalışıyor...", flush=True)
    last_update_id = None
    processed = set()
    while True:
        updates = get_updates(last_update_id)
        if not updates:
            time.sleep(1)
            continue

        for item in updates.get("result", []):
            uid = item["update_id"]
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
