import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import requests
from datetime import datetime
import time
import threading
from flask import Flask

# ==========================================
# --- FINTO SITO WEB PER INGANNARE RENDER ---
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Il Bot di Trading è online e sta funzionando!"

# ==========================================
# --- 1. IMPOSTAZIONI TELEGRAM ---
# ==========================================
TELEGRAM_TOKEN = 'IL_TUO_TOKEN_BOT_QUI'
TELEGRAM_CHAT_ID = 'IL_TUO_CHAT_ID_QUI'

SYMBOL = 'XAUUSD'
EXCHANGE = 'OANDA' 
NUM_ACCEL = 1

TIMEFRAMES = [
    (Interval.in_1_hour, '1 Ora'),
    (Interval.in_15_minute, '15 Minuti'),
    (Interval.in_5_minute, '5 Minuti')
]

ultimi_segnali_inviati = {'1 Ora': None, '15 Minuti': None, '5 Minuti': None}

def analizza_tf(tv, tf_obj, tf_name):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Analisi {SYMBOL} su {tf_name}...")
    try:
        df = tv.get_hist(symbol=SYMBOL, exchange=EXCHANGE, interval=tf_obj, n_bars=500)
    except Exception as e:
        print(f"❌ Errore di connessione su {tf_name}: {e}")
        return

    if df is not None and not df.empty:
        ultimo_segnale_idx = -1 
        data_ultimo_segnale = ""
        tipo_segnale = ""
        prezzo_chiusura = 0

        for curr in range(NUM_ACCEL + 1, len(df)):
            accel_bullish = True
            accel_bearish = True

            for j in range(1, NUM_ACCEL + 1):
                idx = curr - j
                idx_prev = curr - j - 1
                if df['close'].iloc[idx] <= df['open'].iloc[idx] or df['close'].iloc[idx] <= df['high'].iloc[idx_prev]:
                    accel_bullish = False
                if df['close'].iloc[idx] >= df['open'].iloc[idx] or df['close'].iloc[idx] >= df['low'].iloc[idx_prev]:
                    accel_bearish = False

            trigger_short = accel_bullish and (df['close'].iloc[curr] <= df['open'].iloc[curr] or df['close'].iloc[curr] <= df['high'].iloc[curr-1])
            trigger_long = accel_bearish and (df['close'].iloc[curr] >= df['open'].iloc[curr] or df['close'].iloc[curr] >= df['low'].iloc[curr-1])

            if trigger_short:
                ultimo_segnale_idx = curr
                data_ultimo_segnale = df.index[curr].strftime("%d/%m/%Y %H:%M")
                tipo_segnale = "🔴 SHORT (Resistenza)"
                prezzo_chiusura = df['close'].iloc[curr]

            if trigger_long:
                ultimo_segnale_idx = curr
                data_ultimo_segnale = df.index[curr].strftime("%d/%m/%Y %H:%M")
                tipo_segnale = "🟢 LONG (Supporto)"
                prezzo_chiusura = df['close'].iloc[curr]

        if ultimo_segnale_idx != -1:
            if ultimi_segnali_inviati[tf_name] == data_ultimo_segnale:
                return

            ultimi_segnali_inviati[tf_name] = data_ultimo_segnale

            if ultimo_segnale_idx == len(df) - 1:
                stato_tempo = "🚀 *SEGNALE ATTUALE (Fresco!)*"
            else:
                candele_fa = (len(df) - 1) - ultimo_segnale_idx
                stato_tempo = f"⏳ *SEGNALE PASSATO* (Avvenuto {candele_fa} candele fa)"
            
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            messaggio = f"🚨 *WICK BLOCK - {tf_name}*\n\n{stato_tempo}\n\n🗓 **Data/Ora:** {data_ultimo_segnale}\n🏆 **Asset:** {SYMBOL} ({EXCHANGE})\n🎯 **Direzione:** {tipo_segnale}\n💵 **Prezzo chiusura:** {prezzo_chiusura:.2f}$"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": messaggio, "parse_mode": "Markdown"}
            
            try:
                requests.post(url, data=payload)
                print(f"✅ Inviato segnale {tf_name} su Telegram!")
            except Exception as e:
                print(f"❌ Errore API: {e}")

# ==========================================
# --- 3. MOTORE DEL BOT IN BACKGROUND ---
# ==========================================
def run_bot():
    print(f"🤖 BOT AVVIATO. Monitoraggio continuo su {SYMBOL} iniziato!")
    tv = TvDatafeed()
    while True:
        try:
            for tf_obj, tf_name in TIMEFRAMES:
                analizza_tf(tv, tf_obj, tf_name)
                time.sleep(2)
        except Exception as e:
            print(f"❌ Errore nel ciclo principale: {e}")
        time.sleep(300)

if __name__ == '__main__':
    # Avvia il bot di trading su un binario separato
    t = threading.Thread(target=run_bot)
    t.start()
    
    # Avvia il finto sito web richiesto da Render
    app.run(host='0.0.0.0', port=10000)
