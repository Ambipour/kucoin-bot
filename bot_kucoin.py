import os
import logging
from flask import Flask, request, jsonify
import requests
from kucoin.client import Client
from kucoin.exceptions import KucoinAPIException, KucoinRequestException

# Configurar logging a nivel INFO
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# Leer credenciales de entorno
KUCOIN_API_KEY = os.environ.get('KUCOIN_API_KEY')
KUCOIN_API_SECRET = os.environ.get('KUCOIN_API_SECRET')
KUCOIN_API_PASSPHRASE = os.environ.get('KUCOIN_API_PASSPHRASE')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Verificar variables necesarias
required_vars = {
    'KUCOIN_API_KEY': KUCOIN_API_KEY,
    'KUCOIN_API_SECRET': KUCOIN_API_SECRET,
    'KUCOIN_API_PASSPHRASE': KUCOIN_API_PASSPHRASE,
    'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
    'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
}
missing = [name for name, val in required_vars.items() if not val]
if missing:
    for name in missing:
        logging.error(f'Falta la variable de entorno {name}')
    raise SystemExit('Error: Variables de entorno requeridas no definidas. Abortando.')

# Inicializar KuCoin
try:
    kucoin_client = Client(KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE)
    logging.info('Cliente de KuCoin inicializado correctamente.')
except Exception as e:
    logging.error(f'Error al inicializar KuCoin: {e}')
    raise

# Enviar a Telegram
def send_telegram_message(text):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    params = {'chat_id': TELEGRAM_CHAT_ID, 'text': text}
    try:
        resp = requests.get(url, params=params)
        if resp.status_code != 200 or not resp.json().get('ok'):
            logging.error(f'Fallo Telegram: {resp.status_code} {resp.text}')
        else:
            logging.info(f'Mensaje Telegram enviado: {text}')
    except Exception as e:
        logging.error(f'Error enviando Telegram: {e}')

# Crear app
app = Flask(__name__)

# Aviso de inicio
inicio_msg = '🤖 Bot de trading de KuCoin activo y esperando señales.'
logging.info('Enviando mensaje de inicio a Telegram...')
send_telegram_message(inicio_msg)

@app.route('/webhook-eth', methods=['POST'])
def webhook_eth():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        logging.error(f'JSON invalido: {e}')
        return jsonify({'error': 'Formato invalido'}), 400

    if not data:
        return jsonify({'error': 'Solicitud sin datos'}), 400

    action = data.get('action') or data.get('signal') or data.get('type')
    if not action:
        return jsonify({'error': 'Acción no especificada'}), 400

    action = str(action).strip().upper()
    if action not in ('BUY', 'SELL'):
        return jsonify({'error': 'Acción inválida'}), 400

    logging.info(f'Señal recibida: {action}')
    tipo_op = 'COMPRA' if action == 'BUY' else 'VENTA'
    telegram_msg = ''

    try:
        if action == 'BUY':
            accounts = kucoin_client.get_accounts('USDT', 'trade')
            usdt_balance = float(accounts[0]['available']) if accounts and accounts[0].get('available') else 0.0
            if usdt_balance <= 0:
                raise Exception('Saldo USDT insuficiente.')
            amount = round(usdt_balance, 2)
            order = kucoin_client.create_market_order('ETH-USDT', 'buy', funds=str(amount))

        else:
            accounts = kucoin_client.get_accounts('ETH', 'trade')
            eth_balance = float(accounts[0]['available']) if accounts and accounts[0].get('available') else 0.0
            if eth_balance <= 0:
                raise Exception('Saldo ETH insuficiente.')
            from decimal import Decimal, ROUND_DOWN

# Redondear a 4 decimales
        eth_amount = Decimal(str(eth_balance)).quantize(Decimal('0.0001'), rounding=ROUND_DOWN)
        order = kucoin_client.create_market_order('ETH-USDT', 'sell', size=str(eth_amount))


        logging.info(f'Orden {action} ejecutada. Respuesta: {order}')
        telegram_msg = f'✅ {tipo_op} ejecutada con éxito. Respuesta: {order}'
    except (KucoinAPIException, KucoinRequestException) as e:
        logging.error(f'Error KuCoin en {tipo_op}: {e}')
        telegram_msg = f'❌ Error en {tipo_op}: {e}'
    except Exception as e:
        logging.error(f'Fallo en {tipo_op}: {e}')
        telegram_msg = f'❌ No se pudo completar la {tipo_op}: {e}'

    send_telegram_message(telegram_msg)
    return jsonify({'signal': action, 'result': telegram_msg}), 200

# Iniciar servidor
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

