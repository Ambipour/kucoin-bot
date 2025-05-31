import os
import time
import hmac
import hashlib
import signal
import sys
import requests
from flask import Flask, request, jsonify

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
KUCOIN_API_KEY = os.getenv("KUCOIN_API_KEY")
KUCOIN_API_SECRET = os.getenv("KUCOIN_API_SECRET")
KUCOIN_API_PASSPHRASE = os.getenv("KUCOIN_API_PASSPHRASE")

app = Flask(__name__)

def enviar_mensaje_telegram(texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": texto}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"❌ Error enviando a Telegram: {e}")

@app.route("/webhook-eth", methods=["POST"])
def recibir_alerta_eth():
    data = request.json
    print(f"📨 Alerta recibida (ETH): {data}")
    accion = data.get("action", "").upper()
    if accion == "BUY":
        enviar_mensaje_telegram("🟢 Señal de COMPRA detectada para ETH")
    elif accion == "SELL":
        enviar_mensaje_telegram("🔴 Señal de VENTA detectada para ETH")
    else:
        enviar_mensaje_telegram("⚠️ Acción desconocida recibida en ETH")
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    enviar_mensaje_telegram("🤖 Bot ETH KuCoin activo y escuchando señales...")
    app.run(host="0.0.0.0", port=5000)
