from flask import Blueprint, abort, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app import db, login_manager
from app.models import User, Review
from app.utils import create_pie_chart, generate_ai_reply  # Ensure this import is correct
import joblib
import pandas as pd
from werkzeug.utils import secure_filename
import os
from app.utils import configure_gemini
import threading
from collections import defaultdict, Counter
import re
import app 

# Load model and vectorizer
model = joblib.load('voting_clf.pkl')
vectorizer = joblib.load('countvector.pkl')

# Create a Blueprint for routes
main = Blueprint('main', __name__)

# Configure upload folder and allowed extensions
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def analyze_sentiment(text):
    X = vectorizer.transform([text])
    prediction = model.predict(X.toarray())[0]
    
    # Convert numerical prediction to text labels
    return "positive" if prediction == 1 else "negative"  # Or add "neutral" if you have 3 classes
@main.route('/')
def index():
    """Show login page at root URL"""
    return render_template('login.html')  
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@main.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('main.login'))
@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        # Updated login verification
        if user and user.check_password(password):  # Use the check_password method
            login_user(user)
            return redirect(url_for('main.admin_dashboard' if user.role in ['admin', 'superadmin'] else 'main.user_dashboard'))
        else:
            flash('Invalid credentials', 'danger')
    
    return render_template('login.html')

@main.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists!', 'danger')
            return redirect(url_for('main.register'))
        
        new_user = User(
            username=username,
            role='user',  # Default role
            created_by=0  # System-created
        )
        new_user.set_password(password)  # Use set_password method
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('main.login'))
    
    return render_template('register.html')

@main.route('/user/dashboard')
@login_required
def user_dashboard():
    return render_template('user_dashboard.html')

@main.route('/analyze', methods=['POST'])
@login_required
def analyze():
    text = request.form.get('review')
    sentiment = analyze_sentiment(text)
    reply = generate_ai_reply(text)
    
    review = Review(
        text=text,
        sentiment=sentiment,
        reply=reply,
        user_id=current_user.id
    )
    db.session.add(review)
    db.session.commit()
    
    # Check where the request came from
    if request.referrer and 'products' in request.referrer:
        return redirect(url_for('main.products'))
    else:
        return render_template('user_dashboard.html', 
                           sentiment=sentiment, 
                           reply=reply)
    

@main.route('/bulk_upload', methods=['GET', 'POST'])
@login_required
def bulk_upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file uploaded!', 'danger')
            return redirect(request.url)

        file = request.files['file']

        if file.filename == '':
            flash('No file selected!', 'danger')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(file_path)

            try:
                df = pd.read_excel(file_path)
                if 'review' not in df.columns:
                    flash('The file must contain a "review" column!', 'danger')
                    return redirect(request.url)

                # Store all reviews first (without analysis)
                reviews = []
                for review_text in df['review']:
                    review = Review(text=review_text, 
                                  sentiment=None,
                                  reply=None,
                                  user_id=current_user.id)
                    db.session.add(review)
                    reviews.append(review)

                db.session.commit()
                
                # Check if "analyze_all" parameter was sent
                if request.form.get('analyze_all') == 'true':
                    # Analyze all reviews in bulk
                    for review in reviews:
                        review.sentiment = analyze_sentiment(review.text)
                        review.reply = generate_ai_reply(review.text)
                    db.session.commit()
                    flash('Bulk upload and analysis completed!', 'success')
                else:
                    flash('Reviews uploaded successfully! You can analyze them individually or all at once.', 'success')
                
                return render_template('bulk_upload.html', 
                                    uploaded_reviews=reviews,
                                    analyzed_all=request.form.get('analyze_all') == 'true')

            except Exception as e:
                flash(f'Error processing file: {str(e)}', 'danger')
                return redirect(request.url)

    return render_template('bulk_upload.html')

@main.route('/get_reviews')
@login_required
def get_reviews():
    review_ids = request.args.get('ids', '').split(',')
    reviews = Review.query.filter(Review.id.in_(review_ids)).all()
    return jsonify([{
        'id': r.id,
        'reply': r.reply
    } for r in reviews])

@main.route('/generate_reply', methods=['POST'])
@login_required
def generate_ai_reply_route():
    if request.method == 'POST':
        review_text = request.json.get('review')
        try:
            reply = generate_ai_reply(review_text)  # Your AI reply function
            return jsonify({'reply': reply})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@main.route('/bulk_generate_replies', methods=['POST'])
