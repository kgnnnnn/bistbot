import time, random, os, requests, yfinance as yf
from flask import Flask
from threading import Thread
import openai
import xml.etree.ElementTree as ET
import re

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

# =============== SAYI BİÇİMLENDİRME ===============
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

# =============== HABERLER (Google RSS) ===============
def get_news(symbol):
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+Borsa+İstanbul+OR+hisse&hl=tr&gl=TR&ceid=TR:tr"
        r = requests.get(url, timeout=8)
        if r.status_code != 200:
            return "📰 Haberler alınamadı."
        root = ET.fromstring(r.text)
        items = root.findall(".//item")[:3]
        if not items:
            return "📰 Lütfen Hisse Kodunu Doğru Giriniz. Örn: ASELS/asels"
        haberler = ["🗞️ <b>Son Haberler</b>"]
        for item in items:
            title = item.find("title").text
            link = item.find("link").text
            pub_node = item.find("pubDate")
            pub = pub_node.text[:16] if pub_node is not None and pub_node.text else ""
            haberler.append(f"🔹 <a href='{link}'>{title}</a> ({pub})")
        return "\n".join(haberler)
    except Exception as e:
        print("News error:", e, flush=True)
        return "📰 Haberler alınamadı."

# =============== HABER ANALİZİ (OpenAI - Kriptos AI) ===============
def analyze_news_with_ai(news_text):
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return "⚠️ AI yorum yapılamadı (API anahtarı eksik)."
        if "Haberler alınamadı" in news_text or "Lütfen Hisse Kodunu Doğru Giriniz" in news_text:
            return "⚠️ Yorum yapılacak geçerli haber bulunamadı."

        prompt = (
            "Aşağıda Borsa İstanbul'da işlem gören bir hisseye ait son haber başlıkları bulunuyor.\n"
            "Bu başlıkları analiz et; 1-2 cümlelik kısa bir Türkçe özet oluştur ve genel piyasa hissiyatını belirt (pozitif / negatif / nötr).\n"
            "Yatırım tavsiyesi verme. Sonuçta '🤖 <b>Kriptos AI Yorum:</b>' etiketiyle başla.\n\n"
            f"{news_text}"
        )

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 120,
                "temperature": 0.6,
            },
            timeout=15,
        )
        if response.status_code != 200:
            print("AI HTTP Hata:", response.text, flush=True)
            return "⚠️ AI yorum alınamadı."
        data = response.json()
        msg = data.get("choices", [{}])[0].get("message", {}).get("content")
        return msg.strip() if msg else "⚠️ AI yorum alınamadı."
    except Exception as e:
        print("AI yorum hatası:", e, flush=True)
        return "⚠️ AI yorum alınamadı."

# =============== FİYAT VERİSİ (YAHOO) ===============
def get_price(symbol):
    try:
        time.sleep(random.uniform(0.3, 0.6))
        ticker = yf.Ticker(symbol.upper() + ".IS")
        info = ticker.info
        if not info or "currentPrice" not in info or info["currentPrice"] is None:
            return None
        return {
            "url": f"https://finance.yahoo.com/quote/{symbol}.IS",
            "fiyat": info.get("currentPrice"),
            "degisim": f"{(info.get('regularMarketChangePercent') or 0):.2f}%",
            "acilis": info.get("open"),
            "kapanis": info.get("previousClose"),
            "tavan": info.get("dayHigh"),
            "taban": info.get("dayLow"),
            "hacim": format_number(info.get("volume")),
            "fk": info.get("trailingPE"),
            "pddd": info.get("priceToBook"),
            "piyasa": format_number(info.get("marketCap")),
        }
    except Exception:
        return None

# =============== TRADINGVIEW (RSI, EMA50/200) ===============
TV_URL = "https://tradingview-real-time.p.rapidapi.com/technicals/summary"
TV_HEADERS = {
    "x-rapidapi-key": "1749e090ffmsh612a371009ddbcap1c2f2cjsnaa23aba94831",
    "x-rapidapi-host": "tradingview-real-time.p.rapidapi.com",
}

