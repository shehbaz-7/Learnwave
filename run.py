import os
import sys
import logging
import webbrowser
import time
from threading import Timer, Thread
from flask import Flask, render_template, jsonify
import waitress
import requests

# --- PATHING FIX ---
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- GLOBAL STATE ---
main_app_ready = False
initialization_status = {"status": "pending", "message": "Starting initialization..."}

# --- MAIN APPLICATION LOGIC ---
def run_main_app():
    global main_app_ready, initialization_status
    try:
        from main import initialize_main_app
        initialization_status = {"status": "running", "message": "Initializing application components..."}

        def update_status_callback(message):
            global initialization_status
            initialization_status = {"status": "running", "message": message}

        app = initialize_main_app(initialization_status_callback=update_status_callback)

        main_app_ready = True
        initialization_status = {"status": "complete", "message": "Main application is ready."}
        logging.info("--- Main application is now serving on http://127.0.0.1:5001 ---")
        waitress.serve(app, host="127.0.0.1", port=5001, threads=10)

    except Exception as e:
        logging.error(f"A fatal error occurred during main app startup: {e}", exc_info=True)
        main_app_ready = False
        initialization_status = {"status": "error", "message": f"Fatal startup error: {e}"}

# --- PRELOADER FLASK APP ---
preloader_app = Flask(__name__, template_folder=resource_path('templates'))
preloader_app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0 # Disable caching for status checks

@preloader_app.route('/')
def preloader_page():
    return render_template('startup_loader.html')

@preloader_app.route('/status')
def get_status():
    return jsonify(initialization_status)

@preloader_app.route('/check-main-app')
def check_main_app():
    if not main_app_ready:
        return jsonify({"ready": False})
    try:
        # A more reliable check to see if the server is actually responding
        response = requests.get("http://127.0.0.1:5001/auth/login", timeout=0.5)
        return jsonify({"ready": response.status_code == 200})
    except requests.ConnectionError:
        return jsonify({"ready": False})

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    main_app_thread = Thread(target=run_main_app, daemon=True)
    main_app_thread.start()

    def open_browser():
        webbrowser.open_new("http://127.0.0.1:5000")

    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        Timer(1.0, open_browser).start()

    logging.info("--- Starting Preloader on http://127.0.0.1:5000 ---")
    waitress.serve(preloader_app, host="127.0.0.1", port=5000)
