from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    streak = db.Column(db.Integer, default=0)
    last_completed_date = db.Column(db.String(100), nullable=True)
    tasks = db.relationship('Task', backref='owner', lazy=True)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    deadline = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='Pending') # Pending or Completed
    category = db.Column(db.String(50), default='Personal') # Study, Personal, Exam, Work
    priority = db.Column(db.String(20), default='Medium') # High, Medium, Low
    order = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