def map_rsi_label(rsi):
    try:
        r = float(rsi)
    except:
        return "NÖTR"
    if r <= 20: return "GÜÇLÜ AL"
    if r <= 30: return "AL"
    if r >= 85: return "GÜÇLÜ SAT"
    if r >= 70: return "SAT"
    return "NÖTR"

def map_ema_signal(ema50, ema200):
    try:
        e50 = float(ema50)
        e200 = float(ema200)
        return "AL" if e50 >= e200 else "SAT"
    except:
        return "NÖTR"

def combine_recommendation(ema_sig, rsi_label):
    if ema_sig == "AL" and rsi_label in ("AL", "GÜÇLÜ AL"):
        return "ALIŞ"
    if ema_sig == "SAT" and rsi_label in ("SAT", "GÜÇLÜ SAT"):
        return "SATIŞ"
    return "NÖTR"

def get_tv_analysis(symbol):
    try:
        query = {"query": symbol.upper()}
        print(f"📡 TV /technicals/summary {query}", flush=True)
        r = requests.get(TV_URL, headers=TV_HEADERS, params=query, timeout=8)
        data = r.json()
        d = data.get("data") if isinstance(data, dict) else None
        if not d:
            print(f"⚠️ TradingView veri boş döndü: {data}", flush=True)
            return None
        return {
            "rsi": d.get("RSI"),
            "ema50": d.get("EMA50"),
            "ema200": d.get("EMA200"),
        }
    except Exception as e:
        print(f"⚠️ TradingView hata: {e}", flush=True)
        return None

# =============== KAP + GOOGLE NEWS + AI BİLANÇO ===============
def get_balance_summary(symbol):
    symbol = symbol.upper().strip()
    api_key = os.getenv("OPENAI_API_KEY")

    # --- 1️⃣ KAP RSS ---
    try:
        url = "https://www.kap.org.tr/tr/RssFeed/All"
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            root = ET.fromstring(r.text)
            items = root.findall(".//item")
            for it in items[:300]:
                title = (it.findtext("title") or "").upper()
                link = it.findtext("link") or ""
                if symbol in title and ("FİNANSAL" in title or "BİLANÇO" in title):
                    pub = it.findtext("pubDate") or ""
                    return {
                        "period": f"KAP Duyurusu ({pub})",
                        "summary": f"📎 <a href='{link}'>Son finansal rapor PDF</a>\n{title}",
                        "source": "KAP RSS"
                    }
    except Exception as e:
        print("KAP RSS hata:", e, flush=True)

    # --- 2️⃣ Google News + AI ---
    try:
        news_url = f"https://news.google.com/rss/search?q={symbol}+bilanço+OR+finansal+sonuçlar&hl=tr&gl=TR&ceid=TR:tr"
        r = requests.get(news_url, timeout=10)
        root = ET.fromstring(r.text)
        items = root.findall(".//item")[:3]
        if not items:
            return {"period": "—", "summary": "⚠️ Bilanço bilgisi bulunamadı."}
        headlines = "\n".join([i.findtext("title") for i in items if i.findtext("title")])
        if not api_key:
            return {"period": "—", "summary": headlines}
        prompt = (
            f"Aşağıda {symbol} hissesiyle ilgili bilanço haber başlıkları bulunuyor:\n"
            f"{headlines}\n\n"
            "Bu haberlerden yola çıkarak 2-3 cümlelik kısa Türkçe özet yaz. "
            "Net kâr, ciro, kâr marjı gibi verileri tahmin et; yatırım tavsiyesi verme."
        )
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 180,
                "temperature": 0.6,
            },
            timeout=20,
        )
        if resp.status_code != 200:
            print("AI fallback hata:", resp.text, flush=True)
            return {"period": "—", "summary": headlines}
        msg = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
        return {"period": "🧠 AI Haber Özet", "summary": msg, "source": "Google News + AI"}
    except Exception as e:
        print("AI fallback hata:", e, flush=True)
        return {"period": "—", "summary": "⚠️ Hiçbir kaynakta bilanço verisi bulunamadı.", "source": None}

