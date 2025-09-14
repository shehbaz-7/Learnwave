import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from models import User
from gemini_client import GeminiClient
import config_manager

auth = Blueprint('auth', __name__)
gemini_client = GeminiClient()

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.loading_page'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user, remember=True)
            return redirect(url_for('main.loading_page'))
        else:
            flash('Invalid username or password.', 'error')
    return render_template('auth/login.html')

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        # --- START OF CORRECTION ---
        # If already logged in, send to the new initializing page directly.
        return redirect(url_for('main.initializing'))
        # --- END OF CORRECTION ---
    if request.method == 'POST':
        api_key = request.form.get('gemini_api_key')
        user_year = request.form.get('user_year')
        
        if not all([request.form.get('username'), request.form.get('email'), request.form.get('password'), api_key, user_year]):
            flash('Please fill out all fields.', 'error')
            return render_template('auth/register.html')

        if not gemini_client.validate_api_key(api_key):
            flash('Invalid Gemini API key.', 'error')
            return render_template('auth/register.html')
            
        config_manager.save_api_key(api_key)
        config_manager.save_user_year(user_year)

        user = User(
            username=request.form.get('username'),
            email=request.form.get('email')
        )
        user.set_password(request.form.get('password'))
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        flash('Account created successfully!', 'success')

        # --- START OF CORRECTION ---
        # Redirect to our new lightweight initializing page first.
        return redirect(url_for('main.initializing'))
        # --- END OF CORRECTION ---
        
    return render_template('auth/register.html')
@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

@auth.route('/profile')
@login_required
def profile():
    api_key_set = bool(config_manager.load_api_key())
    current_year = config_manager.load_user_year()
    is_admin = config_manager.is_admin()
    return render_template('auth/profile.html', user=current_user, api_key_set=api_key_set, current_year=current_year, is_admin=is_admin)

@auth.route('/update_api_key', methods=['POST'])
@login_required
def update_api_key():
    api_key = request.form.get('gemini_api_key')
    if not api_key or not gemini_client.validate_api_key(api_key):
        flash('Invalid Gemini API key.', 'error')
        return redirect(url_for('auth.profile'))
    
    config_manager.save_api_key(api_key)
    flash('Gemini API key updated successfully!', 'success')
    return redirect(url_for('auth.profile'))

@auth.route('/change_password', methods=['POST'])
@login_required
def change_password():
    if not current_user.check_password(request.form.get('current_password')):
        flash('Current password is incorrect.', 'error')
        return redirect(url_for('auth.profile'))

    current_user.set_password(request.form.get('new_password'))
    db.session.commit()
    flash('Password changed successfully!', 'success')
    return redirect(url_for('auth.profile'))
