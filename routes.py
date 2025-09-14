import os
import json
import logging
import time
import shutil
import re
import sqlite3
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import (render_template, request, redirect, url_for, flash,
                   jsonify, send_from_directory, Response, Blueprint, current_app, abort, send_file)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload, sessionmaker
from sqlalchemy import create_engine, text
from app import db, processing_status, admin_required
from models import PDFDocument, PDFPage, ChatMessage
from pdf_processor import PDFProcessor
from youtube_processor import YouTubeProcessor
from gemini_client import GeminiClient
import config_manager
import numpy as np
from vector_db import VectorDatabase

sync_lock = Lock()
sync_status = {"status": "pending", "message": "Waiting to start..."}
main_routes = Blueprint('main', __name__)

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.int_, np.intc, np.intp, np.int8,
                            np.int16, np.int32, np.int64, np.uint8,
                            np.uint16, np.uint32, np.uint64)):
            return int(obj)
        elif isinstance(obj, (np.float64, np.float16, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        return super(NumpyEncoder, self).default(obj)

def _get_year_path(year):
    app_data_dir = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Learnwave")
    return os.path.join(app_data_dir, year)

def get_youtube_embed_url(youtube_url):
    video_id_match = re.search(r'(?:v=|\/|embed\/|youtu\.be\/)([a-zA-Z0-9_-]{11})', youtube_url)
    if video_id_match:
        video_id = video_id_match.group(1)
        return f"https://www.youtube.com/embed/{video_id}"
    return None

def sync_processed_files_to_drive(app, doc, year, vector_db_instance):
    with app.app_context():
        try:
            folder_id = app.year_folder_ids.get(year)
            if not folder_id: raise Exception(f"No Drive folder ID for year {year}.")
            
            files_to_upload = [
                os.path.join(vector_db_instance.index_path_base, "library.db"),
                vector_db_instance.faiss_index_path,
                vector_db_instance.page_map_path
            ]
            if doc.doc_type == 'pdf' and os.path.exists(doc.file_path):
                 files_to_upload.append(doc.file_path)
            
            for f_path in files_to_upload:
                if os.path.exists(f_path): app.drive_service.upload_file(f_path, folder_id)
        except Exception as e:
            logging.error(f"Failed to sync files for doc {doc.id} to Drive: {e}", exc_info=True)

def orchestrate_master_processing(app_context, content_identifier, original_filename, target_year, user_id, admin_doc_id, doc_type):
    admin_year = "Admin"
    def update_admin_status(text):
        processing_status[str(admin_doc_id)] = {"text": text, "complete": False}

    with app_context.app_context():
        try:
            update_admin_status(f"Analyzing {doc_type} content...")
            api_key = config_manager.load_api_key()
            page_data_list = []
            num_pages = 0
            processor_iterator = None
            if doc_type == 'pdf':
                processor = PDFProcessor(current_app.config)
                processor_iterator = processor.process_pdf(content_identifier, admin_doc_id, api_key, original_filename)
            elif doc_type == 'youtube':
                processor = YouTubeProcessor()
                processor_iterator = processor.process_video(content_identifier, admin_doc_id, api_key, original_filename)

            for status_update in processor_iterator:
                if 'page_data' in status_update:
                    page_data_list.append(status_update['page_data'])
                    num_pages += 1
                elif 'status_text' in status_update:
                    update_admin_status(status_update['status_text'])

            if not page_data_list:
                raise Exception(f"{doc_type.capitalize()} processing returned no data.")

            repos_to_process = [target_year, admin_year]
            for repo_year in repos_to_process:
                is_admin_repo = (repo_year == admin_year)
                repo_path = _get_year_path(repo_year)
                os.makedirs(repo_path, exist_ok=True)
                
                final_file_path = content_identifier
                if doc_type == 'pdf':
                    final_file_path = os.path.join(repo_path, original_filename)
                    if not os.path.exists(final_file_path):
                        shutil.copy(content_identifier, final_file_path)

                engine = create_engine(f"sqlite:///{os.path.join(repo_path, 'library.db')}")
                Session = sessionmaker(bind=engine)
                session = Session()

                try:
                    if is_admin_repo:
                        update_admin_status("Updating admin database...")
                        doc = session.get(PDFDocument, admin_doc_id)
                        doc.file_path = final_file_path
                        doc.file_size = os.path.getsize(final_file_path) if doc_type == 'pdf' else 0
                        doc.total_pages = num_pages
                        doc.processed = True
                    else:
                        doc = PDFDocument(user_id=user_id, filename=original_filename, original_filename=original_filename,
                                          file_path=final_file_path, doc_type=doc_type,
                                          file_size=os.path.getsize(final_file_path) if doc_type == 'pdf' else 0,
                                          processed=True, total_pages=num_pages)
                        session.add(doc)
                    session.commit()
                    doc_id = doc.id
                    for page_data in page_data_list:
                        session.add(PDFPage(document_id=doc_id, **page_data))
                    session.commit()
                    if is_admin_repo: update_admin_status(f"Indexing for admin...")
                    vector_db_instance = VectorDatabase(repo_path)
                    vector_db_instance.add_document(doc_id)
                    if is_admin_repo: update_admin_status(f"Syncing admin files to Drive...")
                    sync_processed_files_to_drive(current_app, doc, repo_year, vector_db_instance)
                finally:
                    session.close()

            logging.info("Reloading main admin vector index in memory.")
            current_app.vector_db.load_index()
            processing_status[str(admin_doc_id)] = {"text": "Processed", "complete": True}
            logging.info(f"--- Master orchestration complete for {original_filename} ---")

        except Exception as e:
            logging.error(f"Master orchestration failed for {original_filename}: {e}", exc_info=True)
            processing_status[str(admin_doc_id)] = {"text": "Failed", "complete": True, "error": True}
        finally:
            if doc_type == 'pdf' and os.path.exists(content_identifier):
                os.remove(content_identifier)

# --- START OF LEARNING PATH RE-ARCHITECTURE ---

def _extract_enhanced_text(analysis_text):
    if not analysis_text: return ""
    try:
        start_tag = "###ENHANCED_TEXT###"
        start_index = analysis_text.find(start_tag)
        if start_index == -1: return analysis_text 
        start_index += len(start_tag)
        next_section_start = analysis_text.find("###", start_index)
        if next_section_start != -1:
            return analysis_text[start_index:next_section_start].strip()
        else:
            return analysis_text[start_index:].strip()
    except Exception:
        return analysis_text

def _generate_step_worker(step_content, api_key, cache_file_path):
    """Worker function for a single thread to generate one HTML module."""
    gemini_client = GeminiClient()
    interactive_html = gemini_client.generate_interactive_module(step_content, api_key)
    with open(cache_file_path, 'w', encoding='utf-8') as f:
        f.write(interactive_html)
    return True

def orchestrate_full_learning_path_generation(app_context, doc_id, api_key):
    status_key = f"learning_path_{doc_id}"
    
    with app_context.app_context():
        try:
            doc = db.get_or_404(PDFDocument, doc_id)
            processing_status[status_key] = {"text": "Generating path structure...", "complete": False}

            engine = db.get_engine(bind_key='library')
            with engine.connect() as connection:
                result = connection.execute(
                    text("SELECT page_number, gemini_analysis FROM pdfpage WHERE document_id = :doc_id ORDER BY page_number"),
                    {"doc_id": doc_id}
                )
                page_contents = { row[0]: _extract_enhanced_text(row[1]) for row in result if row[1] }
            
            full_text = " ".join(page_contents.values())
            if not full_text.strip():
                raise ValueError("Document has no analyzed text content to process.")

            gemini_client = GeminiClient()
            path_structure = gemini_client.generate_learning_path_structure(full_text, doc.original_filename, api_key)
            if "error" in path_structure or not path_structure.get("steps"):
                raise ValueError(path_structure.get("error", "Failed to generate valid path structure."))
            
            steps = path_structure["steps"]
            total_steps = len(steps)
            processing_status[status_key]['path_data'] = path_structure 

            cache_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'learning_path_cache', str(doc_id))
            os.makedirs(cache_dir, exist_ok=True)
            
            # --- START OF MULTI-THREADING IMPLEMENTATION ---
            jobs = []
            for step_data in steps:
                step_number = step_data['step']
                step_content = page_contents.get(step_number)
                if step_content:
                    cache_file_path = os.path.join(cache_dir, f'step_{step_number}.html')
                    jobs.append({'content': step_content, 'path': cache_file_path})
            
            processed_count = 0
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_job = {executor.submit(_generate_step_worker, job['content'], api_key, job['path']): job for job in jobs}
                
                for future in as_completed(future_to_job):
                    try:
                        future.result() # Will re-raise exceptions from the thread
                        processed_count += 1
                        processing_status[status_key]["text"] = f"Generated {processed_count}/{total_steps} steps..."
                    except Exception as exc:
                        logging.error(f"A step generation failed: {exc}", exc_info=True)
                        # Propagate the error to the main try-except block
                        raise exc
            # --- END OF MULTI-THREADING IMPLEMENTATION ---

            processing_status[status_key] = {"text": "Complete", "complete": True, "path_data": path_structure}
            logging.info(f"Successfully generated full learning path for doc {doc_id}")

        except Exception as e:
            logging.error(f"Full learning path generation failed for doc {doc_id}: {e}", exc_info=True)
            processing_status[status_key] = {"text": str(e), "complete": True, "error": True}


@main_routes.route('/learning-path/create-full/<int:doc_id>', methods=['POST'])
@login_required
def create_full_learning_path(doc_id):
    status_key = f"learning_path_{doc_id}"
    if status_key in processing_status and not processing_status[status_key].get('complete'):
        return jsonify({'status': 'busy', 'message': 'This learning path is already being generated.'}), 409

    api_key = config_manager.load_api_key()
    if not api_key:
        return jsonify({'error': 'API key not configured.'}), 400

    processing_status[status_key] = {"text": "Queued for generation...", "complete": False}
    Thread(target=orchestrate_full_learning_path_generation, args=(current_app._get_current_object(), doc_id, api_key)).start()
    
    return jsonify({'status': 'queued', 'message': 'Learning path generation has started.'})

@main_routes.route('/learning-path/view/<path_id>')
@login_required
def learning_path_viewer(path_id):
    return render_template('learning_path.html', path_id=path_id)

@main_routes.route('/learning-path/step-content/<int:doc_id>/<int:step_number>')
@login_required
def learning_path_step_content(doc_id, step_number):
    cache_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'learning_path_cache', str(doc_id))
    cache_file = f'step_{step_number}.html'
    
    if not os.path.exists(os.path.join(cache_dir, cache_file)):
        logging.error(f"Cached file not found for doc {doc_id}, step {step_number}")
        return "Interactive content not found. It may still be generating or an error occurred.", 404
        
    return send_from_directory(cache_dir, cache_file)