@login_required
def bulk_generate_replies():
    review_ids = request.json.get('review_ids', [])
    
    def background_task():
        with app.app_context():
            for review_id in review_ids:
                review = Review.query.get(review_id)
                if review and not review.reply:
                    review.reply = generate_ai_reply(review.text)
                    db.session.commit()
    
    threading.Thread(target=background_task).start()
    return jsonify({'status': 'started'})


@main.route('/products')
def products():
    # Get sample reviews for demonstration
    # In a real app, you'd want to filter by product ID or category
    reviews = Review.query.order_by(Review.id.desc()).limit(10).all()
    p = ['phone', 'smartphone', 'android', 'ios', 'screen protector', 'sim', 'charger', 'battery','mobile']
    l = ['laptop', 'notebook', 'macbook', 'macbook pro', 'macbook air', 'macbook pro 2021', 'macbook pro 2022', 'macbook pro 2023', 'macbook pro 2024','dell','hp','sony','vaio','chrome book']
    # Split into two groups for demonstration (phone and laptop reviews)
    reviews_phone = [r for r in reviews if any(keyword in r.text.lower() for keyword in p)]
    reviews_laptop = [r for r in reviews if any(keyword in r.text.lower() for keyword in l)]    
    
    return render_template('products.html',
                         reviews_phone=reviews_phone,
                         reviews_laptop=reviews_laptop)


# Add these imports at top
from werkzeug.security import generate_password_hash
import click

# ======= SUPER ADMIN ROUTES ======= #
@main.cli.command("create-superadmin")
@click.argument("username")
@click.argument("password")
def create_superadmin(username, password):
    """Create initial superadmin (run once)"""
    if User.query.filter_by(role='superadmin').first():
        print("Superadmin already exists!")
        return
    
    superadmin = User(
        username=username,
        password=generate_password_hash(password),
        role='superadmin',
        created_by=0  # System-created
    )
    db.session.add(superadmin)
    db.session.commit()
    print(f"Superadmin '{username}' created!")

@main.route('/admin/create-admin', methods=['GET', 'POST'])
@login_required
def create_admin():
    if current_user.role != 'superadmin':
        abort(403)
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        new_admin = User(
            username=username,
            password=generate_password_hash(password),
            role='admin',
            created_by=current_user.id
        )
        db.session.add(new_admin)
        db.session.commit()
        flash('Admin created successfully!', 'success')
        return redirect(url_for('main.admin_dashboard'))
    
    return render_template('create_admin.html')

@main.route('/revoke-admin', methods=['POST'])
@login_required
def revoke_admin():
    if current_user.role != 'superadmin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    admin_id = request.json.get('admin_id')
    admin = User.query.get(admin_id)
    
    if not admin or admin.role != 'admin':
        return jsonify({'success': False, 'message': 'Invalid admin'})
    
    admin.role = 'user'
    db.session.commit()
    return jsonify({'success': True})

# ======= UPDATED ADMIN DASHBOARD ======= #
@main.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role not in ['admin', 'superadmin']:
        abort(403)
    reviews = Review.query.filter(Review.sentiment.isnot(None)).all()
    
    # Categorize reviews
    categories = {
        'all': reviews,
        'mobile': [],
        'laptop': [],
        'general': []
    }

    mobile_keywords = {'mobile', 'phone', 'android', 'ios', 'screen protector', 'sim'}
    laptop_keywords = {'laptop', 'notebook', 'macbook', 'keyboard', 'trackpad', 'charger'}

    for review in reviews:
        text = review.text.lower()
        
        # Check for mobile keywords first
        if any(keyword in text for keyword in mobile_keywords):
            categories['mobile'].append(review)
        elif any(keyword in text for keyword in laptop_keywords):
            categories['laptop'].append(review)
        else:
            categories['general'].append(review)

    # Prepare visualization data
    sentiment_data = {}
    word_freq = {}
    for category, cat_reviews in categories.items():
        # Sentiment analysis
        sentiment_counts = defaultdict(int)
        for review in cat_reviews:
            sentiment_counts[review.sentiment] += 1
        sentiment_data[category] = dict(sentiment_counts)
        print(sentiment_data)
        
        # Word frequency
        words = []
        for review in cat_reviews:
            if review.text:
                words.extend(re.findall(r'\b\w+\b', review.text.lower()))
        word_freq[category] = dict(Counter(words).most_common(10))    
    print(word_freq)   
    # For superadmin only
    admins = []
    if current_user.role == 'superadmin':
        admins = User.query.filter(User.role.in_(['admin', 'superadmin'])).all()
    
    return render_template(
    'admin_dashboard.html',
    sentiment_data=sentiment_data,  
    word_freq=word_freq,
    admins=admins
)