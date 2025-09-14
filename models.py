from app import db
from datetime import datetime
from sqlalchemy import Text, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# All models inherit from db.Model, which is the correct declarative base
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    __bind_key__ = 'users'
    
    id = db.Column(Integer, primary_key=True)
    username = db.Column(String(80), unique=True, nullable=False)
    email = db.Column(String(120), unique=True, nullable=False)
    password_hash = db.Column(String(256), nullable=False)
    created_at = db.Column(DateTime, default=datetime.utcnow)
    is_active = db.Column(Boolean, default=True)
    
    documents = relationship("PDFDocument", primaryjoin="User.id == foreign(PDFDocument.user_id)", back_populates="user")
    chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class PDFDocument(db.Model):
    __tablename__ = 'pdfdocument'
    __bind_key__ = 'library'
    
    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, nullable=False)
    filename = db.Column(String(255), nullable=False)
    original_filename = db.Column(String(255), nullable=False)
    file_path = db.Column(String(500), nullable=False) # For PDFs: local path. For YT: URL.
    upload_date = db.Column(DateTime, default=datetime.utcnow)
    total_pages = db.Column(Integer, nullable=False, default=0) # For YT: number of segments.
    file_size = db.Column(Integer, nullable=False, default=0)
    doc_type = db.Column(String(50), nullable=False, default='pdf') # NEW: 'pdf' or 'youtube'
    processed = db.Column(Boolean, default=False)
    
    user = relationship("User", primaryjoin="foreign(PDFDocument.user_id) == User.id", back_populates="documents")
    pages = relationship("PDFPage", back_populates="document", cascade="all, delete-orphan")

class PDFPage(db.Model):
    __tablename__ = 'pdfpage'
    __bind_key__ = 'library'
    id = db.Column(Integer, primary_key=True)
    document_id = db.Column(Integer, ForeignKey('pdfdocument.id'), nullable=False)
    page_number = db.Column(Integer, nullable=False) # Represents page for PDF, segment index for video
    start_time_seconds = db.Column(Integer, nullable=True) # NEW: For linking to video timestamps
    text_content = db.Column(Text)
    gemini_analysis = db.Column(Text)
    processed_date = db.Column(DateTime, default=datetime.utcnow)
    document = relationship("PDFDocument", back_populates="pages")

class ChatMessage(db.Model):
    __tablename__ = 'chatmessage'
    __bind_key__ = 'users'
    
    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, ForeignKey('users.id'), nullable=False)
    user_message = db.Column(Text, nullable=False)
    ai_response = db.Column(Text, nullable=False)
    context_pages = db.Column(Text)
    created_date = db.Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="chat_messages")