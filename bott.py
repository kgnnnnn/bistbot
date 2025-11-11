import time, random, os, requests, yfinance as yf
from flask import Flask
from threading import Thread

BOT_TOKEN = "8116276773:AAHoSQAthKmijTE62bkqtGQNACf0zi0JuCs"
URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# =============== TELEGRAM ===============
def get_updates(offset=None):
    try:
        r = requests.get(URL + "getUpdates",
                         params={"timeout": 100, "offset": offset},
                         timeout=100)
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
        import xml.etree.ElementTree as ET
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

# =============== YAHOO FİYAT & F/K, PD/DD (tek deneme) ===============
def get_price(symbol):
    """YF rate-limit olursa sessizce None döner; mesaj yine tek parça gönderilir."""
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

# =============== TRADINGVIEW REAL-TIME (RSI, EMA50/EMA200) ===============
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
    """TradingView'den RSI, EMA50, EMA200 çeker; yoksa None döner (fallback yok)."""
    try:
        query = {"query": symbol.upper()}
        print(f"📡 TV /technicals/summary {query}", flush=True)
        r = requests.get(TV_URL, headers=TV_HEADERS, params=query, timeout=8)
        data = r.json()
        d = data.get("data") if isinstance(data, dict) else None
        if isinstance(d, dict):
            return {
                "rsi": d.get("RSI"),
                "ema50": d.get("EMA50"),
                "ema200": d.get("EMA200"),
            }
    except Exception:
        pass
    return None

# =============== YFINANCE BİLANÇO ÖZETİ (Temel Finansallar) ===============
def get_balance_summary(symbol):
    """Yahoo Finance üzerinden son çeyrek finansal özet (Net Kâr, Ciro, Özsermaye, Borç, Kâr Marjı)."""
    try:
        ticker = yf.Ticker(symbol.upper() + ".IS")
        fin = ticker.quarterly_financials
        bs = ticker.quarterly_balance_sheet

        if fin.empty or bs.empty:
            return None

        last_col = fin.columns[0]
        net_kar = fin.loc["Net Income"][last_col] if "Net Income" in fin.index else None
        ciro = fin.loc["Total Revenue"][last_col] if "Total Revenue" in fin.index else None
        ozsermaye = bs.loc["Total Stockholder Equity"][last_col] if "Total Stockholder Equity" in bs.index else None
        borc = bs.loc["Total Liab"][last_col] if "Total Liab" in bs.index else None

        borc_orani = (borc / ozsermaye * 100) if borc and ozsermaye else None
        kar_marji = (net_kar / ciro * 100) if net_kar and ciro else None

        # --- Tarih formatı ve çeyrek hesaplama ---
        if hasattr(last_col, "strftime"):
            tarih = last_col.strftime("%d/%m/%Y")  # Türk tarih formatı
            ay = int(last_col.strftime("%m"))
            yil = int(last_col.strftime("%Y"))
            if 1 <= ay <= 3:
                ceyrek = "1. Çeyrek"
            elif 4 <= ay <= 6:
                ceyrek = "2. Çeyrek"
            elif 7 <= ay <= 9:
                ceyrek = "3. Çeyrek"
            else:
                ceyrek = "4. Çeyrek"
            period_text = f"{yil} {ceyrek} ({tarih})"
        else:
            period_text = str(last_col)

        return {
            "period": period_text,
            "net_kar": net_kar,
            "ciro": ciro,
            "ozsermaye": ozsermaye,
            "borc_orani": borc_orani,
            "kar_marji": kar_marji,
        }

    except Exception as e:
        print("Finansal veri hatası:", e)
        return None


