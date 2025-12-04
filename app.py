from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, date
import traceback

app = Flask(__name__)
app.secret_key = 'your_secret_key_change_in_production_2024'  # поменяй в проде

# Добавляем функцию для форматирования даты в шаблоны
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%d.%m.%Y %H:%M'):
    if value is None:
        return ''
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d')
        except:
            return value
    return value.strftime(format)

# Конфигурация базы данных — поменяй при необходимости
db_config = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': '',
    'database': 'cleaning_company',
    'charset': 'utf8mb4'
}


def get_db_connection():
    """Получить соединение с базой данных"""
    try:
        conn = mysql.connector.connect(**db_config)
        conn.autocommit = False
        return conn
    except mysql.connector.Error as err:
        print(f"Ошибка подключения к БД: {err}")
        return None


# Декоратор для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Необходимо войти в систему', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ========== АВТОРИЗАЦИЯ ==========
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('Заполните все поля', 'error')
            return render_template('login.html')

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных', 'error')
            return render_template('login.html')

        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('SELECT * FROM User WHERE Username = %s', (username,))
            user = cursor.fetchone()

            if user and check_password_hash(user['Password'], password):
                session['user_id'] = user['ID']
                session['username'] = user['Username']
                session['fullname'] = user['FullName']
                session['role'] = user['Role']
                flash(f'Добро пожаловать, {user["FullName"]}!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Неверный логин или пароль', 'error')
        except mysql.connector.Error as err:
            flash(f'Ошибка при входе: {err}', 'error')
        finally:
            cursor.close()
            conn.close()

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Стандартная регистрация (по необходимости можно отключить)"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        fullname = request.form.get('fullname', '').strip()
        email = request.form.get('email', '').strip()

        if not all([username, password, password_confirm, fullname]):
            flash('Заполните все обязательные поля', 'error')
            return render_template('register.html')

        if password != password_confirm:
            flash('Пароли не совпадают', 'error')
            return render_template('register.html')

        if len(password) < 6:
            flash('Пароль должен быть не менее 6 символов', 'error')
            return render_template('register.html')

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных', 'error')
            return render_template('register.html')

        cursor = conn.cursor()
        try:
            cursor.execute('SELECT ID FROM User WHERE Username = %s', (username,))
            if cursor.fetchone():
                flash('Пользователь с таким логином уже существует', 'error')
                cursor.close()
                conn.close()
                return render_template('register.html')

            hashed_password = generate_password_hash(password)
            cursor.execute(
                '''INSERT INTO User (Username, Password, FullName, Email, Role) 
                   VALUES (%s, %s, %s, %s, %s)''',
                (username, hashed_password, fullname, email or None, 'manager')
            )
            conn.commit()
            flash('Регистрация успешна! Войдите в систему', 'success')
            return redirect(url_for('login'))
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Ошибка при регистрации: {err}', 'error')
        finally:
            cursor.close()
            conn.close()

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))


