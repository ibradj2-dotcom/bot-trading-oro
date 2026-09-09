import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
import time
import threading
from flask import Flask

# ==========================================
# --- WEB SERVER PER RENDER ---
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Il Bot Wick Block (Real-Time Intrabar) è online!"

# ==========================================
# --- 1. CONFIGURAZIONE TELEGRAM & TRADING ---
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

TZ_ROMA = ZoneInfo("Europe/Rome")

# Memorizza l'orario della candela per cui è già stato spedito l'alert
candele_gia_avvisate = {'1 Ora': None, '15 Minuti': None, '5 Minuti': None}

# ==========================================
# --- 2. LOGICA DI SCANSIONE INTRABAR ---
# ==========================================
def analizza_tf(tv, tf_obj, tf_name):
    try:
        df = tv.get_hist(symbol=SYMBOL, exchange=EXCHANGE, interval=tf_obj, n_bars=30)
    except Exception as e:
        print(f"[{datetime.now(TZ_ROMA).strftime('%H:%M:%S')}] ❌ Errore connessione {tf_name}: {e}")
        return

    if df is not None and not df.empty and len(df) > NUM_ACCEL + 2:
        # Indice della candela viva in corso di formazione
        curr = len(df) - 1
        data_candela = df.index[curr]

        # Conversione timestamp a fuso orario di Roma
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

        # Evita spam: massimo un messaggio per la stessa candela in corso
        if candele_gia_avvisate[tf_name] == data_str:
            return

        # Calcolo accelerazione sulle candele chiuse precedenti
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

        # Verifica trigger sul prezzo live della candela aperta
        prezzo_live = df['close'].iloc[curr]
        open_live = df['open'].iloc[curr]
        high_prev = df['high'].iloc[curr - 1]
        low_prev = df['low'].iloc[curr - 1]

        trigger_short = accel_bullish and (prezzo_live <= open_live or prezzo_live <= high_prev)
        trigger_long = accel_bearish and (prezzo_live >= open_live or prezzo_live >= low_prev)

        if trigger_short or trigger_long:
            candele_gia_avvisate[tf_name] = data_str

            if trigger_short:
                tipo_segnale = "🔴 SHORT (Wick Block Superiore)"
            else:
                tipo_segnale = "🟢 LONG (Wick Block Inferiore)"

            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            messaggio = (
                f"⚡ *SEGNALE REAL-TIME (CANDELA IN CORSO) - {tf_name}*\n\n"
                f"🚨 *TRIGGER VERIFICATO SUL PREZZO ATTUALE*\n\n"
                f"🗓 **Inizio Candela:** {data_str}\n"
                f"🏆 **Asset:** {SYMBOL} ({EXCHANGE})\n"
                f"🎯 **Segnale:** {tipo_segnale}\n"
                f"💵 **Prezzo al tocco:** {prezzo_live:.2f}$"
            )
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": messaggio, "parse_mode": "Markdown"}

            try:
                requests.post(url, data=payload, timeout=10)
                print(f"[{datetime.now(TZ_ROMA).strftime('%H:%M:%S')}] 🚀 Inviato segnale istantaneo ({tf_name}) su Telegram!")
            except Exception as e:
                print(f"❌ Errore invio Telegram: {e}")

# ==========================================
# --- 3. CICLO DI ESECUZIONE (30 SECONDI) ---
# ==========================================
def run_bot():
    print(f"🤖 BOT REAL-TIME AVVIATO: scansione {SYMBOL} ogni 30 secondi.")
    tv = TvDatafeed()
    while True:
        try:
            for tf_obj, tf_name in TIMEFRAMES:
                analizza_tf(tv, tf_obj, tf_name)
                time.sleep(1)
        except Exception as e:
            print(f"❌ Errore nel ciclo di scansione: {e}")

        time.sleep(30)

if __name__ == '__main__':
    t = threading.Thread(target=run_bot)
    t.start()
    app.run(host='0.0.0.0', port=10000)
