from flask import Flask, render_template, redirect, url_for, request, flash, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Task
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here' # Change this in production
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tasks.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Database Initialization ---
with app.app_context():
    db.create_all()

# --- Auth Routes ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_exists = User.query.filter_by(username=username).first()
        if user_exists:
            flash('Username already exists!', category='error')
        else:
            new_user = User(
                username=username, 
                password=generate_password_hash(password, method='pbkdf2:sha256')
            )
            db.session.add(new_user)
            db.session.commit()
            flash('Account created! Please login.', category='success')
            return redirect(url_for('login'))
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Logged in successfully!', category='success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', category='error')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', category='success')
    return redirect(url_for('login'))

# --- Task Routes ---

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    filter_type = request.args.get('filter', 'All')
    category_filter = request.args.get('category', 'All')
    priority_filter = request.args.get('priority', 'All')
    search_query = request.args.get('search', '')
    focus_mode = request.args.get('focus', 'off') == 'on'
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # Base query for the current user
    query = Task.query.filter_by(user_id=current_user.id)
    
    # Combined Search & Filtering Logic
    if search_query:
        query = query.filter(
            (Task.title.contains(search_query)) | 
            (Task.category.contains(search_query))
        )
    
    if filter_type != 'All':
        query = query.filter_by(status=filter_type)
        
    if category_filter != 'All':
        query = query.filter_by(category=category_filter)
        
    if priority_filter != 'All':
        query = query.filter_by(priority=priority_filter)
    
    # Order tasks by custom order column
    tasks = query.order_by(Task.order.asc(), Task.id.desc()).all()
    
    # Process deadline intelligence on backend
    today_date = datetime.now().date()
    for task in tasks:
        if task.deadline and task.status != 'Completed':
            task_date = datetime.strptime(task.deadline, '%Y-%m-%d').date()
            if task_date < today_date:
                task.deadline_status = 'overdue'
            elif task_date == today_date:
                task.deadline_status = 'today'
            elif today_date < task_date <= (today_date + timedelta(days=2)):
                task.deadline_status = 'soon'
            else:
                task.deadline_status = 'upcoming'
        else:
            task.deadline_status = 'none'
    
    # Productivity Statistics
    total_tasks = Task.query.filter_by(user_id=current_user.id).count()
    completed_count = Task.query.filter_by(user_id=current_user.id, status='Completed').count()
    pending_count = total_tasks - completed_count
    high_priority_count = Task.query.filter_by(user_id=current_user.id, status='Pending', priority='High').count()
    overdue_count = Task.query.filter_by(user_id=current_user.id, status='Pending').filter(Task.deadline < today_str).count()
    
    productivity_score = 0
    if total_tasks > 0:
        productivity_score = round((completed_count / total_tasks) * 100)
    
    # Smart Assistant Suggestion
    suggestion = "Try adding a small task to get started!"
    top_task = Task.query.filter_by(user_id=current_user.id, status='Pending').order_by(Task.priority.desc(), Task.deadline.asc()).first()
    if top_task:
        suggestion = f"Consider focusing on: {top_task.title}"
    
    stats = {
        'total': total_tasks,
        'completed': completed_count,
        'pending': pending_count,
        'score': productivity_score,
        'high_priority': high_priority_count,
        'overdue': overdue_count,
        'suggestion': suggestion
    }
    
    # Focus Mode Logic: Filter tasks in memory if needed
    display_tasks = tasks
    if focus_mode:
        pending_only = [t for t in tasks if t.status == 'Pending']
        display_tasks = [pending_only[0]] if pending_only else []

    return render_template('dashboard.html', 
                           tasks=display_tasks, 
                           current_filter=filter_type, 
                           current_category=category_filter,
                           current_priority=priority_filter,
                           search_query=search_query,
                           stats=stats,
                           focus_mode=focus_mode,
                           today=today_str)

@app.route('/update_order', methods=['POST'])
@login_required
def update_order():
    orders = request.json.get('orders', [])
    for order_info in orders:
        task = Task.query.get(order_info['id'])
        if task and task.user_id == current_user.id:
            task.order = order_info['order']
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/add', methods=['POST'])
@login_required
def add_task():
    title = request.form.get('title')
    deadline = request.form.get('deadline')
    category = request.form.get('category')
    priority = request.form.get('priority')
    
    if title:
        # Get max order for current user
        max_order = db.session.query(db.func.max(Task.order)).filter_by(user_id=current_user.id).scalar() or 0
        new_task = Task(
            title=title, 
            deadline=deadline, 
            category=category,
            priority=priority,
            order=max_order + 1,
            user_id=current_user.id
        )
        db.session.add(new_task)
        db.session.commit()
        flash('Task added!', category='success')
    else:
        flash('Task title is required.', category='error')
        
    return redirect(url_for('dashboard'))

@app.route('/complete/<int:id>')
@login_required
def complete_task(id):
    task = Task.query.get_or_404(id)
    if task.user_id != current_user.id:
        abort(403)
        
    task.status = 'Completed' if task.status == 'Pending' else 'Pending'
    
    # Streak Logic
    if task.status == 'Completed':
        today_date = datetime.now().date()
        today_str = today_date.strftime('%Y-%m-%d')
        yesterday_str = (today_date - timedelta(days=1)).strftime('%Y-%m-%d')
        
        if current_user.last_completed_date != today_str:
            if current_user.last_completed_date == yesterday_str:
                current_user.streak += 1
            else:
                current_user.streak = 1
            current_user.last_completed_date = today_str
            
    db.session.commit()
    flash(f'Task marked as {task.status}!', category='success')
    return redirect(url_for('dashboard'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_task(id):
    task = Task.query.get_or_404(id)
    if task.user_id != current_user.id:
        abort(403)
        
    if request.method == 'POST':
        task.title = request.form.get('title')
        task.deadline = request.form.get('deadline')
        task.category = request.form.get('category')
        task.priority = request.form.get('priority')
        db.session.commit()
        flash('Task updated!', category='success')
        return redirect(url_for('dashboard'))
        
    return render_template('edit.html', task=task)

@app.route('/delete/<int:id>')
@login_required
def delete_task(id):
    task = Task.query.get_or_404(id)
    if task.user_id != current_user.id:
        abort(403)
        
    db.session.delete(task)
    db.session.commit()
    flash('Task deleted.', category='success')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)
