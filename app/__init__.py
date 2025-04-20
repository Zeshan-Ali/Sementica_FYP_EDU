from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os
import click
from werkzeug.security import generate_password_hash

# Load environment variables first
load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///sentiment.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') or 'AIzaSyB5jOLyHnopCcpiubNnefqpPs77TMe5lkY'

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    
    # Configure login manager
    login_manager.login_view = 'main.login'
    login_manager.login_message_category = 'info'
    
    # Configure Gemini (ensure utils.py exists)
    from app.utils import configure_gemini
    configure_gemini(app.config['GEMINI_API_KEY'])
    
    # Register blueprints
    from app.routes import main
    app.register_blueprint(main)
    
    # Import models after db initialization to avoid circular imports
    with app.app_context():
        from app.models import User
        db.create_all()  # Create tables if they don't exist
        
        @app.cli.command('create-superadmin')
        @click.argument('username')
        @click.argument('password')
        def create_superadmin(username, password):
            """Create initial superadmin user"""
            if User.query.filter_by(role='superadmin').first():
                click.echo("Superadmin already exists!")
                return
            
            superadmin = User(
                username=username,
                password=generate_password_hash(password),
                role='superadmin',
                created_by=0  # System-created
            )
            db.session.add(superadmin)
            db.session.commit()
            click.echo(f"Superadmin '{username}' created successfully!")
    
    return app