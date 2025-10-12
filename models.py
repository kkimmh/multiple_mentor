# models.py

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    # ... (기존 User 모델 코드는 그대로)
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Conversation(db.Model):
    # ... (기존 Conversation 모델 코드는 그대로)
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    user_q_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user_a_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    # 👇 이 줄을 추가하거나 확인하세요!
    image_path = db.Column(db.String(300), nullable=True) # 이미지 파일 경로 저장
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)