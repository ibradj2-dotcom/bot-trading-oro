import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import requests
from datetime import datetime, timedelta
import time
import threading
from flask import Flask

# ==========================================
# --- FINTO SITO WEB PER INGANNARE RENDER ---
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Il Bot Wick Block (Passato + Futuro) è online!"

# ==========================================
# --- 1. IMPOSTAZIONI TELEGRAM E PARAMETRI ---
# ==========================================
TELEGRAM_TOKEN = '8996771491:AAFi3wBZmIMqtMwELuCdGID3lNMd7NOHV1c'
TELEGRAM_CHAT_ID = '5241768648'

SYMBOL = 'XAUUSD'
EXCHANGE = 'OANDA' 
NUM_ACCEL = 3

TIMEFRAMES = [
    (Interval.in_1_hour, '1 Ora'),
    (Interval.in_15_minute, '15 Minuti'),
    (Interval.in_5_minute, '5 Minuti')
]

# Memoria cronologica: memorizza le chiavi uniche (TF + Data/Ora) dei segnali già inviati
segnali_inviati_storico = set()

# ==========================================
# --- 2. FUNZIONE DI ANALISI (Passato 24h + Futuro) ---
# ==========================================
def analizza_tf(tv, tf_obj, tf_name):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Analisi {SYMBOL} su {tf_name}...")
    try:
        # Scarichiamo un numero sufficiente di barre per coprire almeno l'ultimo giorno e oltre
        df = tv.get_hist(symbol=SYMBOL, exchange=EXCHANGE, interval=tf_obj, n_bars=500)
    except Exception as e:
        print(f"❌ Errore di connessione su {tf_name}: {e}")
        return

    if df is not None and not df.empty:
        # Calcoliamo il limite temporale di 24 ore fa
        limite_24h = datetime.now() - timedelta(hours=24)

        # Logica Pine Script convertita in Python
        for curr in range(NUM_ACCEL + 1, len(df)):
            data_candela = df.index[curr]
            
            # FILTRO: Analizziamo solo le candele dall'ultimo giorno a oggi (e futuro)
            # (Se il dataframe usa date naive o aware, confrontiamo in sicurezza)
            try:
                if isinstance(data_candela, pd.Timestamp) and data_candela.tz is not None:
                    limite_24h_tz = pd.Timestamp(limite_24h, tz=data_candela.tz)
                else:
                    limite_24h_tz = limite_24h
                
                if data_candela < limite_24h_tz:
                    continue
            except:
                pass

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
                data_str = data_candela.strftime("%d/%m/%Y %H:%M")
                chiave_univoca = f"{tf_name}_{data_str}"

                # Se questo specifico segnale non è stato mai inviato, procediamo
                if chiave_univoca not in segnali_inviati_storico:
                    segnali_inviati_storico.add(chiave_univoca)

                    prezzo_chiusura = df['close'].iloc[curr]
                    
                    if trigger_short:
                        tipo_segnale = "🔴 SHORT (Resistenza / Wick Block Superiore)"
                    else:
                        tipo_segnale = "🟢 LONG (Supporto / Wick Block Inferiore)"

                    # Capiamo se è una candela attuale (futuro/live) o del passato (ultime 24h)
                    if curr == len(df) - 1:
                        stato_tempo = "🚀 *SEGNALE ATTUALE (Fresco in tempo reale!)*"
                    else:
                        candele_fa = (len(df) - 1) - curr
                        stato_tempo = f"⏳ *SEGNALE PASSATO DELLE ULTIME 24H* ({candele_fa} candele fa)"

                    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                    messaggio = (
                        f"📊 *WICK BLOCK - {tf_name}*\n\n"
                        f"{stato_tempo}\n\n"
                        f"🗓 **Data/Ora:** {data_str}\n"
                        f"🏆 **Asset:** {SYMBOL} ({EXCHANGE})\n"
                        f"🎯 **Segnale:** {tipo_segnale}\n"
                        f"💵 **Prezzo:** {prezzo_chiusura:.2f}$"
                    )
                    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": messaggio, "parse_mode": "Markdown"}
                    
                    try:
                        requests.post(url, data=payload)
                        print(f"✅ Inviato segnale ({tf_name} - {data_str}) su Telegram!")
                        time.sleep(1) # Pausa breve tra un invio e l'altro per non intasare Telegram
                    except Exception as e:
                        print(f"❌ Errore API Telegram: {e}")

# ==========================================
# --- 3. MOTORE IN BACKGROUND ---
# ==========================================
def run_bot():
    print(f"🤖 BOT WICK BLOCK (24H PASSATO + FUTURO) AVVIATO SU {SYMBOL}!")
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
