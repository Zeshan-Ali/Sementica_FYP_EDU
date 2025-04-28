from flask import Blueprint, abort, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app import db, login_manager
from flask import current_app
from app.models import User, Review, Product,  ProductReview,EcomProductReview,EcomProduct
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
import requests
from datetime import datetime

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

from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['admin', 'superadmin']:
            flash('You do not have permission to access this page', 'danger')
            return redirect(url_for('main.products'))
        return f(*args, **kwargs)
    return decorated_function

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


@main.route('/old-products')
def old_products():
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

@main.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role not in ['admin', 'superadmin']:
        abort(403)
    
    # Get all data
    all_reviews = Review.query.all()
    product_reviews = ProductReview.query.all()
    ecom_reviews = EcomProductReview.query.all()
    
    # Combine all reviews
    combined_reviews = list(all_reviews) + list(product_reviews) + list(ecom_reviews)
    
    # Prepare data structures
    data = {
        'sentiment': defaultdict(lambda: defaultdict(int)),
        'categories': defaultdict(lambda: defaultdict(int)),
        'products': defaultdict(lambda: defaultdict(int)),
        'ratings': defaultdict(int),
        'timeline': defaultdict(lambda: defaultdict(int)),
        'word_freq': defaultdict(lambda: defaultdict(int))
    }
    
    # Process all reviews
    for review in combined_reviews:
        try:
            # Get product info
            product = None
            product_category = "General"
            if hasattr(review, 'product'):
                product = review.product
                if hasattr(product, 'category'):
                    product_category = product.category
            
            # Sentiment analysis
            if review.sentiment:
                data['sentiment']['all'][review.sentiment] += 1
                data['sentiment'][product_category][review.sentiment] += 1
                if product:
                    data['sentiment'][product.name][review.sentiment] += 1
            
            # Categories
            data['categories'][product_category]['total'] += 1
            if review.sentiment:
                data['categories'][product_category][review.sentiment] += 1
            
            # Products
            if product:
                data['products'][product.name]['total'] += 1
                if review.sentiment:
                    data['products'][product.name][review.sentiment] += 1
            
            # Ratings
            if hasattr(review, 'rating') and review.rating:
                data['ratings'][review.rating] += 1
            
            # Timeline
            if hasattr(review, 'date_added') and review.date_added:
                month_year = review.date_added.strftime('%Y-%m')
                data['timeline'][month_year]['total'] += 1
                if review.sentiment:
                    data['timeline'][month_year][review.sentiment] += 1
            
            # Word frequency
            if review.text:
                words = re.findall(r'\b\w{3,}\b', review.text.lower())
                for word in words:
                    data['word_freq']['all'][word] += 1
                    data['word_freq'][product_category][word] += 1
                    if product:
                        data['word_freq'][product.name][word] += 1
        
        except Exception as e:
            print(f"Error processing review {review.id}: {str(e)}")
            continue
    
    # Process word frequencies (get top 20 for each category)
    processed_word_freq = defaultdict(dict)
    for category, words in data['word_freq'].items():
        top_words = sorted(words.items(), key=lambda x: x[1], reverse=True)[:20]
        processed_word_freq[category] = dict(top_words)
    
    # Prepare for superadmin
    admins = []
    if current_user.role == 'superadmin':
        admins = User.query.filter(User.role.in_(['admin', 'superadmin'])).all()
    
    return render_template(
        'admin_dashboard.html',
        sentiment_data=dict(data['sentiment']),
        category_data=dict(data['categories']),
        product_data=dict(data['products']),
        rating_data=dict(data['ratings']),
        timeline_data=dict(data['timeline']),
        word_freq=dict(processed_word_freq),
        admins=admins
    )
import re

