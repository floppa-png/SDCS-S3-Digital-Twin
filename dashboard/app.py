import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from twin_core.engine import Engine
from twin_core.config import MODULATIONS
from twin_core.presets import PRESETS, SCENARIO_METADATA

# Configure Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024  # 4 KB payload limit

# Logging with size cap (RotatingFileHandler, 1 MB)
log_dir = os.path.dirname(__file__)
log_file = os.path.join(log_dir, 'app.log')
os.makedirs(log_dir, exist_ok=True)
handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024, backupCount=2)
handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

# Restrict CORS to localhost
ALLOWED_ORIGINS = [
    "http://127.0.0.1:5000",
    "http://localhost:5000"
]

socketio = SocketIO(
    app,
    async_mode='threading',
    cors_allowed_origins=ALLOWED_ORIGINS
)

# Initialize Engine (fast boot, < 1 second)
engine = Engine(fs=1000000)
if os.environ.get('SDCS_MODE') == 'pluto':
    engine.mode = 'pluto'

# Wire engine callbacks to Socket.IO emits
def handle_frame_emit(payload):
    socketio.emit('frame', payload)

def handle_twin_emit(payload):
    socketio.emit('twin', payload)

def handle_config_emit(payload):
    socketio.emit('config', payload)

def handle_event_emit(payload):
    socketio.emit('event', payload)

engine.on_frame_emit = handle_frame_emit
engine.on_twin_emit = handle_twin_emit
engine.on_config_emit = handle_config_emit
engine.on_event_emit = handle_event_emit

# Start engine background loops
engine.start()

import time
BUILD_VERSION = str(int(time.time()))

@app.context_processor
def inject_version():
    return dict(version=BUILD_VERSION)

# --- Middleware: Request validation ---
@app.before_request
def validate_content_type():
    if request.method == 'POST':
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400

# --- REST Endpoints ---

@app.route('/')
def index():
    return render_template('index.html', version=BUILD_VERSION)

@app.route('/api/state', methods=['GET'])
def get_state():
    return jsonify(engine.get_state())

@app.route('/api/dossier', methods=['GET'])
def get_dossier():
    window = request.args.get('window', 'boot')
    return jsonify(engine.get_dossier(window))

@app.route('/api/config', methods=['POST'])
def update_config():
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({'error': 'Malformed or empty JSON body'}), 400
        
    ok, res = engine.update_config(data)
    if not ok:
        return jsonify({'errors': res}), 400
    return jsonify({'status': 'ok', 'config': res})

@app.route('/api/modulation', methods=['POST'])
def set_modulation():
    data = request.get_json(silent=True)
    if not data or 'modulation' not in data:
        return jsonify({'error': 'Missing modulation key'}), 400
        
    mod = str(data['modulation']).upper()
    if mod not in MODULATIONS:
        return jsonify({'error': f'Invalid modulation. Allowed: {MODULATIONS}'}), 400
        
    ok, msg = engine.set_modulation(mod)
    if not ok:
        return jsonify({'error': msg}), 400
    return jsonify({'status': 'ok', 'modulation': mod})

@app.route('/api/apply_best', methods=['POST'])
def apply_best():
    ok, res = engine.apply_best()
    if not ok:
        return jsonify({'status': 'ignored', 'message': res.get('message', 'Not applied')}), 200
    return jsonify({'status': 'ok', 'result': res})

@app.route('/api/randomize', methods=['POST'])
def toggle_randomizer():
    data = request.get_json(silent=True)
    if not data or 'enabled' not in data:
        return jsonify({'error': 'Missing enabled key'}), 400
    engine.randomizer_enabled = bool(data['enabled'])
    engine.log_event("randomizer_toggle", f"Randomizer {'enabled' if engine.randomizer_enabled else 'disabled'}")
    return jsonify({'status': 'ok', 'randomizer': engine.randomizer_enabled})

@app.route('/api/shuffle', methods=['POST'])
def shuffle():
    engine.shuffle_params()
    return jsonify({'status': 'ok', 'config': engine.config.to_dict()})

@app.route('/api/autopilot', methods=['POST'])
def toggle_autopilot():
    data = request.get_json(silent=True) or {}
    if 'enabled' in data:
        engine.autopilot_enabled = bool(data['enabled'])
    else:
        engine.autopilot_enabled = not engine.autopilot_enabled
        
    status_str = 'enabled' if engine.autopilot_enabled else 'disabled'
    engine.log_event("autopilot_toggle", f"Continuous Autopilot {status_str}", {'autopilot': engine.autopilot_enabled})
    socketio.emit('state', engine.get_state())
    return jsonify({'status': 'ok', 'autopilot': engine.autopilot_enabled})

@app.route('/api/preset', methods=['POST'])
def apply_preset():
    data = request.get_json(silent=True)
    if not data or 'name' not in data:
        return jsonify({'error': 'Missing name key'}), 400
    name = str(data['name'])
    if name not in PRESETS:
        return jsonify({'error': f'Invalid preset name. Allowed: {list(PRESETS.keys())}'}), 400
    ok, msg = engine.set_preset(name)
    if not ok:
        return jsonify({'error': msg}), 400
    return jsonify({'status': 'ok', 'preset': name, 'scenario': engine.active_scenario})

@app.route('/api/scenarios', methods=['GET'])
def get_scenarios():
    return jsonify({
        'active': engine.active_scenario,
        'scenarios': SCENARIO_METADATA
    })

@app.route('/api/fdia', methods=['POST'])
def toggle_fdia():
    data = request.get_json(silent=True)
    if not data or 'active' not in data:
        return jsonify({'error': 'Missing active key'}), 400
    active = bool(data['active'])
    ok, msg = engine.set_fdia(active)
    return jsonify({
        'status': 'ok',
        'fdia_active': engine.config.fdia_active,
        'message': msg
    })

@app.route('/api/fdia_random', methods=['POST'])
def toggle_fdia_random():
    data = request.get_json(silent=True)
    if not data or 'enabled' not in data:
        return jsonify({'error': 'Missing enabled key'}), 400
    enabled = bool(data['enabled'])
    ok, msg = engine.set_random_fdia(enabled)
    return jsonify({
        'status': 'ok',
        'random_fdia': engine.random_fdia_enabled,
        'fdia_active': engine.config.fdia_active,
        'message': msg
    })

@app.route('/api/mode', methods=['POST'])
def set_mode():
    data = request.get_json(silent=True)
    if not data or 'mode' not in data:
        return jsonify({'error': 'Missing mode key'}), 400
    mode = str(data['mode']).lower()
    ok, msg = engine.set_mode(mode)
    if not ok:
        return jsonify({'error': msg}), 400
    socketio.emit('state', engine.get_state())
    return jsonify({'status': 'ok', 'mode': mode})

@app.route('/api/reset_stats', methods=['POST'])
def reset_stats():
    engine.reset_stats()
    return jsonify({'status': 'ok'})

# Socket.IO connection event
@socketio.on('connect')
def on_connect():
    # Emit initial state snapshot on client connect
    socketio.emit('state', engine.get_state())

if __name__ == '__main__':
    print("==================================================")
    print("   Starting SDCS Digital Twin Backend Server      ")
    print("   Listening on http://127.0.0.1:5000            ")
    print("==================================================")
    socketio.run(app, host='127.0.0.1', port=5000, debug=False, allow_unsafe_werkzeug=True)
