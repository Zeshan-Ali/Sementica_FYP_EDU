from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os

# Load environment variables first
load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///sentiment.db'
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') or 'AIzaSyB5jOLyHnopCcpiubNnefqpPs77TMe5lkY'

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    
    # Configure Gemini
    from app.utils import configure_gemini
    configure_gemini(app.config['GEMINI_API_KEY'])
    
    # Register blueprints
    from app.routes import main
    app.register_blueprint(main)
    
    return app