# ========== DASHBOARD ==========
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return render_template('dashboard.html', stats={})

    cursor = conn.cursor(dictionary=True)
    stats = {}
    try:
        cursor.execute('SELECT COUNT(*) as total FROM Client')
        stats['clients_count'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT COUNT(*) as total FROM Object')
        stats['objects_count'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT COUNT(*) as total FROM Employee WHERE Status = "Активен"')
        stats['employees_count'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT COUNT(*) as total FROM Service')
        stats['services_count'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT COUNT(*) as total FROM Schedule WHERE Status = "Запланировано"')
        stats['scheduled_count'] = cursor.fetchone()['total'] or 0

        cursor.execute('''SELECT COUNT(*) as total FROM Schedule 
                          WHERE Status = "Выполнено" 
                          AND MONTH(ScheduledDate) = MONTH(CURDATE())
                          AND YEAR(ScheduledDate) = YEAR(CURDATE())''')
        stats['completed_month'] = cursor.fetchone()['total'] or 0

        cursor.execute('''SELECT SUM(Cost) as total FROM Schedule 
                          WHERE Status = "Выполнено" 
                          AND MONTH(ScheduledDate) = MONTH(CURDATE())
                          AND YEAR(ScheduledDate) = YEAR(CURDATE())''')
        stats['revenue_month'] = cursor.fetchone()['total'] or 0

        cursor.execute('''
            SELECT s.*, o.ObjectName, c.FullName as ClientName, e.FullName as EmployeeName, srv.ServiceName
            FROM Schedule s
            JOIN Object o ON s.ObjectID = o.ID
            JOIN Client c ON o.ClientID = c.ID
            JOIN Service srv ON s.ServiceID = srv.ID
            LEFT JOIN Employee e ON s.EmployeeID = e.ID
            WHERE s.Status = "Запланировано" AND s.ScheduledDate >= CURDATE()
            ORDER BY s.ScheduledDate, s.ScheduledTime
            LIMIT 5
        ''')
        stats['upcoming_schedules'] = cursor.fetchall()

    except mysql.connector.Error as err:
        flash(f'Ошибка при получении статистики: {err}', 'error')
    finally:
        cursor.close()
        conn.close()

    return render_template('dashboard.html', stats=stats)


# ========== CLIENTS ==========
@app.route('/clients')
@login_required
def clients():
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return render_template('clients.html', clients=[])

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('''
            SELECT c.*, COUNT(o.ID) as objects_count
            FROM Client c
            LEFT JOIN Object o ON c.ID = o.ClientID
            GROUP BY c.ID
            ORDER BY c.FullName
        ''')
        clients = cursor.fetchall()
    except mysql.connector.Error as err:
        flash(f'Ошибка при получении данных: {err}', 'error')
        clients = []
    finally:
        cursor.close()
        conn.close()

    return render_template('clients.html', clients=clients)


@app.route('/add_client', methods=['GET', 'POST'])
@login_required
def add_client():
    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        if not fullname:
            flash('Имя клиента обязательно для заполнения', 'error')
            return redirect(url_for('add_client'))

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных', 'error')
            return redirect(url_for('clients'))

        cursor = conn.cursor()
        try:
            cursor.execute(
                '''INSERT INTO Client (FullName, Phone, Email, Address, CompanyName, ContactPerson, Notes) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                (
                    fullname,
                    request.form.get('phone', '').strip() or None,
                    request.form.get('email', '').strip() or None,
                    request.form.get('address', '').strip() or None,
                    request.form.get('company', '').strip() or None,
                    request.form.get('contact', '').strip() or None,
                    request.form.get('notes', '').strip() or None
                )
            )
            conn.commit()
            flash('Клиент успешно добавлен', 'success')
            return redirect(url_for('clients'))
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Ошибка при добавлении клиента: {err}', 'error')
        finally:
            cursor.close()
            conn.close()

    return render_template('add_client.html')


@app.route('/edit_client/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_client(id):
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return redirect(url_for('clients'))

    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        if not fullname:
            flash('Имя клиента обязательно для заполнения', 'error')
            return redirect(url_for('edit_client', id=id))

        cursor = conn.cursor()
        try:
            cursor.execute(
                '''UPDATE Client SET FullName=%s, Phone=%s, Email=%s, Address=%s, 
                   CompanyName=%s, ContactPerson=%s, Notes=%s WHERE ID=%s''',
                (
                    fullname,
                    request.form.get('phone', '').strip() or None,
                    request.form.get('email', '').strip() or None,
                    request.form.get('address', '').strip() or None,
                    request.form.get('company', '').strip() or None,
                    request.form.get('contact', '').strip() or None,
                    request.form.get('notes', '').strip() or None,
                    id
                )
            )
            conn.commit()
            flash('Клиент успешно обновлен', 'success')
            return redirect(url_for('clients'))
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Ошибка при обновлении клиента: {err}', 'error')
        finally:
            cursor.close()
            conn.close()

    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM Client WHERE ID = %s', (id,))
    client = cursor.fetchone()
    cursor.close()
    conn.close()

    if not client:
        flash('Клиент не найден', 'error')
        return redirect(url_for('clients'))

    return render_template('edit_client.html', client=client)


@app.route('/delete_client/<int:id>')
@login_required
def delete_client(id):
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return redirect(url_for('clients'))

    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM Client WHERE ID = %s', (id,))
        conn.commit()
        flash('Клиент успешно удален', 'success')
    except mysql.connector.Error as err:
        conn.rollback()
        flash(f'Ошибка при удалении клиента: {err}', 'error')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('clients'))


# ========== OBJECTS ==========
@app.route('/objects')
@login_required
def objects():
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return render_template('objects.html', objects=[])

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('''
            SELECT o.*, c.FullName as ClientName
            FROM Object o
            JOIN Client c ON o.ClientID = c.ID
            ORDER BY o.ObjectName
        ''')
        objects = cursor.fetchall()
    except mysql.connector.Error as err:
        flash(f'Ошибка при получении данных: {err}', 'error')
        objects = []
    finally:
        cursor.close()
        conn.close()

    return render_template('objects.html', objects=objects)


@app.route('/add_object', methods=['GET', 'POST'])
@login_required
def add_object():
    if request.method == 'POST':
        object_name = request.form.get('object_name', '').strip()
        address = request.form.get('address', '').strip()
        client_id = request.form.get('client_id', '').strip()

        if not all([object_name, address, client_id]):
            flash('Заполните все обязательные поля', 'error')
            return redirect(url_for('add_object'))

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных', 'error')
            return redirect(url_for('objects'))

        cursor = conn.cursor()
        try:
            area = request.form.get('area', '').strip()
            cursor.execute(
                '''INSERT INTO Object (ClientID, ObjectName, Address, Area, ObjectType, AccessInfo, Notes) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                (
                    int(client_id),
                    object_name,
                    address,
                    float(area) if area else None,
                    request.form.get('object_type', 'Офис'),
                    request.form.get('access_info', '').strip() or None,
                    request.form.get('notes', '').strip() or None
                )
            )
            conn.commit()
            flash('Объект успешно добавлен', 'success')
            return redirect(url_for('objects'))
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Ошибка при добавлении объекта: {err}', 'error')
        except ValueError:
            conn.rollback()
            flash('Ошибка в данных. Проверьте правильность ввода', 'error')
        finally:
            cursor.close()
            conn.close()

    conn = get_db_connection()
    if not conn:
        return render_template('add_object.html', clients=[])

    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT ID, FullName FROM Client ORDER BY FullName')
    clients = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('add_object.html', clients=clients)


@app.route('/edit_object/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_object(id):
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return redirect(url_for('objects'))

    if request.method == 'POST':
        object_name = request.form.get('object_name', '').strip()
        address = request.form.get('address', '').strip()
        client_id = request.form.get('client_id', '').strip()

        if not all([object_name, address, client_id]):
            flash('Заполните все обязательные поля', 'error')
            return redirect(url_for('edit_object', id=id))

        cursor = conn.cursor()
        try:
            area = request.form.get('area', '').strip()
            cursor.execute(
                '''UPDATE Object SET ClientID=%s, ObjectName=%s, Address=%s, Area=%s, 
                   ObjectType=%s, AccessInfo=%s, Notes=%s WHERE ID=%s''',
                (
                    int(client_id),
                    object_name,
                    address,
                    float(area) if area else None,
                    request.form.get('object_type', 'Офис'),
                    request.form.get('access_info', '').strip() or None,
                    request.form.get('notes', '').strip() or None,
                    id
                )
            )
            conn.commit()
            flash('Объект успешно обновлен', 'success')
            return redirect(url_for('objects'))
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Ошибка при обновлении объекта: {err}', 'error')
        except ValueError:
            conn.rollback()
            flash('Ошибка в данных', 'error')
        finally:
            cursor.close()
            conn.close()

    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM Object WHERE ID = %s', (id,))
    obj = cursor.fetchone()

    if not obj:
        cursor.close()
        conn.close()
        flash('Объект не найден', 'error')
        return redirect(url_for('objects'))

    cursor.execute('SELECT ID, FullName FROM Client ORDER BY FullName')
    clients = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('edit_object.html', object=obj, clients=clients)


@app.route('/delete_object/<int:id>')
@login_required
def delete_object(id):
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return redirect(url_for('objects'))

    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM Object WHERE ID = %s', (id,))
        conn.commit()
        flash('Объект успешно удален', 'success')
    except mysql.connector.Error as err:
        conn.rollback()
        flash(f'Ошибка при удалении объекта: {err}', 'error')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('objects'))


# ========== EMPLOYEES ==========
@app.route('/employees')
@login_required
def employees():
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return render_template('employees.html', employees=[])

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM Employee ORDER BY FullName')
        employees = cursor.fetchall()
    except mysql.connector.Error as err:
        flash(f'Ошибка при получении данных: {err}', 'error')
        employees = []
    finally:
        cursor.close()
        conn.close()

    return render_template('employees.html', employees=employees)


@app.route('/add_employee', methods=['GET', 'POST'])
@login_required
def add_employee():
    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()

        if not fullname:
            flash('ФИО сотрудника обязательно для заполнения', 'error')
            return redirect(url_for('add_employee'))

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных', 'error')
            return redirect(url_for('employees'))

        cursor = conn.cursor()
        try:
            hire_date = request.form.get('hire_date', '').strip() or None
            salary = request.form.get('salary', '').strip()

            cursor.execute(
                '''INSERT INTO Employee (FullName, Position, Phone, Email, PassportData, HireDate, Salary, Status, Notes) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                (
                    fullname,
                    request.form.get('position', '').strip() or None,
                    request.form.get('phone', '').strip() or None,
                    request.form.get('email', '').strip() or None,
                    request.form.get('passport', '').strip() or None,
                    hire_date,
                    float(salary) if salary else None,
                    request.form.get('status', 'Активен'),
                    request.form.get('notes', '').strip() or None
                )
            )
            conn.commit()
            flash('Сотрудник успешно добавлен', 'success')
            return redirect(url_for('employees'))
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Ошибка при добавлении сотрудника: {err}', 'error')
        except ValueError:
            conn.rollback()
            flash('Ошибка в данных', 'error')
        finally:
            cursor.close()
            conn.close()

    return render_template('add_employee.html')


@app.route('/edit_employee/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_employee(id):
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return redirect(url_for('employees'))

    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()

        if not fullname:
            flash('ФИО сотрудника обязательно для заполнения', 'error')
            return redirect(url_for('edit_employee', id=id))

        cursor = conn.cursor()
        try:
            hire_date = request.form.get('hire_date', '').strip() or None
            salary = request.form.get('salary', '').strip()

            cursor.execute(
                '''UPDATE Employee SET FullName=%s, Position=%s, Phone=%s, Email=%s, 
                   PassportData=%s, HireDate=%s, Salary=%s, Status=%s, Notes=%s WHERE ID=%s''',
                (
                    fullname,
                    request.form.get('position', '').strip() or None,
                    request.form.get('phone', '').strip() or None,
                    request.form.get('email', '').strip() or None,
                    request.form.get('passport', '').strip() or None,
                    hire_date,
                    float(salary) if salary else None,
                    request.form.get('status', 'Активен'),
                    request.form.get('notes', '').strip() or None,
                    id
                )
            )
            conn.commit()
            flash('Сотрудник успешно обновлен', 'success')
            return redirect(url_for('employees'))
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Ошибка при обновлении сотрудника: {err}', 'error')
        except ValueError:
            conn.rollback()
            flash('Ошибка в данных', 'error')
        finally:
            cursor.close()
            conn.close()

    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM Employee WHERE ID = %s', (id,))
    employee = cursor.fetchone()
    cursor.close()
    conn.close()

    if not employee:
        flash('Сотрудник не найден', 'error')
        return redirect(url_for('employees'))

    return render_template('edit_employee.html', employee=employee)


@app.route('/delete_employee/<int:id>')
@login_required
def delete_employee(id):
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return redirect(url_for('employees'))

    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM Employee WHERE ID = %s', (id,))
        conn.commit()
        flash('Сотрудник успешно удален', 'success')
    except mysql.connector.Error as err:
        conn.rollback()
        flash(f'Ошибка при удалении сотрудника: {err}', 'error')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('employees'))


# ========== SERVICES (Услуги) ==========
@app.route('/services')
@login_required
def services():
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return render_template('services.html', services=[])

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM Service ORDER BY ServiceName')
        services = cursor.fetchall()
    except mysql.connector.Error as err:
        flash(f'Ошибка при получении услуг: {err}', 'error')
        services = []
    finally:
        cursor.close()
        conn.close()

    return render_template('services.html', services=services)


@app.route('/add_service', methods=['GET', 'POST'])
@login_required
def add_service():
    if request.method == 'POST':
        name = request.form.get('service_name', '').strip()
        if not name:
            flash('Название услуги обязательно', 'error')
            return redirect(url_for('add_service'))

        try:
            price = request.form.get('price', '').strip()
            duration = request.form.get('duration', '').strip()
        except Exception:
            price = None
            duration = None

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к БД', 'error')
            return redirect(url_for('services'))

        cursor = conn.cursor()
        try:
            cursor.execute(
                '''INSERT INTO Service (ServiceName, Description, PricePerUnit, Unit, Duration, Notes)
                   VALUES (%s, %s, %s, %s, %s, %s)''',
                (
                    name,
                    request.form.get('description', '').strip() or None,
                    float(price) if price else None,
                    request.form.get('unit', '').strip() or None,
                    int(duration) if duration else None,
                    request.form.get('notes', '').strip() or None
                )
            )
            conn.commit()
            flash('Услуга добавлена', 'success')
            return redirect(url_for('services'))
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Ошибка при добавлении услуги: {err}', 'error')
        except ValueError:
            conn.rollback()
            flash('Неправильный формат чисел', 'error')
        finally:
            cursor.close()
            conn.close()

    return render_template('add_service.html')


@app.route('/edit_service/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_service(id):
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к БД', 'error')
        return redirect(url_for('services'))

    if request.method == 'POST':
        name = request.form.get('service_name', '').strip()
        if not name:
            flash('Название услуги обязательно', 'error')
            return redirect(url_for('edit_service', id=id))

        try:
            price = request.form.get('price', '').strip()
            duration = request.form.get('duration', '').strip()
        except Exception:
            price = None
            duration = None

        cursor = conn.cursor()
        try:
            cursor.execute(
                '''UPDATE Service SET ServiceName=%s, Description=%s, PricePerUnit=%s, Unit=%s, Duration=%s, Notes=%s WHERE ID=%s''',
                (
                    name,
                    request.form.get('description', '').strip() or None,
                    float(price) if price else None,
                    request.form.get('unit', '').strip() or None,
                    int(duration) if duration else None,
                    request.form.get('notes', '').strip() or None,
                    id
                )
            )
            conn.commit()
            flash('Услуга обновлена', 'success')
            return redirect(url_for('services'))
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Ошибка при обновлении услуги: {err}', 'error')
        except ValueError:
            conn.rollback()
            flash('Неправильный формат чисел', 'error')
        finally:
            cursor.close()
            conn.close()

    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM Service WHERE ID = %s', (id,))
    service = cursor.fetchone()
    cursor.close()
    conn.close()

    if not service:
        flash('Услуга не найдена', 'error')
        return redirect(url_for('services'))

    return render_template('edit_service.html', service=service)


@app.route('/delete_service/<int:id>')
@login_required
def delete_service(id):
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к БД', 'error')
        return redirect(url_for('services'))

    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM Service WHERE ID = %s', (id,))
        conn.commit()
        flash('Услуга удалена', 'success')
    except mysql.connector.Error as err:
        conn.rollback()
        flash(f'Ошибка при удалении услуги: {err}', 'error')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('services'))


# ========== SCHEDULES (Расписания / Заказы) ==========
def calculate_cost_if_empty(conn, object_id, service_id, provided_cost):
    """
    Логика расчёта стоимости:
    - Если provided_cost (передан пользователем), вернуть его.
    - Иначе:
        * если Service.Unit == 'кв.м' и у объекта есть Area -> PricePerUnit * Area
        * иначе -> PricePerUnit (как базовая стоимость)
    Возвращает Decimal (float) или None.
    """
    if provided_cost:
        try:
            return float(provided_cost)
        except Exception:
            return None

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('SELECT PricePerUnit, Unit FROM Service WHERE ID = %s', (service_id,))
        srv = cursor.fetchone()
        if not srv or srv['PricePerUnit'] is None:
            return None
        price = float(srv['PricePerUnit'])
        unit = srv.get('Unit') or ''

        if unit == 'кв.м':
            cursor.execute('SELECT Area FROM Object WHERE ID = %s', (object_id,))
            obj = cursor.fetchone()
            if obj and obj.get('Area'):
                try:
                    area = float(obj['Area'])
                    return round(price * area, 2)
                except Exception:
                    return round(price, 2)
            else:
                return round(price, 2)
        else:
            # Для других единиц нам достаточно базовой цены
            return round(price, 2)
    finally:
        cursor.close()


@app.route('/schedules')
@login_required
def schedules():
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return render_template('schedules.html', schedules=[])

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('''
            SELECT s.*, o.ObjectName, c.FullName as ClientName, e.FullName as EmployeeName, srv.ServiceName
            FROM Schedule s
            JOIN Object o ON s.ObjectID = o.ID
            JOIN Client c ON o.ClientID = c.ID
            JOIN Service srv ON s.ServiceID = srv.ID
            LEFT JOIN Employee e ON s.EmployeeID = e.ID
            ORDER BY s.ScheduledDate DESC, s.ScheduledTime DESC
        ''')
        schedules = cursor.fetchall()
    except mysql.connector.Error as err:
        flash(f'Ошибка при получении расписания: {err}', 'error')
        schedules = []
    finally:
        cursor.close()
        conn.close()

    return render_template('schedules.html', schedules=schedules)


@app.route('/add_schedule', methods=['GET', 'POST'])
@login_required
def add_schedule():
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к БД', 'error')
        return redirect(url_for('schedules'))

    if request.method == 'POST':
        object_id = request.form.get('object_id')
        service_id = request.form.get('service_id')
        employee_id = request.form.get('employee_id') or None
        scheduled_date = request.form.get('scheduled_date')
        scheduled_time = request.form.get('scheduled_time') or None
        duration = request.form.get('duration') or None
        status = request.form.get('status') or 'Запланировано'
        cost_input = request.form.get('cost') or None
        notes = request.form.get('notes') or None

        if not all([object_id, service_id, scheduled_date]):
            flash('Заполните обязательные поля (объект, услуга, дата)', 'error')
            cursor = conn.cursor()
            cursor.close()
            conn.close()
            return redirect(url_for('add_schedule'))

        cursor = conn.cursor()
        try:
            # Попробуем посчитать стоимость, если не задана
            cost = calculate_cost_if_empty(conn, int(object_id), int(service_id), cost_input)
            cursor.execute(
                '''INSERT INTO Schedule (ObjectID, ServiceID, EmployeeID, ScheduledDate, ScheduledTime, Duration, Status, Cost, Notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                (
                    int(object_id),
                    int(service_id),
                    int(employee_id) if employee_id else None,
                    scheduled_date,
                    scheduled_time,
                    int(duration) if duration else None,
                    status,
                    cost,
                    notes
                )
            )
            conn.commit()
            flash('Расписание добавлено', 'success')
            return redirect(url_for('schedules'))
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Ошибка при добавлении расписания: {err}', 'error')
        except ValueError:
            conn.rollback()
            flash('Ошибка в форматах полей', 'error')
        finally:
            cursor.close()
            conn.close()

    # GET — загрузить объекты, услуги, сотрудников
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT ID, ObjectName FROM Object ORDER BY ObjectName')
    objects = cursor.fetchall()
    cursor.execute('SELECT ID, ServiceName FROM Service ORDER BY ServiceName')
    services = cursor.fetchall()
    cursor.execute('SELECT ID, FullName FROM Employee WHERE Status = "Активен" ORDER BY FullName')
    employees = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('add_schedule.html', objects=objects, services=services, employees=employees)


@app.route('/edit_schedule/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_schedule(id):
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к БД', 'error')
        return redirect(url_for('schedules'))

    if request.method == 'POST':
        object_id = request.form.get('object_id')
        service_id = request.form.get('service_id')
        employee_id = request.form.get('employee_id') or None
        scheduled_date = request.form.get('scheduled_date')
        scheduled_time = request.form.get('scheduled_time') or None
        duration = request.form.get('duration') or None
        status = request.form.get('status') or 'Запланировано'
        cost_input = request.form.get('cost') or None
        notes = request.form.get('notes') or None

        if not all([object_id, service_id, scheduled_date]):
            flash('Заполните обязательные поля (объект, услуга, дата)', 'error')
            return redirect(url_for('edit_schedule', id=id))

        cursor = conn.cursor()
        try:
            cost = calculate_cost_if_empty(conn, int(object_id), int(service_id), cost_input)
            cursor.execute(
                '''UPDATE Schedule SET ObjectID=%s, ServiceID=%s, EmployeeID=%s, ScheduledDate=%s, ScheduledTime=%s,
                   Duration=%s, Status=%s, Cost=%s, Notes=%s WHERE ID=%s''',
                (
                    int(object_id),
                    int(service_id),
                    int(employee_id) if employee_id else None,
                    scheduled_date,
                    scheduled_time,
                    int(duration) if duration else None,
                    status,
                    cost,
                    notes,
                    id
                )
            )
            conn.commit()
            flash('Расписание обновлено', 'success')
            return redirect(url_for('schedules'))
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Ошибка при обновлении расписания: {err}', 'error')
        except ValueError:
            conn.rollback()
            flash('Ошибка в форматах полей', 'error')
        finally:
            cursor.close()
            conn.close()

    # GET - загрузить данные для формы
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM Schedule WHERE ID = %s', (id,))
    schedule = cursor.fetchone()
    if not schedule:
        cursor.close()
        conn.close()
        flash('Запись не найдена', 'error')
        return redirect(url_for('schedules'))

    cursor.execute('SELECT ID, ObjectName FROM Object ORDER BY ObjectName')
    objects = cursor.fetchall()
    cursor.execute('SELECT ID, ServiceName FROM Service ORDER BY ServiceName')
    services = cursor.fetchall()
    cursor.execute('SELECT ID, FullName FROM Employee WHERE Status = "Активен" ORDER BY FullName')
    employees = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('edit_schedule.html', schedule=schedule, objects=objects, services=services, employees=employees)


@app.route('/delete_schedule/<int:id>')
@login_required
def delete_schedule(id):
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к БД', 'error')
        return redirect(url_for('schedules'))

    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM Schedule WHERE ID = %s', (id,))
        conn.commit()
        flash('Запись расписания удалена', 'success')
    except mysql.connector.Error as err:
        conn.rollback()
        flash(f'Ошибка при удалении записи: {err}', 'error')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('schedules'))


# ========== REPORTS (Отчеты) ==========
@app.route('/reports')
@login_required
def reports():
    """Главная страница отчетов"""
    return render_template('reports.html', current_date=datetime.now())


@app.route('/reports/clients')
@login_required
def report_clients():
    """Отчет по клиентам"""
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return render_template('report_clients.html', clients=[], stats={})

    cursor = conn.cursor(dictionary=True)
    stats = {}
    try:
        # Получаем всех клиентов с дополнительной информацией
        cursor.execute('''
            SELECT c.*, COUNT(o.ID) as objects_count,
                   COALESCE(SUM(CASE WHEN s.Status = "Выполнено" THEN s.Cost ELSE 0 END), 0) as total_revenue,
                   COUNT(DISTINCT s.ID) as total_orders
            FROM Client c
            LEFT JOIN Object o ON c.ID = o.ClientID
            LEFT JOIN Schedule s ON o.ID = s.ObjectID
            GROUP BY c.ID
            ORDER BY c.FullName
        ''')
        clients = cursor.fetchall()

        # Статистика
        cursor.execute('SELECT COUNT(*) as total FROM Client')
        stats['total'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT COUNT(*) as total FROM Client WHERE Phone IS NOT NULL AND Phone != ""')
        stats['with_phone'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT COUNT(*) as total FROM Client WHERE Email IS NOT NULL AND Email != ""')
        stats['with_email'] = cursor.fetchone()['total'] or 0

        cursor.execute('''
            SELECT COUNT(DISTINCT c.ID) as total
            FROM Client c
            JOIN Object o ON c.ID = o.ClientID
        ''')
        stats['with_objects'] = cursor.fetchone()['total'] or 0

    except mysql.connector.Error as err:
        flash(f'Ошибка при получении данных: {err}', 'error')
        clients = []
    finally:
        cursor.close()
        conn.close()

    return render_template('report_clients.html', clients=clients, stats=stats, current_date=datetime.now())


@app.route('/reports/objects')
@login_required
def report_objects():
    """Отчет по объектам"""
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return render_template('report_objects.html', objects=[], stats={})

    cursor = conn.cursor(dictionary=True)
    stats = {}
    try:
        cursor.execute('''
            SELECT o.*, c.FullName as ClientName,
                   COUNT(s.ID) as total_orders,
                   COALESCE(SUM(CASE WHEN s.Status = "Выполнено" THEN s.Cost ELSE 0 END), 0) as total_revenue,
                   MAX(s.ScheduledDate) as last_service_date
            FROM Object o
            JOIN Client c ON o.ClientID = c.ID
            LEFT JOIN Schedule s ON o.ID = s.ObjectID
            GROUP BY o.ID
            ORDER BY o.ObjectName
        ''')
        objects = cursor.fetchall()

        # Статистика
        cursor.execute('SELECT COUNT(*) as total FROM Object')
        stats['total'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT SUM(Area) as total FROM Object WHERE Area IS NOT NULL')
        stats['total_area'] = cursor.fetchone()['total'] or 0

        cursor.execute('''
            SELECT COUNT(DISTINCT o.ID) as total
            FROM Object o
            JOIN Schedule s ON o.ID = s.ObjectID
            WHERE s.Status = "Выполнено"
        ''')
        stats['with_services'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT COUNT(DISTINCT ObjectType) as total FROM Object WHERE ObjectType IS NOT NULL')
        stats['types_count'] = cursor.fetchone()['total'] or 0

    except mysql.connector.Error as err:
        flash(f'Ошибка при получении данных: {err}', 'error')
        objects = []
    finally:
        cursor.close()
        conn.close()

    return render_template('report_objects.html', objects=objects, stats=stats, current_date=datetime.now())


@app.route('/reports/employees')
@login_required
def report_employees():
    """Отчет по сотрудникам"""
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return render_template('report_employees.html', employees=[], stats={})

    cursor = conn.cursor(dictionary=True)
    stats = {}
    try:
        cursor.execute('''
            SELECT e.*,
                   COUNT(s.ID) as total_orders,
                   COALESCE(SUM(CASE WHEN s.Status = "Выполнено" THEN s.Cost ELSE 0 END), 0) as total_revenue,
                   COUNT(CASE WHEN s.Status = "Выполнено" THEN 1 END) as completed_orders
            FROM Employee e
            LEFT JOIN Schedule s ON e.ID = s.EmployeeID
            GROUP BY e.ID
            ORDER BY e.FullName
        ''')
        employees = cursor.fetchall()

        # Статистика
        cursor.execute('SELECT COUNT(*) as total FROM Employee')
        stats['total'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT COUNT(*) as total FROM Employee WHERE Status = "Активен"')
        stats['active'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT COUNT(*) as total FROM Employee WHERE Status = "Неактивен"')
        stats['inactive'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT AVG(Salary) as avg FROM Employee WHERE Salary IS NOT NULL AND Status = "Активен"')
        result = cursor.fetchone()
        stats['avg_salary'] = result['avg'] if result['avg'] else 0

        cursor.execute('SELECT SUM(Salary) as total FROM Employee WHERE Status = "Активен"')
        stats['total_salary'] = cursor.fetchone()['total'] or 0

    except mysql.connector.Error as err:
        flash(f'Ошибка при получении данных: {err}', 'error')
        employees = []
    finally:
        cursor.close()
        conn.close()

    return render_template('report_employees.html', employees=employees, stats=stats, current_date=datetime.now())


@app.route('/reports/services')
@login_required
def report_services():
    """Отчет по услугам"""
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return render_template('report_services.html', services=[], stats={})

    cursor = conn.cursor(dictionary=True)
    stats = {}
    try:
        cursor.execute('''
            SELECT s.*,
                   COUNT(sch.ID) as total_orders,
                   COALESCE(SUM(CASE WHEN sch.Status = "Выполнено" THEN sch.Cost ELSE 0 END), 0) as total_revenue,
                   COUNT(CASE WHEN sch.Status = "Выполнено" THEN 1 END) as completed_orders
            FROM Service s
            LEFT JOIN Schedule sch ON s.ID = sch.ServiceID
            GROUP BY s.ID
            ORDER BY s.ServiceName
        ''')
        services = cursor.fetchall()

        # Статистика
        cursor.execute('SELECT COUNT(*) as total FROM Service')
        stats['total'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT AVG(PricePerUnit) as avg FROM Service WHERE PricePerUnit IS NOT NULL')
        result = cursor.fetchone()
        stats['avg_price'] = result['avg'] if result['avg'] else 0

        cursor.execute('''
            SELECT SUM(CASE WHEN sch.Status = "Выполнено" THEN sch.Cost ELSE 0 END) as total
            FROM Schedule sch
        ''')
        stats['total_revenue'] = cursor.fetchone()['total'] or 0

        cursor.execute('''
            SELECT COUNT(*) as total
            FROM Schedule
            WHERE Status = "Выполнено"
        ''')
        stats['completed_orders'] = cursor.fetchone()['total'] or 0

    except mysql.connector.Error as err:
        flash(f'Ошибка при получении данных: {err}', 'error')
        services = []
    finally:
        cursor.close()
        conn.close()

    return render_template('report_services.html', services=services, stats=stats, current_date=datetime.now())


@app.route('/reports/schedules')
@login_required
def report_schedules():
    """Отчет по расписанию/заказам"""
    conn = get_db_connection()
    if not conn:
        flash('Ошибка подключения к базе данных', 'error')
        return render_template('report_schedules.html', schedules=[], stats={})

    # Получаем параметры фильтрации
    status_filter = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    cursor = conn.cursor(dictionary=True)
    stats = {}
    try:
        # Базовый запрос
        query = '''
            SELECT s.*, o.ObjectName, o.Address as ObjectAddress,
                   c.FullName as ClientName, c.Phone as ClientPhone,
                   e.FullName as EmployeeName, srv.ServiceName, srv.PricePerUnit
            FROM Schedule s
            JOIN Object o ON s.ObjectID = o.ID
            JOIN Client c ON o.ClientID = c.ID
            JOIN Service srv ON s.ServiceID = srv.ID
            LEFT JOIN Employee e ON s.EmployeeID = e.ID
            WHERE 1=1
        '''
        params = []

        if status_filter:
            query += ' AND s.Status = %s'
            params.append(status_filter)

        if date_from:
            query += ' AND s.ScheduledDate >= %s'
            params.append(date_from)

        if date_to:
            query += ' AND s.ScheduledDate <= %s'
            params.append(date_to)

        query += ' ORDER BY s.ScheduledDate DESC, s.ScheduledTime DESC'

        cursor.execute(query, params)
        schedules = cursor.fetchall()

        # Статистика
        cursor.execute('SELECT COUNT(*) as total FROM Schedule')
        stats['total'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT COUNT(*) as total FROM Schedule WHERE Status = "Запланировано"')
        stats['scheduled'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT COUNT(*) as total FROM Schedule WHERE Status = "Выполнено"')
        stats['completed'] = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT COUNT(*) as total FROM Schedule WHERE Status = "Отменено"')
        stats['cancelled'] = cursor.fetchone()['total'] or 0

        cursor.execute('''
            SELECT SUM(Cost) as total
            FROM Schedule
            WHERE Status = "Выполнено"
        ''')
        stats['total_revenue'] = cursor.fetchone()['total'] or 0

        cursor.execute('''
            SELECT SUM(Cost) as total
            FROM Schedule
            WHERE Status = "Выполнено"
            AND MONTH(ScheduledDate) = MONTH(CURDATE())
            AND YEAR(ScheduledDate) = YEAR(CURDATE())
        ''')
        stats['revenue_month'] = cursor.fetchone()['total'] or 0

        cursor.execute('''
            SELECT AVG(Cost) as avg
            FROM Schedule
            WHERE Status = "Выполнено" AND Cost IS NOT NULL
        ''')
        result = cursor.fetchone()
        stats['avg_order_cost'] = result['avg'] if result['avg'] else 0

    except mysql.connector.Error as err:
        flash(f'Ошибка при получении данных: {err}', 'error')
        schedules = []
    finally:
        cursor.close()
        conn.close()

    return render_template('report_schedules.html', schedules=schedules, stats=stats,
                          status_filter=status_filter, date_from=date_from, date_to=date_to, current_date=datetime.now())


# ========== Доп. маршруты / утилиты ==========
@app.route('/favicon.ico')
def favicon():
    """Обработчик для favicon.ico, чтобы избежать ошибок 404/500"""
    return '', 204  # No Content


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
