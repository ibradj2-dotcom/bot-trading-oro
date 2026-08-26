import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time
import threading
from flask import Flask

# ==========================================
# --- FINTO SITO WEB PER INGANNARE RENDER ---
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Il Bot Wick Block (Ora Italiana) è online!"

# ==========================================
# --- 1. IMPOSTAZIONI TELEGRAM E PARAMETRI ---
# ==========================================
TELEGRAM_TOKEN = 'IL_TUO_TOKEN_BOT_QUI'
TELEGRAM_CHAT_ID = 'IL_TUO_CHAT_ID_QUI'

SYMBOL = 'XAUUSD'
EXCHANGE = 'OANDA' 
NUM_ACCEL = 4

TIMEFRAMES = [
    (Interval.in_1_hour, '1 Ora'),
    (Interval.in_15_minute, '15 Minuti'),
    (Interval.in_5_minute, '5 Minuti')
]

# Fuso orario di Roma
TZ_ROMA = ZoneInfo("Europe/Rome")

# Memoria cronologica dei segnali già inviati
segnali_inviati_storico = set()

# ==========================================
# --- 2. FUNZIONE DI ANALISI ---
# ==========================================
def analizza_tf(tv, tf_obj, tf_name):
    print(f"[{datetime.now(TZ_ROMA).strftime('%H:%M:%S')}] 🔄 Analisi {SYMBOL} su {tf_name}...")
    try:
        df = tv.get_hist(symbol=SYMBOL, exchange=EXCHANGE, interval=tf_obj, n_bars=500)
    except Exception as e:
        print(f"❌ Errore di connessione su {tf_name}: {e}")
        return

    if df is not None and not df.empty:
        # Calcoliamo il limite di 24 ore fa basato sull'ora di Roma
        limite_24h = datetime.now(TZ_ROMA) - timedelta(hours=24)

        for curr in range(NUM_ACCEL + 1, len(df)):
            data_candela = df.index[curr]
            
            # Gestione della conversione dell'orario della candela a Ora Italiana
            try:
                if isinstance(data_candela, pd.Timestamp):
                    if data_candela.tz is None:
                        # Se i dati non hanno fuso, assumiamo UTC o li normalizziamo
                        data_candela_it = data_candela.tz_localize("UTC").tz_convert(TZ_ROMA)
                    else:
                        data_candela_it = data_candela.tz_convert(TZ_ROMA)
                else:
                    data_candela_it = pd.to_datetime(data_candela).tz_localize("UTC").tz_convert(TZ_ROMA)
            except Exception:
                # Fallback di sicurezza se la conversione fallisce
                data_candela_it = pd.to_datetime(data_candela)

            # FILTRO: Analizziamo solo le ultime 24 ore e il futuro
            if data_candela_it < limite_24h:
                continue

            accel_bullish = True
            accel_bearish = True

            for i in range(1, NUM_ACCEL + 1):
                idx = curr - i
                idx_prev = curr - i - 1
                
                is_green_current = df['close'].iloc[idx] > df['open'].iloc[idx]
                is_green_prev = df['close'].iloc[idx_prev] > df['open'].iloc[idx_prev]
                breaks_high = df['close'].iloc[idx] > df['high'].iloc[idx_prev]
                
                if not (is_green_current and is_green_prev and breaks_high):
                    accel_bullish = False

                is_red_current = df['close'].iloc[idx] < df['open'].iloc[idx]
                is_red_prev = df['close'].iloc[idx_prev] < df['open'].iloc[idx_prev]
                breaks_low = df['close'].iloc[idx] < df['low'].iloc[idx_prev]
                
                if not (is_red_current and is_red_prev and breaks_low):
                    accel_bearish = False

            trigger_short = accel_bullish and (df['close'].iloc[curr] <= df['open'].iloc[curr] or df['close'].iloc[curr] <= df['high'].iloc[curr-1])
            trigger_long = accel_bearish and (df['close'].iloc[curr] >= df['open'].iloc[curr] or df['close'].iloc[curr] >= df['low'].iloc[curr-1])

            if trigger_short or trigger_long:
                data_str = data_candela_it.strftime("%d/%m/%Y %H:%M")
                chiave_univoca = f"{tf_name}_{data_str}"

                if chiave_univoca not in segnali_inviati_storico:
                    segnali_inviati_storico.add(chiave_univoca)

                    prezzo_chiusura = df['close'].iloc[curr]
                    
                    if trigger_short:
                        tipo_segnale = "🔴 SHORT (Resistenza / Wick Block Superiore)"
                    else:
                        tipo_segnale = "🟢 LONG (Supporto / Wick Block Inferiore)"

                    if curr == len(df) - 1:
                        stato_tempo = "🚀 *SEGNALE ATTUALE (Fresco in tempo reale!)*"
                    else:
                        candele_fa = (len(df) - 1) - curr
                        stato_tempo = f"⏳ *SEGNALE PASSATO DELLE ULTIME 24H* ({candele_fa} candele fa)"

                    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                    messaggio = (
                        f"📊 *WICK BLOCK - {tf_name}*\n\n"
                        f"{stato_tempo}\n\n"
                        f"🗓 **Data/Ora (Italia):** {data_str}\n"
                        f"🏆 **Asset:** {SYMBOL} ({EXCHANGE})\n"
                        f"🎯 **Segnale:** {tipo_segnale}\n"
                        f"💵 **Prezzo:** {prezzo_chiusura:.2f}$"
                    )
                    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": messaggio, "parse_mode": "Markdown"}
                    
                    try:
                        requests.post(url, data=payload)
                        print(f"✅ Inviato segnale ({tf_name} - {data_str}) su Telegram!")
                        time.sleep(1)
                    except Exception as e:
                        print(f"❌ Errore API Telegram: {e}")

# ==========================================
# --- 3. MOTORE IN BACKGROUND ---
# ==========================================
def run_bot():
    print(f"🤖 BOT WICK BLOCK (ORA ITALIANA) AVVIATO SU {SYMBOL}!")
    tv = TvDatafeed()
    while True:
        try:
            for tf_obj, tf_name in TIMEFRAMES:
                analizza_tf(tv, tf_obj, tf_name)
                time.sleep(2)
        except Exception as e:
            print(f"❌ Errore nel ciclo principale: {e}")
        
        print("\n⏳ Attesa di 5 minuti prima del prossimo controllo live...\n")
        time.sleep(300)

if __name__ == '__main__':
    t = threading.Thread(target=run_bot)
    t.start()
    app.run(host='0.0.0.0', port=10000)