# =============== MESAJ OLUŞTURMA ===============
def build_message(symbol):
    symbol = symbol.strip().upper()
    info = get_price(symbol)
    tech = get_tv_analysis(symbol)
    lines = [f"📈 <b>{symbol}</b> Hisse Özeti (BIST)"]

    if info:
        if info.get("fiyat") is not None:
            lines.append(f"💰 Fiyat: {info['fiyat']} TL")
        if info.get("degisim") and info["degisim"] != "0.00%":
            lines.append(f"📉 Değişim: {info['degisim']}")
        satir = []
        if info.get("acilis") is not None: satir.append(f"Açılış: {info['acilis']}")
        if info.get("kapanis") is not None: satir.append(f"Kapanış: {info['kapanis']}")
        if satir: lines.append("📊 " + " | ".join(satir))
        satir = []
        if info.get("tavan") is not None: satir.append(f"🔼 Tavan: {info['tavan']}")
        if info.get("taban") is not None: satir.append(f"🔽 Taban: {info['taban']}")
        if satir: lines.append(" | ".join(satir))
        if info.get("hacim"): lines.append(f"💸 Hacim: {info['hacim']}")
        if info.get("piyasa"): lines.append(f"🏢 Piyasa Değeri: {info['piyasa']}")
        fkpddd = []
        if info.get("fk") is not None: fkpddd.append(f"📗 F/K: {info['fk']}")
        if info.get("pddd") is not None: fkpddd.append(f"📘 PD/DD: {info['pddd']}")
        if fkpddd: lines.append(" | ".join(fkpddd))

    if tech and (tech.get("rsi") is not None or (tech.get("ema50") and tech.get("ema200"))):
        rsi_val = tech.get("rsi")
        ema50 = tech.get("ema50")
        ema200 = tech.get("ema200")
        rsi_label = map_rsi_label(rsi_val)
        ema_sig = map_ema_signal(ema50, ema200)
        overall = combine_recommendation(ema_sig, rsi_label)
        parts = [
            f"RSI(G): {round(float(rsi_val),2) if rsi_val else '—'} ({rsi_label})",
            f"EMA(G): {ema_sig}",
            f"Tahmin(Kriptos AI): {overall}"
        ]
        lines.append("\n📊 " + "\n".join(parts))
    else:
        lines.append("\n📊 Teknik analiz alınamadı.")

    # --- Temel Finansal Veriler (Bilanço Özeti) ---
    fin = get_balance_summary(symbol)
    if fin:
        lines.append("\n🏦 <b>Bilanço Özeti</b>")
        lines.append(f"📅 Dönem: {fin['period']}")
        if fin.get('net_kar'): lines.append(f"💰 Net Kâr: {round(fin['net_kar']/1e9,2)} milyar TL")
        if fin.get('ciro'): lines.append(f"💵 Ciro: {round(fin['ciro']/1e9,2)} milyar TL")
        if fin.get('ozsermaye'): lines.append(f"🏢 Özsermaye: {round(fin['ozsermaye']/1e9,2)} milyar TL")
        if fin.get('borc_orani'): lines.append(f"📊 Borç/Özsermaye: %{round(fin['borc_orani'],1)}")
        if fin.get('kar_marji'): lines.append(f"📈 Kâr Marjı: %{round(fin['kar_marji'],1)}")

    lines.append("\n" + get_news(symbol))

    if info and info.get("url"):
        lines.append(f"\n📎 <a href='{info['url']}'>Kaynak: Yahoo Finance</a>")

    return "\n".join(lines)

# =============== ANA DÖNGÜ (tek mesaj garantisi) ===============
def main():
    print("🚀 Borsa İstanbul Botu çalışıyor...", flush=True)
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
                    "💬 Sadece hisse kodunu (örnek: ASELS, THYAO...) yazın.\n\n"
                    "Algoritmamız fiyat, güncel haberler, hacim vb. bilgileri iletir.\n\n"
                    "Yapay zeka destekli algoritmamız RSI ve EMA indikatör analizleri yapar ve (al-sat-vb.) önermeler üretir.\n\n"
                    "⚙️ Veriler: TradingView & Yahoo Finance'den sağlanmaktadır.\n\n"
                    "❗️UYARI: Bilgiler kesinlikle YATIRIM TAVSİYESİ kapsamında değildir!\n\n"
                    "📊 Komut örneği: <b>ASELS/asels</b>\n\n"
                    "Sorun veya öneriler için @kriptosbtc ile iletişime geçebilirsiniz."
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
