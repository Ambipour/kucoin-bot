import os
import logging
from flask import Flask, request, jsonify
import requests
from kucoin.client import Client
from kucoin.exceptions import KucoinAPIException, KucoinResponseException

# Configurar logging a nivel INFO para mostrar mensajes informativos en consola
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# Leer credenciales de KuCoin y Telegram desde variables de entorno
KUCOIN_API_KEY = os.environ.get('KUCOIN_API_KEY')
KUCOIN_API_SECRET = os.environ.get('KUCOIN_API_SECRET')
KUCOIN_API_PASSPHRASE = os.environ.get('KUCOIN_API_PASSPHRASE')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Verificar que todas las variables de entorno requeridas estén definidas
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

# Inicializar el cliente de la API de KuCoin
try:
    kucoin_client = Client(KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE)
    logging.info('Cliente de KuCoin inicializado correctamente.')
except Exception as e:
    logging.error(f'Error al inicializar el cliente de KuCoin: {e}')
    raise

# Función auxiliar para enviar mensajes de texto a Telegram
def send_telegram_message(text: str):
    """Envía un mensaje de texto al chat de Telegram configurado."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error('Credenciales de Telegram no configuradas; no se puede enviar el mensaje.')
        return
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    params = {'chat_id': TELEGRAM_CHAT_ID, 'text': text}
    try:
        resp = requests.get(url, params=params)
        if resp.status_code != 200:
            logging.error(f'Error al enviar mensaje a Telegram. Código HTTP {resp.status_code}: {resp.text}')
        else:
            data = resp.json()
            if not data.get('ok'):
                # La API de Telegram pudo responder 200 OK pero con ok=False (error en el envío)
                logging.error(f'La API de Telegram devolvió un error: {data}')
            else:
                logging.info(f'Mensaje enviado a Telegram: {text}')
    except Exception as e:
        logging.error(f'Error de conexión al enviar mensaje a Telegram: {e}')

# Crear la aplicación Flask
app = Flask(__name__)

# Enviar un mensaje a Telegram al arrancar, indicando que el bot está activo
inicio_msg = '🤖 Bot de trading de KuCoin activo y esperando señales.'
logging.info('Enviando mensaje de inicio a Telegram...')
send_telegram_message(inicio_msg)

@app.route('/webhook-eth', methods=['POST'])
def webhook_eth():
    """Maneja las señales de trading (BUY o SELL) recibidas via webhook."""
    # Intentar obtener el JSON de la petición
    try:
        data = request.get_json(force=True)
    except Exception as e:
        logging.error(f'Error al leer JSON de la petición: {e}')
        return jsonify({'error': 'Formato de datos inválido'}), 400

    if not data:
        logging.error('Petición POST /webhook-eth recibida sin cuerpo JSON.')
        return jsonify({'error': 'Solicitud sin datos'}), 400

    # Determinar la acción de la señal (esperada 'BUY' o 'SELL')
    action = None
    if isinstance(data, dict):
        # Aceptar posibles claves de acción en el JSON
        action = data.get('action') or data.get('signal') or data.get('type')
    if not action:
        logging.error('JSON de webhook no contiene campo de acción (BUY/SELL).')
        return jsonify({'error': 'No se especificó la acción (BUY o SELL)'}), 400

    action = str(action).strip().upper()
    if action not in ('BUY', 'SELL'):
        logging.error(f'Acción inválida en la señal: {action}')
        return jsonify({'error': 'Acción inválida, debe ser BUY o SELL'}), 400

    logging.info(f'Señal recibida: {action}')
    tipo_op = 'COMPRA' if action == 'BUY' else 'VENTA'
    telegram_msg = ''

    # Intentar realizar la operación en KuCoin
    try:
        if action == 'BUY':
            # Obtener 100% del saldo disponible de USDT para comprar ETH
            accounts = kucoin_client.get_accounts('USDT', 'trade')
            usdt_balance = float(accounts[0]['available']) if accounts and accounts[0].get('available') else 0.0
            if usdt_balance <= 0:
                raise Exception('Saldo USDT insuficiente para ejecutar la compra.')
            # Ejecutar orden de mercado de compra (usar todo el USDT disponible)
            order = kucoin_client.create_market_order('ETH-USDT', 'buy', funds=str(usdt_balance))
        else:  # SELL
            # Obtener 100% del saldo disponible de ETH para vender
            accounts = kucoin_client.get_accounts('ETH', 'trade')
            eth_balance = float(accounts[0]['available']) if accounts and accounts[0].get('available') else 0.0
            if eth_balance <= 0:
                raise Exception('Saldo ETH insuficiente para ejecutar la venta.')
            # Ejecutar orden de mercado de venta (vender todo el ETH disponible)
            order = kucoin_client.create_market_order('ETH-USDT', 'sell', size=str(eth_balance))

        # Si la orden se colocó exitosamente, registrar respuesta
        logging.info(f'Orden de {action} enviada. Respuesta de KuCoin: {order}')
        telegram_msg = f'✅ {tipo_op} ejecutada con éxito. Respuesta KuCoin: {order}'
    except (KucoinAPIException, KucoinResponseException) as e:
        # Error devuelto por la API de KuCoin
        logging.error(f'Error de KuCoin en la {tipo_op}: {e}')
        telegram_msg = f'❌ Error al realizar la {tipo_op}: {e}'
    except Exception as e:
        # Cualquier otro error (ej. saldo insuficiente u otro fallo)
        logging.error(f'Error al procesar la operación de {tipo_op}: {e}')
        telegram_msg = f'❌ No se pudo completar la {tipo_op}: {e}'

    # Enviar notificación a Telegram sobre el resultado de la señal
    send_telegram_message(telegram_msg)
    # Responder al webhook con un mensaje de confirmación (siempre 200 OK)
    return jsonify({'signal': action, 'result': telegram_msg}), 200

# Iniciar la aplicación Flask en puerto 5000 (host 0.0.0.0) para producción
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
