import os
import json
import logging

APP_DATA_DIR = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Learnwave")
CONFIG_PATH = os.path.join(APP_DATA_DIR, "user_config.json")

def _load_config():
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def _save_config(config_data):
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config_data, f, indent=4)
    except IOError as e:
        logging.error(f"Could not write to user_config.json: {e}")

def save_api_key(api_key):
    config = _load_config()
    config['gemini_api_key'] = api_key
    _save_config(config)

def load_api_key():
    return _load_config().get('gemini_api_key')

def save_user_year(year):
    config = _load_config()
    config['user_year'] = year
    _save_config(config)
    logging.info(f"User year saved as: {year}")

def load_user_year():
    return _load_config().get('user_year')

def is_admin():
    return _load_config().get('is_admin', False)
