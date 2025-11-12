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
from urllib.parse import quote

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


# ==== BILANÇO ÖZETİ: Sıkı ve Çok-Kaynaklı Haber Tabanlı Çıkarım ====
# Bu blok, mevcut get_balance_summary(symbol) fonksiyonunun yerini alır.

import re, html, time, random, requests, xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import quote

# ——— Yapılandırma ———
BAL_NEWS_DOMAINS = [
    "kap.org.tr",
    "fintables.com",
    "bloomberght.com",
    "dunya.com",
    "borsagundem.com",
    "foreks.com",
    "hurriyet.com.tr",
    "ntv.com.tr",
    "trthaber.com",
    "cnnturk.com",
    "patronlardunyasi.com",
    "haberturk.com",
]

COMMON_TICKERS = [
    "ASELS","HEKTS","SASA","EREGL","THYAO","BIMAS","TUPRS","YKBNK","AKBNK","GARAN",
    "KRDMD","KCHOL","SISE","PETKM","TOASO","SAHOL","TCELL","PGSUS","VESTL","KOZAL",
    "KOZAA","KONTR","ALARK","ISCTR","HALKB","TSKB","GESAN","ODAS","ECILC","AGHOL"
]

FIN_KEYWORDS_NEAR = {
    "net_income": ["net kâr", "net kar", "net dönem kârı", "net dönem karı", "net profit", "net income"],
    "revenue":    ["ciro", "gelir", "hasılat", "net satış", "revenue", "sales"],
    "debt":       ["toplam borç", "net borç", "borç", "total debt"],
    "equity":     ["özsermaye", "özkaynak", "öz kaynak", "equity"],
    "ebitda":     ["ebitda"],
}

# haberin kabul edilmesi için bu kelimelerden en az biri başlık veya içerikte geçmeli
FIN_KEYWORDS_REQUIRED = [
    "bilanço", "bilanco", "finansal sonuç", "finansal sonuçlar", "finansal", "faaliyet raporu",
    "net kâr", "net kar", "ciro", "gelir", "zarar", "özsermaye", "özkaynak", "borç",
    "ebitda", "çeyrek", "dönemsel sonuç", "3. çeyrek", "4. çeyrek"
]

NEARBY_WINDOW = 120

UNIT_MAP = {
    "milyar": 1_000_000_000,
    "milyon": 1_000_000,
    "bin": 1_000,
    "k": 1_000,
    "m": 1_000_000,
    "b": 1_000_000_000,
}

NUM_CANDIDATE_RE = re.compile(
    r"(?:(?:\d{1,3}(?:[.\s]\d{3})+)|(?:\d+(?:[.,]\d+)?))(?:\s*(?:milyar|milyon|bin|k|m|b|TL|₺|tl))?",
    flags=re.IGNORECASE,
)

def _safe_get(url: str) -> str:
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0 (KriptosBot/1.0)"})
        if r.status_code != 200:
            return ""
        txt = r.text
        return txt[:600_000] if len(txt) > 600_000 else txt
    except Exception:
        return ""

def _contains_2025_in_any(title: str, url: str, html_text: str) -> bool:
    return any("2025" in s for s in [title or "", url or "", html_text or ""])

def _within_last_100_days(pub: str) -> bool:
    if not pub:
        return True
    try:
        try:
            dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z").replace(tzinfo=None)
        except Exception:
            dt = datetime.strptime(pub.split("+")[0].strip(), "%a, %d %b %Y %H:%M:%S").replace(tzinfo=None)
        return dt >= (datetime.now() - timedelta(days=100))
    except Exception:
        return True

