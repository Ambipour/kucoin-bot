import os
import time
import hmac
import hashlib
import base64
import json
import requests
from flask import Flask, request, jsonify

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
KUCOIN_API_KEY = os.getenv("KUCOIN_API_KEY")
KUCOIN_API_SECRET = os.getenv("KUCOIN_API_SECRET")
KUCOIN_API_PASSPHRASE = os.getenv("KUCOIN_API_PASSPHRASE")

BASE_URL = "https://api.kucoin.com"
SYMBOL = "ETH-USDT"

app = Flask(__name__)

def enviar_mensaje_telegram(texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": texto}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"❌ Error enviando a Telegram: {e}")

def firmar(endpoint, method, body, timestamp):
    str_to_sign = str(timestamp) + method + endpoint + body
    return base64.b64encode(
        hmac.new(KUCOIN_API_SECRET.encode(), str_to_sign.encode(), hashlib.sha256).digest()
    ).decode()

def obtener_saldo(asset):
    endpoint = "/api/v1/accounts"
    url = BASE_URL + endpoint
    timestamp = str(int(time.time() * 1000))
    headers = {
        "KC-API-KEY": KUCOIN_API_KEY,
        "KC-API-SIGN": firmar(endpoint, "GET", "", timestamp),
        "KC-API-TIMESTAMP": timestamp,
        "KC-API-PASSPHRASE": KUCOIN_API_PASSPHRASE,
        "KC-API-KEY-VERSION": "2",
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        cuentas = response.json()["data"]
        for cuenta in cuentas:
            if cuenta["currency"] == asset and cuenta["type"] == "trade":
                return float(cuenta["available"])
    return 0.0

def crear_orden(accion, cantidad):
    endpoint = "/api/v1/orders"
    url = BASE_URL + endpoint
    timestamp = str(int(time.time() * 1000))
    
    body = {
        "clientOid": str(int(time.time() * 1000)),
        "side": accion.lower(),
        "symbol": SYMBOL,
        "type": "market"
    }

    if accion.upper() == "BUY":
        body["funds"] = str(cantidad)
    elif accion.upper() == "SELL":
        body["size"] = str(cantidad)

    body_str = json.dumps(body)
    headers = {
        "KC-API-KEY": KUCOIN_API_KEY,
        "KC-API-SIGN": firmar(endpoint, "POST", body_str, timestamp),
        "KC-API-TIMESTAMP": timestamp,
        "KC-API-PASSPHRASE": KUCOIN_API_PASSPHRASE,
        "KC-API-KEY-VERSION": "2",
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, data=body_str)
    print("📤 ORDEN ENVIADA:", response.status_code, response.text)
    return response.json()

@app.route("/webhook-eth", methods=["POST"])
def recibir_alerta_eth():
    data = request.json
    print(f"📨 Alerta recibida (ETH): {data}")
    accion = data.get("action", "").upper()
    try:
        if accion == "BUY":
            saldo = obtener_saldo("USDT")
            if saldo <= 0:
                enviar_mensaje_telegram("❌ Saldo insuficiente en USDT para comprar ETH.")
                return jsonify({"error": "Saldo insuficiente"}), 400
            crear_orden("BUY", saldo)
            enviar_mensaje_telegram(f"🟢 COMPRA ejecutada de ETH por ~{saldo} USDT")

        elif accion == "SELL":
            saldo = obtener_saldo("ETH")
            if saldo <= 0:
                enviar_mensaje_telegram("❌ Saldo insuficiente en ETH para vender.")
                return jsonify({"error": "Saldo insuficiente"}), 400
            crear_orden("SELL", saldo)
            enviar_mensaje_telegram(f"🔴 VENTA ejecutada de {saldo} ETH")

        else:
            enviar_mensaje_telegram("⚠️ Acción desconocida recibida en ETH")
        return jsonify({"status": "ok"})

    except Exception as e:
        print(f"❌ ERROR: {e}")
        enviar_mensaje_telegram(f"❌ Error ejecutando orden:\n{e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    enviar_mensaje_telegram("🤖 Bot ETH KuCoin activo y escuchando señales...")
    app.run(host="0.0.0.0", port=5000)

