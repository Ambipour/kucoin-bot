import os
import logging
from flask import Flask, request, jsonify
import requests
from kucoin.client import Client
from kucoin.exceptions import KucoinAPIException, KucoinRequestException
from decimal import Decimal, ROUND_DOWN

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# Leer variables de entorno
KUCOIN_API_KEY = os.getenv('KUCOIN_API_KEY')
KUCOIN_API_SECRET = os.getenv('KUCOIN_API_SECRET')
KUCOIN_API_PASSPHRASE = os.getenv('KUCOIN_API_PASSPHRASE')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Verificar que todas existan
for var_name, var in {
    'KUCOIN_API_KEY': KUCOIN_API_KEY,
    'KUCOIN_API_SECRET': KUCOIN_API_SECRET,
    'KUCOIN_API_PASSPHRASE': KUCOIN_API_PASSPHRASE,
    'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
    'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
}.items():
    if not var:
        raise Exception(f'❌ Falta la variable de entorno: {var_name}')

# Inicializar cliente KuCoin
try:
    kucoin_client = Client(KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE)
    logging.info('✅ Cliente de KuCoin inicializado correctamente.')
except Exception as e:
    logging.error(f'❌ Error al inicializar KuCoin: {e}')
    raise

# Enviar mensaje a Telegram
def enviar_mensaje_telegram(texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": texto}
    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            logging.error(f'❌ Telegram error {response.status_code}: {response.text}')
    except Exception as e:
        logging.error(f'❌ Error enviando Telegram: {e}')

# Flask app
app = Flask(__name__)

# Al iniciar
enviar_mensaje_telegram("🤖 Bot de trading de KuCoin activo y esperando señales.")

@app.route('/webhook-eth', methods=['POST'])
def webhook_eth():
    try:
        data = request.get_json(force=True)
        logging.info(f'📨 Señal recibida: {data}')
    except Exception:
        return jsonify({'error': 'JSON inválido'}), 400

    action = str(data.get('action', '')).strip().upper()
    if action not in ['BUY', 'SELL']:
        return jsonify({'error': 'Acción inválida'}), 400

    try:
        if action == 'BUY':
            saldo = float(next(acc['available'] for acc in kucoin_client.get_accounts()
                               if acc['currency'] == 'USDT' and acc['type'] == 'trade'))
            if saldo <= 0:
                raise Exception('Saldo USDT insuficiente.')

            amount = Decimal(str(saldo)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            orden = kucoin_client.create_market_order('ETH-USDT', 'buy', funds=str(amount))

        else:
            saldo = float(next(acc['available'] for acc in kucoin_client.get_accounts()
                               if acc['currency'] == 'ETH' and acc['type'] == 'trade'))
            if saldo <= 0:
                raise Exception('Saldo ETH insuficiente.')

            tamaño = Decimal(str(saldo)).quantize(Decimal('0.0001'), rounding=ROUND_DOWN)
            orden = kucoin_client.create_market_order('ETH-USDT', 'sell', size=str(tamaño))

        texto = f"✅ {action} ejecutada con éxito. Respuesta: {orden}"
        logging.info(texto)

    except Exception as e:
        texto = f"❌ Error en {action}: {e}"
        logging.error(texto)

    enviar_mensaje_telegram(texto)
    return jsonify({'signal': action, 'result': texto}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
