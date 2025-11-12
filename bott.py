import time, random, os, requests, yfinance as yf
from flask import Flask
from threading import Thread
import openai
import os, math
from isyatirimhisse import fetch_financials

openai.api_key = os.getenv("OPENAI_API_KEY")
print("DEBUG OPENAI KEY:", openai.api_key[:10] if openai.api_key else "YOK", flush=True)

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

# =============== HABER ANALİZİ (OpenAI - Kriptos AI) ===============
def analyze_news_with_ai(news_text):
    """Son 3 haber başlığını özetleyip, kısa bir piyasa hissiyatı yorumu döndürür."""
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return "⚠️ AI yorum yapılamadı (API anahtarı eksik)."

        # Eğer haber metni Google RSS default mesajlarından biri ise (örneğin 'Haberler alınamadı')
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
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
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


# =============== YFINANCE BİLANÇO ÖZETİ (Temel Finansallar) ===============


def _pick(df, patterns):
    # satır adında geçen kalemleri esnek yakala (Türkçe varyasyonlar)
    # df kolon/şema farklı olabilir; hem 'Kalem' hem 'item' olasılıklarını dene
    name_col = 'Kalem' if 'Kalem' in df.columns else ('item' if 'item' in df.columns else None)
    if not name_col: 
        return None
    mask = False
    for p in patterns:
        mask = mask | df[name_col].str.contains(p, case=False, regex=True, na=False)
    sub = df[mask].copy()
    if sub.empty:
        return None
    # En son dönem kolonunu/alanını bul
    # Geniş formattaysa son sütunu, uzun formattaysa 'Period' ya da 'period' + 'Value'
    if 'Period' in df.columns and ('Value' in df.columns or 'value' in df.columns):
        vcol = 'Value' if 'Value' in df.columns else 'value'
        # aynı kalemden birden fazla dönem varsa en yeniyi al
        sub = sub.sort_values('Period').tail(1)
        return sub.iloc[0][vcol]
    else:
        # geniş form: ilk iki sütun meta, sonrası dönem sütunlarıdır varsay
        period_cols = [c for c in sub.columns if c not in ('Sembol','Symbol','Kalem','item','Grup','Group','Para','Currency')]
        if not period_cols:
            return None
        last = period_cols[-1]
        # sayıya çevir
        val = sub.iloc[0][last]
        try:
            return float(val)
        except Exception:
            # 1.234,56 gibi değerleri normalize et
            if isinstance(val, str):
                v = val.replace('.', '').replace(',', '.')
                try:
                    return float(v)
                except Exception:
                    return None
            return None

def get_balance_summary(symbol: str):
    """
    yfinance YOK. İş Yatırım kaynaklı finansalları çeker.
    Dönem, Net Kâr, Ciro, Özsermaye, Borç/Özsermaye, Kâr marjı hesaplar.
    """
    try:
        # UFRS (financial_group='2') tercih ettim; TRY bazlı çekiyoruz
        df = fetch_financials(
            symbols=symbol.upper(),
            start_year=2022,  # çok geriye gitmeye gerek yok
            end_year=2100,
            exchange="TRY",
            financial_group="2"  # '1': XI_29, '2': UFRS, '3': UFRS_K
        )
        if df is None or len(df) == 0:
            return {"period": "—", "summary": "⚠️ Finansal tablo bulunamadı."}

        # Dönem metni: en yeni dönem ismini bul
        period_col = 'Period' if 'Period' in df.columns else ('period' if 'period' in df.columns else None)
        if period_col:
            last_period = sorted(df[period_col].dropna().unique())[-1]
            period_text = str(last_period)
            dfl = df[df[period_col] == last_period].copy()
        else:
            # geniş form ise son dönem sütunu adı
            meta_cols = ('Sembol','Symbol','Kalem','item','Grup','Group','Para','Currency')
            period_cols = [c for c in df.columns if c not in meta_cols]
            period_text = period_cols[-1] if period_cols else "Son dönem"
            dfl = df.copy()

        # Kalemleri çek
        net_kar = _pick(dfl, [r"net.*k[aâ]r", r"kar", r"kâr", r"donem k[aâ]r", r"period profit"])
        ciro    = _pick(dfl, [r"sat[iı]ş geliri", r"hasılat", r"ciro", r"revenue", r"sales"])
        ozser   = _pick(dfl, [r"özkaynak", r"ozsermay", r"equity", r"shareholders.*equity"])
        borc    = _pick(dfl, [r"toplam bor[cç]", r"y[uü]k[uü]ml[uü]l[uü]k", r"total liab", r"bor[çc]"])

        # oranlar
        borc_orani = None
        if (ozser or ozser == 0) and (borc or borc == 0):
            try:
                borc_orani = (float(borc)/float(ozser))*100 if float(ozser)!=0 else None
            except Exception:
                borc_orani = None

        kar_marji = None
        if (net_kar or net_kar == 0) and (ciro or ciro == 0):
            try:
                kar_marji = (float(net_kar)/float(ciro))*100 if float(ciro)!=0 else None
            except Exception:
                kar_marji = None

        def bn(v):
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                return None
            try:
                return float(v)
            except Exception:
                return None

        return {
            "period": period_text,
            "net_kar": bn(net_kar),
            "ciro": bn(ciro),
            "ozsermaye": bn(ozser),
            "borc_orani": borc_orani,
            "kar_marji": kar_marji,
            "source": "İş Yatırım (isyatirimhisse)"
        }
    except Exception as e:
        print("get_balance_summary (isyatirimhisse) hata:", e, flush=True)
        return {"period": "—", "summary": "⚠️ Finansal tablo hatası."}

