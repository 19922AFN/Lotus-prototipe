from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import os
import base64

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    discord_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    discord_username = db.Column(db.String(100), nullable=False)
    nation_id = db.Column(db.Integer, unique=True, nullable=True, index=True)
    nation_name = db.Column(db.String(100), nullable=True)
    rank = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<User {self.discord_username} - {self.nation_name}>'
    
    def set_api_key(self, api_key):
        if api_key:
            encrypted = cipher_suite.encrypt(api_key.encode())
            self.encrypted_api_key = encrypted
        else:
            self.encrypted_api_key = None
    
    def get_api_key(self):
        if self.encrypted_api_key:
            try:
                decrypted = cipher_suite.decrypt(self.encrypted_api_key)
                return decrypted.decode()
            except Exception as e:
                print(f"Error decrypting API key for user {self.id}: {e}")
                return None
        return None
    
    def to_dict(self):
        return {
            'id': self.id,
            'discord_id': self.discord_id,
            'discord_username': self.discord_username,
            'nation_id': self.nation_id,
            'nation_name': self.nation_name,
            'rank': self.rank,
            'has_api_key': self.encrypted_api_key is not None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Announcement(db.Model):
    __tablename__ = 'announcements'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Announcement {self.title}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'author': self.author,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    action = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    user = db.relationship('User', backref=db.backref('activity_logs', lazy=True))
    
    def __repr__(self):
        return f'<ActivityLog {self.action} by User {self.user_id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'details': self.details,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
