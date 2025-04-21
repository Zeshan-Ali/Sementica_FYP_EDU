from . import db
from flask_login import UserMixin

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
   