# =============== MESAJ OLUŞTURMA ===============
def build_message(symbol):
    symbol = symbol.strip().upper()
    info = get_price(symbol)
    tech = get_tv_analysis(symbol)
    lines = [f"💹 <b>{symbol}</b> Hisse Özeti (BIST100)"]

    # --- Fiyat & temel bilgiler ---
    if info:
        if info.get("fiyat") is not None:
            lines.append(f"💰 Fiyat: {info['fiyat']} TL")
        if info.get("degisim") and info["degisim"] != "0.00%":
            lines.append(f"🧮 Değişim: {info['degisim']}")
        satir = []
        if info.get("acilis") is not None:
            satir.append(f"Açılış: {info['acilis']}")
        if info.get("kapanis") is not None:
            satir.append(f"Kapanış: {info['kapanis']}")
        if satir:
            lines.append("📊 " + " | ".join(satir))
        satir = []
        if info.get("tavan") is not None:
            satir.append(f"🔼 Tavan: {info['tavan']}")
        if info.get("taban") is not None:
            satir.append(f"🔽 Taban: {info['taban']}")
        if satir:
            lines.append(" | ".join(satir))
        if info.get("hacim"):
            lines.append(f"💸 Hacim: {info['hacim']}")
        if info.get("piyasa"):
            lines.append(f"🏢 Piyasa Değeri: {info['piyasa']}")
        fkpddd = []
        if info.get("fk") is not None:
            fkpddd.append(f"📗 F/K: {info['fk']}")
        if info.get("pddd") is not None:
            fkpddd.append(f"📘 PD/DD: {info['pddd']}")
        if fkpddd:
            lines.append(" | ".join(fkpddd))

    # --- Teknik Analiz ---
    if tech and (tech.get("rsi") is not None or (tech.get("ema50") and tech.get("ema200"))):
        rsi_val = tech.get("rsi")
        ema50 = tech.get("ema50")
        ema200 = tech.get("ema200")

        rsi_label = map_rsi_label(rsi_val)
        ema_sig = map_ema_signal(ema50, ema200)
        overall = combine_recommendation(ema_sig, rsi_label)

        parts = [
            f"⚡ RSI(G): {round(float(rsi_val),2) if rsi_val else '—'} ({rsi_label})",
            f"🔄 EMA(G): {ema_sig}",
            f"🤖 <b>Kriptos AI:</b> {overall}"
        ]
        lines.append("\n\n📊 <b>Teknik Analiz Sonuçları</b>\n" + "\n".join(parts))
    else:
        lines.append("\n\n📊 Teknik analiz alınamadı.")

    # --- Temel Finansal Veriler (Bilanço Özeti) ---
    fin = get_balance_summary(symbol)
    if fin:
        lines.append("\n\n🏦 <b>Bilanço Özeti</b>")
        lines.append(f"📅 Dönem: {fin['period']}")
        if fin.get('net_kar'):
            lines.append(f"💰 Net Kâr: {round(fin['net_kar']/1e9,2)} milyar TL")
        if fin.get('ciro'):
            lines.append(f"💵 Ciro: {round(fin['ciro']/1e9,2)} milyar TL")
        if fin.get('ozsermaye'):
            lines.append(f"🏢 Özsermaye: {round(fin['ozsermaye']/1e9,2)} milyar TL")
        if fin.get('borc_orani'):
            lines.append(f"📊 Borç/Özsermaye: %{round(fin['borc_orani'],1)}")
        if fin.get('kar_marji'):
            lines.append(f"📈 Kâr Marjı: %{round(fin['kar_marji'],1)}")

    # --- Haberler (tek çekim) ---
    news_text = get_news(symbol)
    lines.append("\n\n" + news_text)

    # --- AI Haber Yorumu ---
    ai_comment = analyze_news_with_ai(news_text)
    lines.append("\n" + ai_comment)

    # --- Kaynak ---
    if info and info.get("url"):
        lines.append(f"\n\n📎 <a href='{info['url']}'>Kaynak: Yahoo Finance</a>")

    # --- Görüş / İletişim ---
    lines.append("\n\n<b>💬 Görüş & Öneri:</b> @kriptosbtc")

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
