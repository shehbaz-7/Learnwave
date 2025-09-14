import os
import sys
import logging
from app import create_app
from drive_service import DriveService
from vector_db import VectorDatabase
import config_manager

def get_current_version():
    try:
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(base_path, 'version.txt'), 'r') as f:
            return f.read().strip()
    except Exception:
        return "0.0.0"

CURRENT_APP_VERSION = get_current_version()
APP_DATA_DIR = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Learnwave")

YEAR_FOLDER_IDS = {
    "FirstYear": "1P107u74ulyHYuY1ykQ4rxKMBkD_gjsT3",
    "SecondYear": "1t3addYcCmouXQtGOIHN_ghsl3szlUjdX",
    "ThirdYear": "10GlPBkufD_oh-eOBDRDS8Ik25CBurmkN",
    "FourthYear": "1bwKg_Rd4zv1X6eAJGA40rqUO1tMHT7LS",
    "Admin": "1FF8yYUthkO-vAS8GoMlL6OlixDPexpQM"
}

class Config:
    SECRET_KEY = "dev-secret-key-for-desktop-multi-year"
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_recycle": 300, "pool_pre_ping": True}
    UPLOAD_FOLDER = APP_DATA_DIR
    LIBRARY_DB_PATH = os.path.join(APP_DATA_DIR, "library.db")
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{LIBRARY_DB_PATH}'
    USER_DB_PATH = os.path.join(APP_DATA_DIR, "user.db")
    SQLALCHEMY_BINDS = {
        'users': f'sqlite:///{USER_DB_PATH}'
    }

def initialize_main_app(initialization_status_callback):
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    
    initialization_status_callback("Authenticating with Google...")
    drive = DriveService()
    
    user_year = "Admin" if config_manager.is_admin() else config_manager.load_user_year()
    
    if user_year and user_year in YEAR_FOLDER_IDS:
        year_data_path = os.path.join(APP_DATA_DIR, user_year)
        os.makedirs(year_data_path, exist_ok=True)
        library_db_path = os.path.join(year_data_path, "library.db")
        Config.SQLALCHEMY_BINDS['library'] = f"sqlite:///{library_db_path}"
    else:
        dummy_path = os.path.join(APP_DATA_DIR, "dummy_library.db")
        Config.SQLALCHEMY_BINDS['library'] = f'sqlite:///{dummy_path}'
    
    app = create_app(Config)
    app.drive_service = drive
    app.year_folder_ids = YEAR_FOLDER_IDS
    
    with app.app_context():
        initialization_status_callback("Loading ML models and vector index...")
        if user_year:
            year_data_path = os.path.join(APP_DATA_DIR, user_year)
            vector_db_path = os.path.join(year_data_path)
            app.vector_db = VectorDatabase(vector_db_path)
        else:
            app.vector_db = None
            logging.warning("No user year selected, vector database not loaded.")

    return app
