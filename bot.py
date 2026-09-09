import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import requests
from datetime import datetime
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
    return "✅ Il Bot Wick Block (Solo Segnali Live - Controllo 1 Minuto) è online!"

# ==========================================
# --- 1. IMPOSTAZIONI TELEGRAM E PARAMETRI ---
# ==========================================
TELEGRAM_TOKEN = '8996771491:AAFi3wBZmIMqtMwELuCdGID3lNMd7NOHV1c'
TELEGRAM_CHAT_ID = '-1003760907517'

SYMBOL = 'XAUUSD'
EXCHANGE = 'OANDA' 
NUM_ACCEL = 3

TIMEFRAMES = [
    (Interval.in_1_hour, '1 Ora'),
    (Interval.in_15_minute, '15 Minuti'),
    (Interval.in_5_minute, '5 Minuti')
]

# Fuso orario di Roma
TZ_ROMA = ZoneInfo("Europe/Rome")

# Memoria dell'ultimo timestamp processato per ciascun timeframe (evita duplicati e scarta il passato)
ultimi_timestamp_processati = {'1 Ora': None, '15 Minuti': None, '5 Minuti': None}

# ==========================================
# --- 2. FUNZIONE DI ANALISI SOLO LIVE ---
# ==========================================
def analizza_tf(tv, tf_obj, tf_name):
    try:
        # Scarichiamo solo le ultime barre necessarie per il calcolo dell'accelerazione
        df = tv.get_hist(symbol=SYMBOL, exchange=EXCHANGE, interval=tf_obj, n_bars=50)
    except Exception as e:
        print(f"[{datetime.now(TZ_ROMA).strftime('%H:%M:%S')}] ❌ Errore connessione {tf_name}: {e}")
        return

    if df is not None and not df.empty and len(df) > NUM_ACCEL + 2:
        # La candela chiusa più recente è l'ultima o la penultima a seconda del feed real-time.
        # Analizziamo la candela appena completata (indice -2 o -1 se la barra corrente è già consolidata)
        curr = len(df) - 1
        data_candela = df.index[curr]

        # Conversione fuso orario a Europe/Rome
        try:
            if isinstance(data_candela, pd.Timestamp):
                if data_candela.tz is None:
                    data_candela_it = data_candela.tz_localize("UTC").tz_convert(TZ_ROMA)
                else:
                    data_candela_it = data_candela.tz_convert(TZ_ROMA)
            else:
                data_candela_it = pd.to_datetime(data_candela).tz_localize("UTC").tz_convert(TZ_ROMA)
        except Exception:
            data_candela_it = pd.to_datetime(data_candela)

        data_str = data_candela_it.strftime("%d/%m/%Y %H:%M")

        # Se è il primo avvio del bot per questo timeframe, salviamo l'orario e NON mandiamo vecchi segnali
        if ultimi_timestamp_processati[tf_name] is None:
            ultimi_timestamp_processati[tf_name] = data_str
            print(f"[{datetime.now(TZ_ROMA).strftime('%H:%M:%S')}] 📌 Inizializzato {tf_name} su candela: {data_str} (nessun segnale passato inviato)")
            return

        # Se questa candela è già stata analizzata, aspettiamo la prossima
        if ultimi_timestamp_processati[tf_name] == data_str:
            return

        # Calcolo Accelerazione Pura (Pine Script) sulle barre precedenti
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

        # Trigger su candela corrente
        trigger_short = accel_bullish and (df['close'].iloc[curr] <= df['open'].iloc[curr] or df['close'].iloc[curr] <= df['high'].iloc[curr-1])
        trigger_long = accel_bearish and (df['close'].iloc[curr] >= df['open'].iloc[curr] or df['close'].iloc[curr] >= df['low'].iloc[curr-1])

        # Aggiorniamo sempre il timestamp visto per non rieseguire sulla stessa candela
        ultimi_timestamp_processati[tf_name] = data_str

        if trigger_short or trigger_long:
            prezzo_chiusura = df['close'].iloc[curr]
            
            if trigger_short:
                tipo_segnale = "🔴 SHORT (Resistenza / Wick Block Superiore)"
            else:
                tipo_segnale = "🟢 LONG (Supporto / Wick Block Inferiore)"

            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            messaggio = (
                f"⚡ *NUOVO SEGNALE LIVE - {tf_name}*\n\n"
                f"🗓 **Data/Ora:** {data_str}\n"
                f"🏆 **Asset:** {SYMBOL} ({EXCHANGE})\n"
                f"🎯 **Segnale:** {tipo_segnale}\n"
                f"💵 **Prezzo:** {prezzo_chiusura:.2f}$"
            )
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": messaggio, "parse_mode": "Markdown"}
            
            try:
                requests.post(url, data=payload, timeout=10)
                print(f"[{datetime.now(TZ_ROMA).strftime('%H:%M:%S')}] 🚀 Inviato segnale FRESCO ({tf_name}) su Telegram!")
            except Exception as e:
                print(f"❌ Errore invio Telegram: {e}")

# ==========================================
# --- 3. MOTORE IN BACKGROUND ---
# ==========================================
def run_bot():
    print(f"🤖 BOT AVVIATO: Monitoraggio {SYMBOL} ({EXCHANGE}) ogni 60 secondi!")
    tv = TvDatafeed()
    while True:
        try:
            for tf_obj, tf_name in TIMEFRAMES:
                analizza_tf(tv, tf_obj, tf_name)
                time.sleep(1)  # Breve pausa di rispetto tra le richieste API
        except Exception as e:
            print(f"❌ Errore nel ciclo di scansione: {e}")
        
        # Scansione ogni 60 secondi
        time.sleep(60)

if __name__ == '__main__':
    t = threading.Thread(target=run_bot)
    t.start()
    app.run(host='0.0.0.0', port=10000)
