import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')
    
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://localhost/lotus_db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
    DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
    DISCORD_REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI', 'http://localhost:5000/callback')
    
    PNW_API_KEY = os.getenv('PNW_API_KEY')
    ALLIANCE_ID = os.getenv('ALLIANCE_ID')
    
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 