def extract_product_id(url):
    """
    Extracts product ID from any Walmart product or reviews URL
    Handles these formats:
    - https://www.walmart.com/ip/PRODUCT-NAME/320040053
    - https://www.walmart.com/ip/320040053
    - https://www.walmart.com/reviews/product/320040053
    - https://www.walmart.com/reviews/product/320040053?entryPoint=viewAllReviewsBottom
    """
    patterns = [
        r'/ip/(?:[^/]+/)?(\d+)',  # /ip/.../PRODUCT_ID or /ip/PRODUCT_ID
        r'/reviews/product/(\d+)'   # /reviews/product/PRODUCT_ID
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None
def build_reviews_url(product_id):
    """Build the reviews URL from product ID"""
    return f"https://www.walmart.com/reviews/product/{product_id}?entryPoint=viewAllReviewsBottom"

def fetch_walmart_reviews(original_url):
    """Fetch reviews from Walmart using ZenRows API"""
    try:
        product_id = extract_product_id(original_url)
        if not product_id:
            return None, []
            
        # Build the proper reviews URL regardless of input URL format
        reviews_url = build_reviews_url(product_id)
        
        apikey = 'fee2190f6b50c867678a5ab9f37d9b4ab194259b'
        params = {
            'apikey': apikey,
            'url': reviews_url,
        }
        
        response = requests.get(
            'https://ecommerce.api.zenrows.com/v1/targets/walmart/reviews/',
            params=params,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Get product name from either the product_details or the original URL
        product_name = data.get('product_details', {}).get('product_name')
        if not product_name:
            # Fallback: Extract from original URL if available
            if '/ip/' in original_url:
                product_name = original_url.split('/ip/')[1].split('/')[0].replace('-', ' ').title()
        
        return product_name or f"Product {product_id}", data.get('product_reviews_list', [])
        
    except Exception as e:
        print(f"Error fetching reviews: {str(e)}")
        return None, []

def parse_walmart_date(date_str):
    """Convert Walmart date string (like 'Jun 27, 2024') to datetime object"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%b %d, %Y')
    except ValueError:
        return None

def process_reviews_in_batches(reviews, product_id, batch_size=20):
    """Process reviews in batches to avoid timeouts"""
    for i in range(0, len(reviews), batch_size):
        batch = reviews[i:i + batch_size]
        for review_data in batch:
            try:
                review_text = review_data.get('review_content', '')[:500]
                sentiment = analyze_sentiment(review_text)
                reply = generate_ai_reply(review_text)
                
                review = ProductReview(
                    text=review_text,
                    sentiment=sentiment,
                    reply=reply,
                    rating=int(review_data['average_rating_score']) if review_data.get('average_rating_score') else None,
                    reviewer=review_data.get('reviewer_name', '')[:100],
                    date_posted=parse_walmart_date(review_data.get('review_date')),
                    product_id=product_id
                )
                db.session.add(review)
            except Exception as e:
                print(f"Error processing review: {e}")
                continue
        
        db.session.commit()

@main.route('/product-reviews', methods=['GET', 'POST'])
@login_required
def product_reviews():
    if request.method == 'POST':
        original_url = request.form.get('product_url').strip()
        
        # Extract product ID from any valid Walmart URL format
        product_id = extract_product_id(original_url)
        if not product_id:
            flash('Invalid Walmart product URL. Please use a product page or reviews page URL.', 'danger')
            return redirect(url_for('main.product_reviews'))
        
        try:
            # Check if product exists or create new one
            product = Product.query.filter_by(product_id=product_id).first()
            if not product:
                # Fetch product details and reviews
                product_name, reviews = fetch_walmart_reviews(original_url)
                if not product_name or not reviews:
                    flash('No reviews found for this product', 'warning')
                    return redirect(url_for('main.product_reviews'))
                
                # Create new product with the original URL
                product = Product(
                    product_id=product_id,
                    name=product_name[:200],
                    url=original_url[:500]  # Store the original URL
                )
                db.session.add(product)
                db.session.flush()
                
                # Process reviews with sentiment analysis
                for review_data in reviews:
                    try:
                        review_text = review_data.get('review_content', '')[:500]
                        sentiment = analyze_sentiment(review_text)
                        reply = generate_ai_reply(review_text)
                        
                        review = ProductReview(
                            text=review_text,
                            sentiment=sentiment,
                            reply=reply,
                            rating=int(review_data.get('rating_score', 0)) if review_data.get('rating_score') else None,
                            reviewer=review_data.get('reviewer_name', '')[:100],
                            date_posted=parse_walmart_date(review_data.get('review_date')),
                            product_id=product.id,
                        )
                        db.session.add(review)
                    except Exception as e:
                        print(f"Error processing review: {e}")
                        continue
                
                db.session.commit()
                flash(f'Successfully imported {len(reviews)} reviews for {product_name}!', 'success')
            else:
                flash('This product already exists in database', 'info')
            
            return redirect(url_for('main.view_product_reviews', product_id=product.id))
        
        except Exception as e:
            db.session.rollback()
            print(f"Error: {str(e)}")
            flash('Error processing product reviews', 'danger')
            return redirect(url_for('main.product_reviews'))
    
    return render_template('product_reviews.html') 

@main.route('/product-reviews/<int:product_id>')
@login_required
def view_product_reviews(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Calculate sentiment distribution
    sentiment_counts = defaultdict(int)
    for review in product.reviews:
        if review.sentiment:
            sentiment_counts[review.sentiment] += 1
    
    # Prepare data for visualization
    sentiment_data = dict(sentiment_counts)
    
    return render_template(
        'view_product_reviews.html',
        product=product,
        sentiment_data=sentiment_data
    )
from werkzeug.utils import secure_filename
import os
from werkzeug.utils import secure_filename
import os

def allowed_image_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

@main.route('/products')
def products():
    """View all products - accessible to everyone"""
    all_products = EcomProduct.query.order_by(EcomProduct.date_added.desc()).all()
    return render_template('products.html', products=all_products)

@main.route('/product/<int:product_id>')
def product_detail(product_id):
    """View product details - accessible to everyone"""
    product = EcomProduct.query.get_or_404(product_id)
    
    # Calculate sentiment distribution for visualization
    sentiment_counts = defaultdict(int)
    for review in product.reviews:
        if review.sentiment:
            sentiment_counts[review.sentiment] += 1
    
    return render_template(
        'product_detail.html',
        product=product,
        sentiment_data=dict(sentiment_counts)
    )

@main.route('/add-review/<int:product_id>', methods=['POST'])
@login_required  # Only logged-in users can submit reviews
def add_review(product_id):
    """Submit review - accessible to all logged-in users"""
    product = EcomProduct.query.get_or_404(product_id)
    review_text = request.form.get('review_text')
    rating = int(request.form.get('rating'))
    
    # Analyze sentiment
    sentiment = analyze_sentiment(review_text)
    reply = generate_ai_reply(review_text)
    
    # Create review
    review = EcomProductReview(
        text=review_text,
        sentiment=sentiment,
        reply=reply,
        product_id=product.id,
        user_id=current_user.id,
        rating=rating
    )
    db.session.add(review)
    db.session.commit()
    
    flash('Review submitted successfully!', 'success')
    return redirect(url_for('main.product_detail', product_id=product.id))

@main.route('/add-product', methods=['GET', 'POST'])
@login_required
@admin_required  # This decorator needs to be created (see below)
def add_product():
    """Add product - accessible only to admins"""
    if request.method == 'POST':
        try:
            # Handle file upload
            image_file = request.files.get('image_file')
            filename = None
            
            if image_file and allowed_image_file(image_file.filename):
                filename = secure_filename(image_file.filename)
                image_path = os.path.join(current_app.root_path, 'static', 'uploads', 'products', filename)
                image_file.save(image_path)
            
            # Create new product
            product = EcomProduct(
                name=request.form.get('name'),
                price=float(request.form.get('price')),
                description=request.form.get('description'),
                image_filename=filename,
                category=request.form.get('category')
            )
            db.session.add(product)
            db.session.commit()
            flash('Product added successfully!', 'success')
            return redirect(url_for('main.products'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding product: {str(e)}', 'danger')
    
    return render_template('add_product.html')