@main_routes.route('/learning-path/delete-cache/<int:doc_id>', methods=['POST'])
@login_required
def delete_learning_path_cache(doc_id):
    try:
        cache_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'learning_path_cache', str(doc_id))
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            processing_status.pop(f"learning_path_{doc_id}", None)
            logging.info(f"Deleted learning path cache for doc {doc_id}")
        return jsonify({'status': 'success'})
    except Exception as e:
        logging.error(f"Failed to delete learning path cache for doc {doc_id}: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

# --- END OF LEARNING PATH RE-ARCHITECTURE ---

# --- START OF CORRECTION ---
@main_routes.route('/generate_study_set/<int:doc_id>', methods=['POST'])
@login_required
def generate_study_set(doc_id):
    api_key = config_manager.load_api_key()
    if not api_key:
        return jsonify({'error': 'API key not configured.'}), 400

    data = request.json
    try:
        # Use the correct database engine for the 'library' bind
        engine = db.get_engine(bind_key='library')
        with engine.connect() as connection:
            # First, get the document's filename to pass to the AI
            doc_result = connection.execute(
                text("SELECT original_filename FROM pdfdocument WHERE id = :doc_id"),
                {"doc_id": doc_id}
            ).fetchone()
            
            if not doc_result:
                return jsonify({'error': 'Document not found in the library database.'}), 404
            doc_filename = doc_result[0]

            # Now, get all the page text from the correct database
            page_result = connection.execute(
                text("SELECT text_content FROM pdfpage WHERE document_id = :doc_id"),
                {"doc_id": doc_id}
            )
            full_text = " ".join([row[0] for row in page_result if row[0]])

        if not full_text.strip():
            return jsonify({'error': 'Document has no text content to process.'}), 400

        gemini_client = GeminiClient()
        study_set_json = gemini_client.generate_study_set(
            document_text=full_text,
            doc_filename=doc_filename, # Use the correctly fetched filename
            set_type=data.get('setType', 'quiz'),
            difficulty=data.get('difficulty', 'medium'),
            question_count=data.get('count', 10),
            api_key=api_key
        )
        return jsonify(study_set_json)
    except Exception as e:
        logging.error(f"Failed to generate study set for doc {doc_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@main_routes.route('/get_explanation', methods=['POST'])
@login_required
def get_explanation():
    api_key = config_manager.load_api_key()
    if not api_key:
        return jsonify({'error': 'API key not configured.'}), 400
    
    data = request.json
    question = data.get('question')
    correct_answer = data.get('correctAnswer')
    doc_id = data.get('docId')

    try:
        # Use the correct database engine for the 'library' bind
        engine = db.get_engine(bind_key='library')
        with engine.connect() as connection:
            # First, confirm the document exists in this database
            doc_exists = connection.execute(
                text("SELECT id FROM pdfdocument WHERE id = :doc_id"),
                {"doc_id": doc_id}
            ).fetchone()
            
            if not doc_exists:
                 return jsonify({'error': 'Document not found in the library database.'}), 404

            # Now, get the text content from the correct database
            result = connection.execute(
                text("SELECT text_content FROM pdfpage WHERE document_id = :doc_id"),
                {"doc_id": doc_id}
            )
            full_text = " ".join([row[0] for row in result if row[0]])
        
        gemini_client = GeminiClient()
        explanation = gemini_client.get_answer_explanation(question, correct_answer, full_text, api_key)
        return jsonify({'explanation': explanation})
    except Exception as e:
        logging.error(f"Failed to get explanation: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
# --- END OF CORRECTION ---

@main_routes.route('/upload', methods=['POST'])
@login_required
@admin_required
def upload_content():
    target_year = request.form.get('target_year')
    upload_type = request.form.get('upload_type')
    if not target_year:
        flash("Please select a target year repository.", "error")
        return redirect(url_for('main.upload_file'))
    repos_to_check = ['Admin', target_year]
    for repo_year in repos_to_check:
        engine = create_engine(f"sqlite:///{os.path.join(_get_year_path(repo_year), 'library.db')}")
        with current_app.app_context():
                db.metadata.create_all(bind=engine, tables=[PDFDocument.__table__, PDFPage.__table__])
    if upload_type == 'pdf':
        files = request.files.getlist('files[]')
        if not files or not files[0].filename:
            flash("Please select at least one PDF file.", "error")
            return redirect(url_for('main.upload_file'))
        for file in files:
            original_filename = secure_filename(file.filename)
            temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp_uploads')
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(temp_dir, original_filename)
            file.save(temp_path)
            placeholder = PDFDocument(user_id=current_user.id, filename=original_filename, original_filename=original_filename, file_path="", doc_type='pdf', file_size=0, processed=False, total_pages=0)
            db.session.add(placeholder)
            db.session.commit()
            processing_status[str(placeholder.id)] = {"text": "Queued", "complete": False}
            Thread(target=orchestrate_master_processing, args=(current_app._get_current_object(), temp_path, original_filename, target_year, current_user.id, placeholder.id, 'pdf')).start()
        flash(f'{len(files)} PDF file(s) queued for processing.', 'success')
    elif upload_type == 'youtube':
        youtube_url = request.form.get('youtube_url')
        if not youtube_url or not re.search(r'(?:youtube\.com|youtu\.be)', youtube_url):
            flash("Please provide a valid YouTube URL.", "error")
            return redirect(url_for('main.upload_file'))
        video_id_match = re.search(r'(?:v=|\/)([a-zA-Z0-9_-]{11})', youtube_url)
        video_id = video_id_match.group(1) if video_id_match else "Unknown_Video"
        original_filename = f"YouTube - {video_id}"
        placeholder = PDFDocument(user_id=current_user.id, filename=video_id, original_filename=original_filename, file_path=youtube_url, doc_type='youtube', file_size=0, processed=False, total_pages=0)
        db.session.add(placeholder)
        db.session.commit()
        processing_status[str(placeholder.id)] = {"text": "Queued", "complete": False}
        Thread(target=orchestrate_master_processing, args=(current_app._get_current_object(), youtube_url, original_filename, target_year, current_user.id, placeholder.id, 'youtube')).start()
        flash(f'YouTube video "{original_filename}" queued for processing.', 'success')
    return redirect(url_for('main.index'))

@main_routes.route('/upload-page')
@login_required
@admin_required
def upload_file():
    api_key_set = bool(config_manager.load_api_key())
    return render_template('upload.html', api_key_set=api_key_set, years=list(current_app.year_folder_ids.keys()))

@main_routes.route('/')
@login_required
def root_redirect():
    return redirect(url_for('main.loading_page'))

@main_routes.route('/repository')
@login_required
def index():
    documents = db.session.execute(db.select(PDFDocument).order_by(PDFDocument.upload_date.desc())).scalars().all()
    return render_template('index.html', documents=documents)

@main_routes.route('/chat')
@login_required
def chat():
    history_query = db.select(ChatMessage).filter_by(user_id=current_user.id).order_by(ChatMessage.created_date.asc())
    history = db.session.execute(history_query).scalars().all()
    for msg in history:
        try:
            parsed_context = json.loads(msg.context_pages) if msg.context_pages else []
            for item in parsed_context:
                item['document_name'] = item.get('document_name', 'Unknown Document')
            msg.parsed_context = parsed_context
        except (json.JSONDecodeError, TypeError):
            msg.parsed_context = []
    all_docs = db.session.execute(db.select(PDFDocument)).scalars().all()
    documents_for_js = [{'id': doc.id, 'filename': doc.filename} for doc in all_docs]
    return render_template('chat.html', history=history, documents=documents_for_js)

@main_routes.route('/my-space')
@login_required
def my_space():
    return render_template('my_space.html')

@main_routes.route('/study_session/<set_id>')
@login_required
def study_session(set_id):
    return render_template('study_session.html')

@main_routes.route('/chat/message', methods=['POST'])
@login_required
def chat_message():
    data = request.json
    user_message = data.get('message', '').strip()
    content_type_filter = data.get('filter', 'all')
    if not user_message: return jsonify({'error': 'Empty message.'}), 400
    api_key = config_manager.load_api_key()
    if not api_key: return jsonify({'response': 'Error: API key is not configured.'}), 400
    try:
        gemini_client = GeminiClient()
        history = db.session.execute(db.select(ChatMessage).filter_by(user_id=current_user.id).order_by(ChatMessage.created_date.desc()).limit(5)).scalars().all()
        enhanced_query = gemini_client.refine_query_for_search(user_message, reversed(history), api_key)
        search_results = current_app.vector_db.search(enhanced_query, top_k=5, content_type_filter=content_type_filter)
        ai_response = gemini_client.generate_response(user_message, search_results, api_key)
        context_json = json.dumps(search_results, cls=NumpyEncoder)
        new_msg = ChatMessage(user_id=current_user.id, user_message=user_message, ai_response=ai_response, context_pages=context_json)
        db.session.add(new_msg)
        db.session.commit()
        return Response(json.dumps({'response': ai_response, 'context_pages': search_results}, cls=NumpyEncoder), content_type='application/json')
    except Exception as e:
        logging.error(f"Chat message error: {e}", exc_info=True)
        return jsonify({'response': f'An error occurred: {e}'}), 500

@main_routes.route('/search')
@login_required
def search():
    query = request.args.get('q', '').strip()
    results = []
    if query:
        search_results = current_app.vector_db.search(query, top_k=20)
        page_ids = [res['page_id'] for res in search_results]
        pages = db.session.query(PDFPage).filter(PDFPage.id.in_(page_ids)).options(joinedload(PDFPage.document)).all()
        page_map = {page.id: page for page in pages}
        for res in search_results:
            page = page_map.get(res['page_id'])
            if page:
                results.append({'document': page.document, 'page': page, 'score': res['score'], 'snippet': res.get('snippet', '')})
    return render_template('search.html', query=query, results=results)

@main_routes.route('/initializing')
@login_required
def initializing():
    return render_template('initializing.html')

@main_routes.route('/loading')
@login_required
def loading_page():
    user_year = "Admin" if config_manager.is_admin() else config_manager.load_user_year()
    if not user_year:
        flash("Please select your academic year in your profile to continue.", "info")
        return redirect(url_for('auth.profile'))
    try:
        year_path = _get_year_path(user_year)
        os.makedirs(year_path, exist_ok=True)
        library_db_path = os.path.join(year_path, "library.db")
        if 'library' in db.engines:
            db.get_engine(bind='library').dispose()
            logging.info("Disposed of existing library DB engine to release file locks.")
        if os.path.exists(library_db_path):
            try:
                conn = sqlite3.connect(library_db_path)
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(pdfdocument)")
                columns_doc = {info[1] for info in cursor.fetchall()}
                cursor.execute("PRAGMA table_info(pdfpage)")
                columns_page = {info[1] for info in cursor.fetchall()}
                conn.close()
                if 'doc_type' not in columns_doc or 'start_time_seconds' not in columns_page:
                    logging.warning("Outdated database schema detected. Wiping local library for a fresh start.")
                    shutil.rmtree(year_path)
                    os.makedirs(year_path, exist_ok=True)
                    flash("Your local library has been upgraded. A fresh sync will begin now.", "info")
            except Exception as e:
                logging.error(f"Failed to check database schema, forcing a wipe: {e}")
                shutil.rmtree(year_path)
                os.makedirs(year_path, exist_ok=True)
        library_db_uri = f"sqlite:///{library_db_path}"
        db.engines['library'] = db.create_engine(library_db_uri)
        with current_app.app_context():
            db.create_all(bind_key='library')
        current_app.vector_db = VectorDatabase(year_path)
    except Exception as e:
        logging.error(f"Failed to configure services for year {user_year}: {e}", exc_info=True)
        flash(f"A critical error occurred while initializing your library: {e}", "error")
        return redirect(url_for('auth.profile'))
    return render_template('loading.html')

@main_routes.route('/sync-status')
@login_required
def get_sync_status():
    global sync_status
    if sync_status['status'] == 'pending':
        if sync_lock.acquire(blocking=False):
            try:
                def do_sync(app):
                    global sync_status
                    with app.app_context():
                        user_year = "Admin" if config_manager.is_admin() else config_manager.load_user_year()
                        if not user_year:
                            sync_status = {"status": "error", "message": "User year not set."}
                            return
                        year_path = _get_year_path(user_year)
                        folder_id = app.year_folder_ids.get(user_year)
                        manifest_path = os.path.join(year_path, "sync_manifest.json")
                        if not folder_id:
                            sync_status = {"status": "error", "message": "Drive folder not configured."}
                            return
                        try:
                            sync_status = {"status": "syncing", "message": "Listing remote files..."}
                            local_manifest = json.load(open(manifest_path)) if os.path.exists(manifest_path) else {}
                            drive_files = app.drive_service.list_files_in_folder(folder_id)
                            drive_map = {f['name']: {'id': f['id'], 'modifiedTime': f['modifiedTime']} for f in drive_files}
                            to_download = [info for name, info in drive_map.items() if local_manifest.get(name, {}).get('modifiedTime') != info['modifiedTime']]
                            if not to_download:
                                sync_status = {"status": "complete", "message": "Library is up to date."}
                                return
                            for i, f_info in enumerate(to_download):
                                f_name = [k for k, v in drive_map.items() if v['id'] == f_info['id']][0]
                                sync_status = {"status": "syncing", "message": f"Downloading ({i+1}/{len(to_download)}): {f_name}"}
                                app.drive_service.download_file(f_info['id'], os.path.join(year_path, f_name))
                                local_manifest[f_name] = {'modifiedTime': f_info['modifiedTime']}
                            with open(manifest_path, 'w') as f: json.dump(local_manifest, f)
                            sync_status = {"status": "complete", "message": "Sync complete!"}
                        except Exception as e:
                            sync_status = {"status": "error", "message": f"Sync failed: {e}"}
                Thread(target=do_sync, args=[current_app._get_current_object()]).start()
            finally:
                sync_lock.release()
    return jsonify(sync_status)

@main_routes.route('/reload-services', methods=['POST'])
@login_required
def reload_services():
    try:
        user_year = "Admin" if config_manager.is_admin() else config_manager.load_user_year()
        if user_year:
            year_path = _get_year_path(user_year)
            library_db_uri = f"sqlite:///{os.path.join(year_path, 'library.db')}"
            logging.info(f"Reloading services for year {user_year}. Disposing old DB engine and creating new one for {library_db_uri}")
            if 'library' in db.engines:
                db.get_engine(bind='library').dispose()
            db.engines['library'] = db.create_engine(library_db_uri, pool_recycle=300, pool_pre_ping=True)
        if current_app.vector_db:
            current_app.vector_db.load_index()
            if current_app.vector_db.faiss_index.ntotal == 0:
                logging.warning("Index is empty after load. Triggering a full build as a fallback.")
                current_app.vector_db.build_full_index()
        if config_manager.is_admin():
            logging.info("Admin user detected. Reloading main admin vector index in memory.")
            current_app.vector_db.load_index()
        return jsonify({'status': 'success'})
    except Exception as e:
        logging.error(f"Failed to reload services: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_routes.route('/status/updates')
@login_required
def status_updates():
    def generate():
        while True:
            status_copy = dict(processing_status)
            yield f"data: {json.dumps(status_copy)}\n\n"
            time.sleep(1)
    return Response(generate(), mimetype='text/event-stream')

@main_routes.route('/document/delete/<int:doc_id>', methods=['POST'])
@login_required
@admin_required
def delete_document(doc_id):
    doc = db.get_or_404(PDFDocument, doc_id)
    original_filename = doc.original_filename
    try:
        cache_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'learning_path_cache', str(doc.id))
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            logging.info(f"Deleted learning path cache for document {doc.id}")

        repos_to_check = list(current_app.year_folder_ids.keys())
        for year in repos_to_check:
            year_path = _get_year_path(year)
            db_path = os.path.join(year_path, "library.db")
            if not os.path.exists(db_path): continue
            engine = create_engine(f"sqlite:///{db_path}")
            Session = sessionmaker(bind=engine)
            session = Session()
            try:
                doc_in_year = session.query(PDFDocument).filter_by(original_filename=original_filename).first()
                if doc_in_year:
                    logging.info(f"Deleting '{original_filename}' from {year} repository.")
                    if doc.doc_type == 'pdf':
                        folder_id = current_app.year_folder_ids.get(year)
                        current_app.drive_service.delete_file_by_name(original_filename, folder_id)
                    vector_db_instance = VectorDatabase(year_path)
                    vector_db_instance.remove_document(doc_in_year.id)
                    if doc.doc_type == 'pdf' and os.path.exists(doc_in_year.file_path):
                        os.remove(doc_in_year.file_path)
                    session.delete(doc_in_year)
                    session.commit()
            finally:
                session.close()
        flash(f'Successfully deleted "{original_filename}" from all repositories.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred during multi-repository delete: {e}', 'error')
    return redirect(url_for('main.index'))

@main_routes.route('/change_year', methods=['POST'])
@login_required
def change_year():
    new_year = request.form.get('new_year')
    if new_year not in current_app.year_folder_ids:
        return jsonify({'status': 'error', 'message': 'Invalid year selected.'}), 400
    try:
        old_year = config_manager.load_user_year()
        if old_year:
            shutil.rmtree(_get_year_path(old_year), ignore_errors=True)
        config_manager.save_user_year(new_year)
        return jsonify({'status': 'restart_required'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_routes.route('/delete_local_data', methods=['POST'])
@login_required
def delete_local_data():
    try:
        user_year = config_manager.load_user_year()
        if user_year:
            shutil.rmtree(_get_year_path(user_year), ignore_errors=True)
        learning_path_cache = os.path.join(current_app.config['UPLOAD_FOLDER'], 'learning_path_cache')
        if os.path.exists(learning_path_cache):
            shutil.rmtree(learning_path_cache)
        return jsonify({'status': 'restart_required'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_routes.route('/chat/clear', methods=['POST'])
@login_required
def clear_chat_history():
    try:
        ChatMessage.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception:
        db.session.rollback()
        return jsonify({'status': 'error'}), 500

@main_routes.route('/document/<int:doc_id>')
@login_required
def view_document(doc_id):
    doc = db.get_or_404(PDFDocument, doc_id)
    embed_url = None
    if doc.doc_type == 'youtube':
        embed_url = get_youtube_embed_url(doc.file_path)
    return render_template('view_document.html', document=doc, embed_url=embed_url)

@main_routes.route('/uploads/<int:doc_id>')
@login_required
def serve_pdf(doc_id):
    logging.info(f"Serving request for doc_id: {doc_id}")
    try:
        doc = db.get_or_404(PDFDocument, doc_id)
        filename = doc.original_filename
        if not filename:
            logging.error(f"Document with ID {doc_id} has no 'original_filename' in the database.")
            abort(404)
        user_year = "Admin" if config_manager.is_admin() else config_manager.load_user_year()
        local_directory = _get_year_path(user_year)
        expected_file_path = os.path.join(local_directory, filename)
        logging.info(f"  - Expecting file at: {expected_file_path}")
        if not os.path.exists(expected_file_path):
            logging.error(f"  - FILE NOT FOUND at the expected path.")
            try:
                files_in_dir = os.listdir(local_directory)
                logging.warning(f"  - Contents of '{local_directory}': {files_in_dir}")
            except Exception as e:
                logging.error(f"  - Could not list directory contents: {e}")
            abort(404)
        logging.info(f"  - File found. Serving '{filename}' from '{local_directory}'.")
        return send_from_directory(local_directory, filename)
    except Exception as e:
        logging.error(f"An unexpected error occurred in serve_pdf for doc_id {doc_id}: {e}", exc_info=True)
        abort(500)
