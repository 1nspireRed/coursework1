import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'my_super_secret_key_30052003'

DB_NAME = 'database.db'

#базы данных
def init_db():
    if not os.path.exists(DB_NAME):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'user'
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS donations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                donor_name TEXT,
                category TEXT,
                amount REAL,
                date TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                amount REAL,
                status TEXT DEFAULT 'На рассмотрении',
                comment TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        #администратор
        cursor.execute('SELECT * FROM users WHERE email = ?', ('admin@fund.ru',))
        admin = cursor.fetchone()
        if not admin:
            cursor.execute('''
                           INSERT INTO users (name, email, password, role)
                           VALUES (?, ?, ?, ?)
                           ''', ('Администратор', 'admin@fund.ru', 'admin123', 'admin'))
            print('[INFO] Администратор создан: admin@fund.ru / admin123')

        conn.commit()
        conn.close()

# Главная страница
@app.route('/')
def index():
    user = session.get('user')

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Получаем сумму по категориям
    cursor.execute("SELECT SUM(amount) FROM donations WHERE category = 'прочее'")
    sport_total = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(amount) FROM donations WHERE category = 'научная деятельность'")
    site_total = cursor.fetchone()[0] or 0

    # Статистика: общее количество заявок и пользователей
    cursor.execute("SELECT COUNT(*) FROM applications")
    total_applications = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    conn.close()

    # Цели по категориям (в рублях)
    sport_goal = 50000
    site_goal = 30000

    return render_template(
        'index.html',
        user=user,
        sport_total=sport_total,
        site_total=site_total,
        sport_goal=sport_goal,
        site_goal=site_goal,
        total_applications=total_applications,
        total_users=total_users
    )
# Регистрация
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)',
                           (name, email, password))
            conn.commit()
            flash('Регистрация прошла успешно!', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Пользователь с таким email уже существует', 'danger')
        finally:
            conn.close()

    return render_template('register.html')

# Вход
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ? AND password = ?', (email, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session['user'] = {'id': user[0], 'name': user[1], 'email': user[2], 'role': user[4]}
            flash(f'Добро пожаловать, {user[1]}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверный email или пароль', 'danger')

    return render_template('login.html')

# Выход
@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

# Подача заявки
@app.route('/apply', methods=['GET', 'POST'])
def apply():
    if 'user' not in session:
        flash('Войдите в систему для подачи заявки.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        amount = request.form['amount']
        user_id = session['user']['id']

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
                       INSERT INTO applications (user_id, title, description, amount)
                       VALUES (?, ?, ?, ?)
                       ''', (user_id, title, description, amount))
        conn.commit()
        conn.close()

        flash('Заявка успешно подана!', 'success')
        return redirect(url_for('my_applications'))

    return render_template('apply.html', user=session.get('user'))

# Просмотр своих заявок
@app.route('/my_applications')
def my_applications():
    if 'user' not in session:
        flash('Войдите для просмотра заявок.', 'danger')
        return redirect(url_for('login'))

    user_id = session['user']['id']
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id, title, amount, status, comment FROM applications WHERE user_id = ?', (user_id,))
    apps = cursor.fetchall()
    conn.close()

    return render_template('my_applications.html', apps=apps, user=session.get('user'))

# Панель администратора
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'user' not in session or session['user']['role'] != 'admin':
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('index'))

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Обработка формы
    if request.method == 'POST':
        app_id = request.form['app_id']
        status = request.form['status']
        comment = request.form['comment']
        cursor.execute('''
            UPDATE applications
            SET status = ?, comment = ?
            WHERE id = ?
        ''', (status, comment, app_id))
        conn.commit()
        flash('Заявка обновлена', 'success')

    # Пагинация
    page = int(request.args.get('page', 1))
    page_size = 10
    offset = (page - 1) * page_size

    # Всего заявок
    cursor.execute('SELECT COUNT(*) FROM applications')
    total_apps = cursor.fetchone()[0]
    total_pages = (total_apps + page_size - 1) // page_size

    # Заявки на текущей странице
    cursor.execute('''
                   SELECT applications.id, users.name, title, amount, status, comment
                   FROM applications
                            JOIN users ON applications.user_id = users.id
                   ORDER BY applications.id DESC LIMIT ?
                   OFFSET ?
                   ''', (page_size, offset))
    apps = cursor.fetchall()

    # Отчёт: заявки
    applications = apps  # можно будет отдельно фильтровать

    # Отчёт пожертвования
    cursor.execute('SELECT donor_name, category, amount, date FROM donations ORDER BY date DESC')
    donations = cursor.fetchall()

    cursor.execute('SELECT SUM(amount) FROM donations')
    total = cursor.fetchone()[0] or 0

    conn.close()

    return render_template(
        'admin_panel.html',
        apps=apps,
        applications=apps,
        donations=donations,
        total=total,
        page=page,
        total_pages=total_pages,
        user=session.get('user'))

# Редактирование заявки
@app.route('/edit/<int:app_id>', methods=['GET', 'POST'])
def edit_application(app_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT title, description, amount, status
        FROM applications
        WHERE id = ? AND user_id = ?
    ''', (app_id, session['user']['id']))
    app_data = cursor.fetchone()

    if not app_data:
        flash('Заявка не найдена', 'danger')
        conn.close()
        return redirect(url_for('my_applications'))

    if app_data[3] != 'На рассмотрении':
        flash('Редактирование доступно только для заявок на рассмотрении.', 'warning')
        conn.close()
        return redirect(url_for('my_applications'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        amount = request.form['amount']
        cursor.execute('''
            UPDATE applications
            SET title = ?, description = ?, amount = ?
            WHERE id = ?
        ''', (title, description, amount, app_id))
        conn.commit()
        conn.close()
        flash('Заявка обновлена.', 'success')
        return redirect(url_for('my_applications'))
    conn.close()
    return render_template('edit_application.html', app_id=app_id, app=app_data)

# Учёт пожертвований
@app.route('/donations', methods=['GET', 'POST'])
def donations():
    if 'user' not in session:
        flash('Войдите в систему для доступа к пожертвованиям', 'danger')
        return redirect(url_for('login'))

    role = session['user']['role']
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    if request.method == 'POST':
        # и админ, и обычный пользователь могут делать пожертвования
        donor = request.form['donor']
        category = request.form['category']
        amount = request.form['amount']
        date = datetime.now().strftime('%Y-%m-%d %H:%M')

        cursor.execute('''
            INSERT INTO donations (donor_name, category, amount, date)
            VALUES (?, ?, ?, ?)
        ''', (donor, category, amount, date))
        conn.commit()
        flash('Спасибо за пожертвование!', 'success')

    # Показываем список всем
    cursor.execute('SELECT donor_name, category, amount, date FROM donations ORDER BY date DESC')
    all_donations = cursor.fetchall()

    cursor.execute('SELECT SUM(amount) FROM donations')
    total = cursor.fetchone()[0] or 0

    conn.close()
    return render_template(
        'donations.html',
        donations=all_donations,
        total=total,
        role=role,
        user=session.get('user')
    )
# Запуск
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
