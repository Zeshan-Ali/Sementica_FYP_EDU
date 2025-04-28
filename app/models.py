from . import db
from flask_login import UserMixin
from datetime import datetime
from . import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash,check_password_hash

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')  # superadmin/admin/user
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # Who created this user
    is_active = db.Column(db.Boolean, default=True)

    # In your User model
    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

# models.py
class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(500), nullable=False)
    sentiment = db.Column(db.String(20), nullable=True)
    reply = db.Column(db.String(500), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
   


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    reviews = db.relationship('ProductReview', backref='product', lazy=True)
    
    @property
    def reviews_url(self):
        """Generate the proper reviews URL from product ID"""
        return f"https://www.walmart.com/reviews/product/{self.product_id}?entryPoint=viewAllReviewsBottom"

class ProductReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(500), nullable=False)
    sentiment = db.Column(db.String(20), nullable=True)
    reply = db.Column(db.String(500), nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)  # Must be provided
    rating = db.Column(db.Integer, nullable=True)
    reviewer = db.Column(db.String(100), nullable=True)
    date_posted = db.Column(db.DateTime, nullable=True)  # Changed from String to DateTime
    
    __table_args__ = (
        db.Index('ix_product_review_product', 'product_id'),
    )

class EcomProduct(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    category = db.Column(db.String(50), nullable=False)  # e.g., 'Electronics', 'Clothing'
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    reviews = db.relationship('EcomProductReview', backref='product', lazy=True)

class EcomProductReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(500), nullable=False)
    sentiment = db.Column(db.String(20), nullable=True)
    reply = db.Column(db.String(500), nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    product_id = db.Column(db.Integer, db.ForeignKey('ecom_product.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=True)
    
    user = db.relationship('User', backref='ecom_reviews')