# =============== MESAJ OLUŞTURMA ===============
def build_message(symbol):
    symbol = symbol.strip().upper()
    info = get_price(symbol)
    tech = get_tv_analysis(symbol)
    lines = [f"💹 <b>{symbol}</b> Hisse Özeti (BIST100)"]

    # --- Fiyat & Temel ---
    if info:
        if info.get("fiyat"):
            lines.append(f"💰 Fiyat: {info['fiyat']} TL")
        if info.get("degisim") != "0.00%":
            lines.append(f"📈 Günlük Değişim: {info['degisim']}")
        if info.get("piyasa"):
            lines.append(f"🏢 Piyasa Değeri: {info['piyasa']}")
        if info.get("fk") or info.get("pddd"):
            fkpd = []
            if info.get("fk"):
                fkpd.append(f"📗 F/K: {info['fk']}")
            if info.get("pddd"):
                fkpd.append(f"📘 PD/DD: {info['pddd']}")
            lines.append(" | ".join(fkpd))

    # --- Teknik Analiz ---
    if tech:
        rsi_val = tech.get("rsi")
        ema50 = tech.get("ema50")
        ema200 = tech.get("ema200")
        rsi_label = map_rsi_label(rsi_val)
        ema_sig = map_ema_signal(ema50, ema200)
        overall = combine_recommendation(ema_sig, rsi_label)

        lines.append("\n\n📊 <b>Teknik Analiz</b>")
        lines.append(f"⚡ RSI: {rsi_val} ({rsi_label})")
        lines.append(f"🔄 EMA(50/200): {ema_sig}")
        lines.append(f"🤖 <b>Kriptos AI:</b> {overall}")
    else:
        lines.append("\n\n📊 Teknik analiz verisi alınamadı.")

    # --- Bilanço Özeti ---
    fin = get_balance_summary(symbol)
    if fin:
        lines.append("\n\n🏦 <b>Bilanço Özeti</b>")
        if fin.get("summary"):
            lines.append(f"🤖 <b>Kriptos AI:</b>")
            lines.append(f"🧾 {fin['summary']}")

    # --- Haberler ---
    news_text = get_news(symbol)
    lines.append("\n\n" + news_text)

    # --- AI Haber Yorumu ---
    ai_comment = analyze_news_with_ai(news_text)
    lines.append("\n" + ai_comment)

    # --- Kaynak & Görüş ---
    lines.append("\n\n<b>💬 Görüş & Öneri:</b> @kriptosbtc")

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
            message = item.get("message", {}) or {}
            chat = message.get("chat", {}) or {}
            chat_id = chat.get("id")
            text = (message.get("text") or "").strip()
            if not chat_id or not text:
                continue
            if text.lower() == "/start":
                msg = (
                    "👋 <b>Kriptos BIST100 Takip Botu'na Hoş Geldin!</b>\n\n"
                    "💬 Hisse kodunu (örnek: ASELS, THYAO) yaz.\n"
                    "📈 Fiyat, RSI, EMA, bilanço ve haber özetlerini getiririm.\n\n"
                    "🤖 Yapay zeka bilanço & haber özetlerini oluşturur.\n"
                    "⚙️ Kaynaklar: TradingView, KAP, Google News, OpenAI, Yahoo Finance."
                )
                send_message(chat_id, msg)
                continue
            symbol = text.split()[0].lstrip("/").upper()
            print(f"Gelen istek: {symbol}", flush=True)
            reply = build_message(symbol)
            send_message(chat_id, reply)
            time.sleep(0.8)
        if len(processed) > 4000:
            processed = set(list(processed)[-1500:])
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