def _normalize_number(text):
    if not text:
        return None
    t = text.lower().strip().replace("\u00a0", " ").replace(" ", "")
    multiplier = 1
    for word, mul in UNIT_MAP.items():
        if word in t:
            multiplier = mul
            t = t.replace(word, "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t and "." not in t:
        t = t.replace(",", ".")
    else:
        t = t.replace(".", "")
    try:
        val = float(t) * multiplier
        return int(round(val)) if abs(val - round(val)) < 1e-4 else val
    except Exception:
        return None

def _extract_numbers_near_keywords(text, keywords_map):
    res = {k: [] for k in keywords_map.keys()}
    low = text.lower()
    for field, kws in keywords_map.items():
        for kw in kws:
            for m in re.finditer(re.escape(kw.lower()), low):
                start = max(0, m.start() - NEARBY_WINDOW)
                end = min(len(low), m.end() + NEARBY_WINDOW)
                window = low[start:end]
                for num_m in NUM_CANDIDATE_RE.finditer(window):
                    norm = _normalize_number(num_m.group(0))
                    if norm is not None:
                        res[field].append(norm)
    return res

def _has_required_fin_keyword(title: str, html_text: str) -> bool:
    low = (title + " " + html_text).lower()
    return any(k in low for k in FIN_KEYWORDS_REQUIRED)

def _belongs_to_symbol(symbol: str, title: str, url: str, html_text: str) -> bool:
    s = (symbol or "").upper()
    joined = " ".join([title or "", url or "", html_text or ""]).upper()
    if s not in joined:
        return False
    for tk in COMMON_TICKERS:
        if tk == s:
            continue
        if joined.count(tk) >= 2:
            return False
    return True

def _fetch_gnews_items(symbol: str, domain: str):
    ts = int(time.time() * 1000)
    query = f'{symbol} ("bilanço" OR "net kâr" OR "net kar" OR "ciro" OR "gelir" OR "zarar" OR "finansal sonuç" OR "faaliyet raporu" OR "çeyrek") site:{domain}'
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=tr&gl=TR&ceid=TR:tr&t={ts}&nocache={random.randint(10000,9999999)}"
    try:
        r = requests.get(url, timeout=12)
        if r.status_code != 200:
            return []
        raw = r.text.encode("utf-8", "ignore").decode("utf-8", "ignore").replace("&", "&amp;")
        root = ET.fromstring(raw)
        out = []
        for it in root.findall(".//item"):
            title = (it.find("title").text or "").strip()
            link = (it.find("link").text or "").strip()
            pub = (it.find("pubDate").text or "").strip() if it.find("pubDate") is not None else ""
            out.append({"title": title, "link": link, "pub": pub, "domain": domain})
        return out
    except Exception as e:
        print("gnews err", domain, e, flush=True)
        return []

def _format_human(val):
    v = float(val)
    if v >= 1_000_000_000:
        return f"{round(v/1_000_000_000,2)} milyar TL"
    if v >= 1_000_000:
        return f"{round(v/1_000_000,2)} milyon TL"
    if v >= 1_000:
        return f"{round(v/1_000,2)} bin TL"
    return f"{int(v) if v.is_integer() else v} TL"

def get_balance_summary(symbol: str):
    """
    Çok-kaynaklı finans haberlerinden (Google News + site:domain) 
    2025 veya son 100g filtresiyle
    net kâr/ciro/borç/özsermaye/EBITDA değerlerini çıkarmaya çalışır.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return {"summary": "📄 Geçersiz hisse kodu."}

    # 1️⃣ Haber adaylarını topla
    domains = list(BAL_NEWS_DOMAINS)
    random.shuffle(domains)
    candidates = []
    for d in domains:
        items = _fetch_gnews_items(sym, d)
        if items:
            candidates.extend(items)
        if len(candidates) > 100:
            break

    # 2️⃣ Filtrele + HTML analiz
    picked = []
    for it in candidates:
        title, link, pub = it["title"], it["link"], it["pub"]
        if not link.startswith("http"):
            continue

        html_text = _safe_get(link)
        if not html_text:
            continue

        has_2025 = _contains_2025_in_any(title, link, html_text)
        recent = _within_last_100_days(pub)
        if not has_2025 and not recent:
            continue

        if not _has_required_fin_keyword(title, html_text):
            continue

        if not _belongs_to_symbol(sym, title, link, html_text):
            continue

        plain = re.sub(r"<[^>]+>", " ", html_text)
        numbers = _extract_numbers_near_keywords(plain, FIN_KEYWORDS_NEAR)

        picked.append({
            "title": title,
            "link": link,
            "pub": pub,
            "domain": it["domain"],
            "numbers": numbers,
            "priority": (1 if has_2025 else 0)
        })

        if len(picked) >= 5:
            break

    if not picked:
        return {"summary": "📰 Son 100 günde güncel finansal haber bulunamadı."}

    # 3️⃣ 2025 geçenleri öncele
    picked.sort(key=lambda x: x["priority"], reverse=True)

    # 4️⃣ alan bazında değer seçimi
    agg = {k: [] for k in FIN_KEYWORDS_NEAR}
    for p in picked:
        for fld, vals in p["numbers"].items():
            agg[fld].extend(vals)

    final = {}
    for fld, arr in agg.items():
        if not arr:
            final[fld] = None
            continue
        counts = {}
        for v in arr:
            k = int(round(v)) if isinstance(v, (int, float)) else v
            counts[k] = counts.get(k, 0) + 1
        best_key = max(counts.items(), key=lambda x: (x[1], x[0]))[0]
        final[fld] = best_key

    # 5️⃣ insan okunur özet
    parts = []
    if final.get("net_income") is not None:
        parts.append(f"💸 Net kâr: {_format_human(final['net_income'])}")
    if final.get("revenue") is not None:
        parts.append(f"🏢 Ciro/Gelir: {_format_human(final['revenue'])}")
    if final.get("ebitda") is not None:
        parts.append(f"📈 EBITDA: {_format_human(final['ebitda'])}")
    if final.get("equity") is not None:
        parts.append(f"🔐 Özsermaye: {_format_human(final['equity'])}")
    if final.get("debt") is not None:
        parts.append(f"💳 Toplam Borç: {_format_human(final['debt'])}")

    summary = "📰 Haberlerden net bilanço rakamı seçilemedi." if not parts else \
               "🤖 <b>Bilanço Özeti (haber tabanlı)</b>\n" + "\n".join(parts)

    # 6️⃣ kaynaklar
    lines = [summary, "\n🔗 <b>Kaynaklar</b>"]
    for p in picked[:3]:
        pub = p["pub"].split("+")[0].strip() if p["pub"] else ""
        lines.append(f"• <a href='{p['link']}'>{html.escape(p['title'])}</a> ({p['domain']}) {('— ' + pub) if pub else ''}")

    return {"summary": "\n".join(lines)}



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
