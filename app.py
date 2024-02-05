from flask import Flask, render_template, request, redirect, url_for, flash, session,jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from wtforms import StringField, PasswordField, SubmitField, validators,Form
from flask_wtf import FlaskForm
import secrets, random
from flask_socketio import SocketIO, emit
from bson import ObjectId



app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
socketio = SocketIO(app)

client = MongoClient('mongodb://localhost:27017')
db = client['test_db']
users_collection = db['users']
groups_collection = db['groups']


@app.route('/api/home')
def home():
    # if 'user' in session:
        return jsonify(message="Домашняя страница")
    # return 'Домашняя страница'


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

from flask import request, jsonify

# ...

@app.route('/api/login', methods=['POST'])
def login():
    if request.is_json:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        user = users_collection.find_one({'username': username})

        if user and check_password_hash(user['password'], password):
            session['user'] = username
            return jsonify({'message': 'Вход успешен'}), 200
        else:
            return jsonify({'message': 'Неверные учетные данные'}), 401

    return jsonify({'message': 'Неправильный формат данных'}), 400

@app.route('/api/register', methods=['POST'])
def register():
    if request.is_json:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        if users_collection.find_one({'username': username}):
            return jsonify({'message': 'Пользователь с таким именем уже существует'}), 400
        else:
            new_user = {'username': username, 'password': hashed_password, 'groups': []}
            users_collection.insert_one(new_user)
            return jsonify({'message': 'Регистрация успешна. Теперь вы можете войти!'}), 200

    return jsonify({'message': 'Неправильный формат данных'}), 400


@app.route('/api/logout', methods=['POST'])
def logout():
    if 'user' in session:
        session.pop('user')
        return jsonify({'message': 'Вы успешно вышли из аккаунта'}), 200
    else:
        return jsonify({'message': 'Вы не вошли в аккаунт'}), 401



@socketio.on('connect', namespace='/group')
def handle_connect():
    print('Client connected')


@app.route('/api/create_group', methods=['POST'])
def create_group():
    if request.is_json:
        data = request.get_json()
        group_name = data.get('group_name')
        theme = data.get('theme')
        max_members = int(data.get('max_members', 8))

        user_name = data.get('username')
        group_id = generate_group_id()

        existing_group = groups_collection.find_one({'group_id': group_id})

        if existing_group:
            if len(existing_group.get('members', [])) < max_members:
                groups_collection.update_one(
                    {'group_id': group_id},
                    {'$addToSet': {'members': user_name}}
                )
            else:
                return jsonify({'message': 'Достигнут лимит участников в группе'}), 400
        else:
            # При создании группы
            groups_collection.insert_one({
                'group_id': group_id,
                'group_name': group_name,
                'theme': theme,
                'members': [{'username': user_name or ""}],
                'max_members': max_members
            })

        # Обновление документа пользователя новым идентификатором группы
        users_collection.update_one(
            {'username': user_name},
            {'$addToSet': {'groups': group_id}}
        )

        # Получение обновленной информации о группе
        updated_group = groups_collection.find_one({'group_id': group_id})

        # Проверка, есть ли у группы поле 'members', иначе установка пустого массива
        members = updated_group.get('members', [])

        return jsonify({
            'group_id': group_id,
            'group_name': group_name,
            'theme': theme,
            'members': members
        }), 200

    return jsonify({'message': 'Неправильный формат данных'}), 400


# Страница чата в группе
@app.route('/api/delete_group/<int:group_id>', methods=['DELETE'])
def delete_group(group_id):
    user_name = session.get('user')

    group = groups_collection.find_one({'group_id': group_id})

    if group and user_name in group['members']:
        # Удаление группы из коллекции
        groups_collection.delete_one({'group_id': group_id})

        # Удаление группы из массива групп в документах пользователей
        users_collection.update_many(
            {'groups': group_id},
            {'$pull': {'groups': group_id}}
        )

        socketio.emit('group_deleted', {'group_id': group_id}, namespace='/group')

        return jsonify({'message': 'Группа успешно удалена'}), 200
    else:
        abort(403)   # Forbidden


@app.route('/api/group/<int:group_id>', methods=['GET'])
def api_get_group(group_id):
    group = groups_collection.find_one({'group_id': group_id})
    if group:
        return jsonify({
            'group_id': group['group_id'],
            'group_name': group['group_name'],
            'theme': group['theme'],
            'members': group['members'],
        }), 200
    else:
        return jsonify({'error': 'Группа не найдена'}), 404

# ...

@app.route('/api/group/<int:group_id>', methods=['POST'])
def group_chat(group_id):
    if request.is_json:
        data = request.get_json()
        user_id = data.get('user_id')  # Принимаем _id пользователя
        user_name = data.get('user_name')

        # Проверка, является ли введенный _id ObjectId
        try:
            user_id = ObjectId(user_id)
            user = users_collection.find_one({'_id': user_id})
        except Exception as e:
            user = users_collection.find_one({'username': user_name})

        group = groups_collection.find_one({'group_id': group_id})

        if user:
            members = group.get('members', [])
            if len(members) < 8:
                # Проверка, есть ли пользователь уже в группе
                if user['username'] not in members:
                    groups_collection.update_one(
                        {'group_id': group_id},
                        {'$push': {'members': {'username': user_name, 'status': 'pending'}}}
                    )

                    # Обновление массива групп в документе пользователя
                    users_collection.update_one(
                        {'_id': user['_id']},
                        {'$addToSet': {'groups': group_id}}
                    )

                    socketio.emit('user_joined', {'user_name': user['username']}, namespace='/group', room=group_id)

                    return jsonify({'success': True}), 200
                else:
                    return jsonify({'error': 'Пользователь уже состоит в группе'}), 400
            else:
                return jsonify({'error': 'Лимит участников в группе достигнут'}), 400
        else:
            return jsonify({'error': 'Пользователь не найден'}), 404

    return jsonify({'error': 'Неправильный формат данных'}), 400

# ...


def generate_group_id():
    while True:
        group_id = random.randint(1000000, 9999999)
        if not groups_collection.find_one({'group_id': group_id}):
            return group_id



@socketio.on('update_action', namespace='/group')
def handle_update_action(data):
    user_name = data.get('user_name')
    group_id = data.get('group_id')
    your_action = data.get('your_action')

    # Обновление действий пользователя в группе
    groups_collection.update_one(
        {'group_id': group_id},
        {'$set': {f'user_actions.{user_name}': your_action}}
    )

    emit('action_updated', {'user_name': user_name, 'your_action': your_action}, room=group_id)

if __name__ == '__main__':
    app.run(port=3000, debug=True)
    # socketio.run(app, debug=True)
