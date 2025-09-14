import os
import logging
from flask import Flask, abort, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from functools import wraps
import config_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Standard Flask-SQLAlchemy initialization
db = SQLAlchemy()
login_manager = LoginManager()
processing_status = {}

def create_app(config_object):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    login_manager.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        with app.app_context():
            return db.session.get(User, int(user_id))

    @app.context_processor
    def inject_admin_status():
        if current_user.is_authenticated:
            return dict(is_admin=config_manager.is_admin())
        return dict(is_admin=False)

    @app.errorhandler(403)
    def forbidden(error): return render_template('errors/403.html'), 403
    @app.errorhandler(404)
    def not_found(error): return render_template('errors/404.html'), 404
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    with app.app_context():
        # Import models here so they register with the db object
        from models import User, PDFDocument, PDFPage, ChatMessage
        from auth import auth
        from routes import main_routes

        app.register_blueprint(auth, url_prefix='/auth')
        app.register_blueprint(main_routes)
        
        # This creates tables for the initial app context (user.db and Admin/library.db)
        db.create_all()

    return app

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not config_manager.is_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated_function