from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from wtforms import StringField, PasswordField, SubmitField, validators,Form
from flask_wtf import FlaskForm
import secrets
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)

client = MongoClient('mongodb://localhost:27017')
db = client['test_db']  # Замените 'your_database_name' на имя вашей базы данных
users_collection = db['users']
groups_collection = db['groups']


@app.route('/home')
def home():
    if 'user' in session:
        return f'Добро пожаловать, {session["user"]}!'
    return 'Домашняя страница'


# ВСЕ модели
class RegistrationForm(FlaskForm):
    username = StringField('Username', [validators.Length(min=4, max=20)])
    password = PasswordField('Password', [
        validators.DataRequired(),
        validators.EqualTo('confirm_password', message='Passwords must match')
    ])
    confirm_password = PasswordField('Confirm Password')
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    username = StringField('Username', [validators.Length(min=4, max=20)])
    password = PasswordField('Password', [validators.DataRequired()])
    submit = SubmitField('Login')

class CreateGroupForm(FlaskForm):
    group_name = StringField('Group Name', [validators.DataRequired()])
    submit = SubmitField('Create Group')

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()

    if request.method == 'POST' and form.validate_on_submit():
        username = form.username.data
        password = form.password.data

        user = users_collection.find_one({'username': username})

        if user and check_password_hash(user['password'], password):
            session['user'] = username
            flash('Вход успешен', 'success')
            return redirect(url_for('home'))
        else:
            flash('Неверные учетные данные', 'danger')

    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()

    if request.method == 'POST' and form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        if users_collection.find_one({'username': username}):
            flash('Пользователь с таким именем уже существует', 'danger')
        else:
            new_user = {'username': username, 'password': hashed_password}
            users_collection.insert_one(new_user)
            flash('Регистрация успешна. Теперь вы можете войти!', 'success')
            return redirect(url_for('login'))

    return render_template('register.html', form=form)


@app.route('/join_group', methods=['GET'])
def show_join_group_form():
    return render_template('join_group.html')

@app.route('/join_group', methods=['POST'])
def submit_join_group_form():
    group_id = request.form.get('group_id')
    return redirect(url_for('join_group', group_id=group_id))


@app.route('/group/<group_id>', methods=['GET', 'POST'])
def join_group(group_id):
    if request.method == 'GET':
        # Обработка GET-запроса (например, отображение информации о группе)
        return render_template('group_info.html', group_id=group_id)

    # Обработка POST-запроса
    if 'user' not in session:
        flash('Для доступа к этой странице вам необходимо войти', 'danger')
        return redirect(url_for('login'))

    user = users_collection.find_one({'username': session['user']})

    if user:
        # Получение информации о группе
        group = groups_collection.find_one({'group_id': group_id})

        if group and len(group.get('members', [])) < 10:
            # Добавление текущего пользователя в группу
            groups_collection.update_one(
                {'group_id': group_id},
                {'$push': {'members': session['user']}}
            )
            flash(f'Вы успешно присоединились к группе с ID {group_id}', 'success')
        elif not group:
            flash('Группа не существует', 'danger')
        else:
            flash('Группа переполнена. Невозможно присоединиться.', 'danger')
    else:
        flash('Ошибка при попытке вступить в группу', 'danger')

    return redirect(url_for('index'))

@app.route('/create_group', methods=['GET', 'POST'])
def create_group():
    if 'user' not in session:
        flash('Для доступа к этой странице вам необходимо войти', 'danger')
        return redirect(url_for('login'))

    form = CreateGroupForm()

    if request.method == 'POST' and form.validate_on_submit():
        group_name = form.group_name.data
        group_id = generate_group_id()  # Генерация уникального group_id
        user = users_collection.find_one({'username': session['user']})

        if user:
            # Получение информации о группе
            group = groups_collection.find_one({'group_name': group_name})

            # Проверка на существование группы и количество участников меньше 10
            if group and len(group.get('members', [])) < 10:
                # Добавление текущего пользователя в группу
                groups_collection.update_one(
                    {'group_name': group_name},
                    {'$push': {'members': session['user']}}
                )
                flash(f'Вы успешно присоединились к группе "{group_name}"', 'success')
            elif not group:
                # Если группы не существует, создаем её и добавляем пользователя
                groups_collection.insert_one({
                    'group_id': group_id,
                    'group_name': group_name,
                    'members': [session['user']]
                })
                flash(f'Группа "{group_name}" успешно создана с ID {group_id}', 'success')
            else:
                flash('Группа переполнена. Невозможно присоединиться.', 'danger')
        else:
            flash('Ошибка при создании группы', 'danger')

    return render_template('create_group.html', form=form)
def generate_group_id():
    while True:
        group_id = random.randint(1000000, 9999999)
        if not groups_collection.find_one({'group_id': group_id}):
            return str(group_id)



if __name__ == '__main__':
    app.run(debug=True)