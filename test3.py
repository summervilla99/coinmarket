from flask import Flask, render_template, flash, request, redirect, session, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import json
import certifi

app = Flask(__name__, static_url_path='/static')
app.secret_key = 'hello'

client = MongoClient('mongodb+srv://jihwan:990423@jihwan.bfelauv.mongodb.net/?retryWrites=true&w=majority', tlsCAFile=certifi.where())
db = client['test1']
users_collection = db['users']
transaction_collection = db['transaction']
coin_market_collection = db['coin_market']
user_selling_collection = db['user_selling']

def initialize_database():
    if transaction_collection.count_documents({}) == 0:
        transaction_collection.insert_one({'balance': 0.0, 'coin_count': 100})

    if coin_market_collection.count_documents({}) == 0:
        coin_market_collection.insert_one({'price': 100.0, 'price_history': []})
    elif 'price_history' not in coin_market_collection.find_one():
        coin_market_collection.update_one({}, {'$set': {'price_history': []}})

    if 'coin_count' not in transaction_collection.find_one():
        transaction_collection.update_one({}, {'$set': {'coin_count': 0}})

    if users_collection.count_documents({}) == 0:
        users_collection.insert_one({'username': 'admin', 'password': 'admin', 'balance': 0.0, 'coin_count': 0})


initialize_database()


def update_user_balance(username):
    user = users_collection.find_one({'username': username})
    if user:
        user_balance = user.get('balance', 0.0)
        session['user_balance'] = float(user_balance)  # Convert balance to float
        session['user_coin_count'] = user.get('coin_count', 0)


@app.route('/static/style.css')
def static_css():
    return app.send_static_file('style.css')


@app.template_filter('tojson')
def tojson(value):
    return json.dumps(value, default=str)

@app.route('/get_coin_price', methods=['GET'])
def get_coin_price():
    coin_price = coin_market_collection.find_one()['price']
    return jsonify({'coin_price': coin_price})


@app.route('/')
def index():
    if 'username' in session:
        return render_template('user_home.html', username=session['username'])
    elif 'get_started' in session and session['get_started']:
        session.pop('get_started', None)
        return render_template('guest_home.html', show_buttons=True)
    else:
        return render_template('guest_home.html', show_buttons=False)
    
    
@app.route('/get_started')
def get_started():
    session['get_started'] = True
    return redirect('/')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = users_collection.find_one({'username': username})

        if user and user['password'] == password:
            session['username'] = username
            update_user_balance(username)
            return redirect('/')
        else:
            return render_template('login.html', error='Invalid username or password')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if users_collection.find_one({'username': username}):
            return render_template('register.html', error='Username already exists')

        users_collection.insert_one({'username': username, 'password': password, 'balance': 0.0, 'coin_count': 0})
        session['username'] = username
        users_collection.update_one({'username': username}, {'$set': {'balance': 0.0, 'coin_count': 0}})
        update_user_balance(username)

        return redirect('/')

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect('/')


@app.route('/spot')
def spot():
    if 'username' in session:
        coin_market = coin_market_collection.find_one()
        coin_price = coin_market['price']
        price_history = coin_market['price_history']
        marketplace = transaction_collection.find_one()
        available_coins = marketplace["coin_count"]
        user_balance = session.get('user_balance', 0.0)
        user_coin_count = session.get('user_coin_count', 0)
        user_selling_posts = list(user_selling_collection.find({}))

        session['user_balance'] = user_balance
        session['user_coin_count'] = user_coin_count
        
        coin_price_param = request.args.get('coin_price')
        if coin_price_param is not None:
            coin_price = float(coin_price_param)

        return render_template(
            'spot.html',
            username=session['username'],
            coin_price=coin_price,
            price_history=price_history,
            available_coins=available_coins,
            user_balance=user_balance,
            user_coin_count=user_coin_count,
            user_selling_posts=user_selling_posts,
        )
    else:
        coin_market = coin_market_collection.find_one()
        coin_price = coin_market['price']
        price_history = coin_market['price_history']
        marketplace = transaction_collection.find_one()
        available_coins = marketplace["coin_count"]
        return render_template(
            'guest_spot.html',
            coin_price=coin_price,
            price_history=price_history,
            available_coins=available_coins
        )


@app.route('/create_sell_order', methods=['POST'])
def create_sell_order():
    if 'username' not in session:
        return redirect('/login')

    selling_price = float(request.form['selling_price'])
    coins_to_sell = int(request.form['amount'])
    user = users_collection.find_one({'username': session['username']})
    user_coin_count = user.get('coin_count', 0)

    if coins_to_sell > user_coin_count:
        return redirect('/spot')

    user_selling_collection.insert_one({
        'username': session['username'],
        'number_of_coins': coins_to_sell,
        'selling_price': selling_price,
        'status': 'open'
    })

    # Update user coin count
    new_user_coin_count = user_coin_count - coins_to_sell
    users_collection.update_one({'username': session['username']}, {'$set': {'coin_count': new_user_coin_count}})

    # Update price history
    coin_price = coin_market_collection.find_one()['price']
    price_history = coin_market_collection.find_one()['price_history']
    price_history.append({'price': coin_price, 'date': datetime.now()})
    coin_market_collection.update_one({}, {'$set': {'price_history': price_history}})

    transaction_collection.update_one({}, {'$inc': {'coin_count': coins_to_sell}})

    return redirect('/spot')


@app.route('/buy_from_user', methods=['POST'])
def buy_from_user():
    if 'username' not in session:
        return redirect('/login')

    sell_order_id = request.form['sell_order_id']
    sell_order = user_selling_collection.find_one({'_id': ObjectId(sell_order_id)})

    if not sell_order or sell_order['status'] != 'open':
        flash('Invalid or closed selling post', 'error')
        return redirect('/spot')
    
    if sell_order['username'] == session['username']:
        flash("This post is yours", 'error')
        return redirect('/spot')

    total_cost = sell_order['number_of_coins'] * sell_order['selling_price']
    buyer = users_collection.find_one({'username': session['username']})
    seller = users_collection.find_one({'username': sell_order['username']})

    if buyer['balance'] < total_cost:
        flash('Insufficient balance', 'error')
        return redirect('/spot')

    # Update buyer's balance and coin count
    new_buyer_balance = buyer['balance'] - total_cost
    new_buyer_coin_count = buyer['coin_count'] + sell_order['number_of_coins']
    users_collection.update_one({'username': session['username']},
                            {'$set': {'balance': new_buyer_balance, 'coin_count': new_buyer_coin_count}})

    # Update seller's balance and coin count
    new_seller_balance = seller['balance'] + total_cost
    new_seller_coin_count = seller['coin_count'] - sell_order['number_of_coins']
    users_collection.update_one({'username': sell_order['username']},
                            {'$set': {'balance': new_seller_balance, 'coin_count': new_seller_coin_count}})

    # Delete the sold selling post
    user_selling_collection.delete_one({'_id': ObjectId(sell_order_id)})

    # Update price history
    coin_price = coin_market_collection.find_one()['price']
    price_history = coin_market_collection.find_one()['price_history']
    price_history.append({'price': coin_price, 'date': datetime.now()})
    coin_market_collection.update_one({}, {'$set': {'price_history': price_history}})

    # Update current coin price
    # coin_market_collection.update_one({}, {'$set': {'price': coin_price}})
    coin_price = sell_order['selling_price']
    coin_market_collection.update_one({}, {'$set': {'price': coin_price}})
    
    #Update available coin in marketplace
    marketplace = transaction_collection.find_one()
    marketplace_coin_count = marketplace['coin_count']
    new_marketplace_coin_count = marketplace_coin_count - sell_order['number_of_coins']
    transaction_collection.update_one({}, {'$set': {'coin_count': new_marketplace_coin_count}})

    # Update session data
    session['user_balance'] = new_buyer_balance
    session['user_coin_count'] = new_buyer_coin_count

    flash('Purchase successful', 'success')
    return redirect('/spot?coin_price=' + str(coin_price))


@app.route('/buy', methods=['POST'])
def buy_coins():
    if 'username' not in session:
        return redirect('/login')

    coins_to_buy = int(request.form['amount'])
    coin_price = coin_market_collection.find_one()['price']
    marketplace = transaction_collection.find_one()
    marketplace_coin_count = marketplace['coin_count']
    user = users_collection.find_one({'username': session['username']})
    user_balance = user.get('balance', 0.0)
    user_coin_count = user.get('coin_count', 0)

    total_cost = coins_to_buy * coin_price

    if total_cost > user_balance or coins_to_buy > marketplace_coin_count:
        return redirect('/spot')

    # Update user balance and coin count
    new_user_balance = user_balance - total_cost
    new_user_coin_count = user_coin_count + coins_to_buy
    users_collection.update_one({'username': session['username']},
                                {'$set': {'balance': new_user_balance, 'coin_count': new_user_coin_count}})
    users_collection.update_one({'username': session['username']}, 
                                {'$inc': {'coin_count': coins_to_buy}})

    # Update marketplace coin count
    new_marketplace_coin_count = marketplace_coin_count - coins_to_buy
    transaction_collection.update_one({}, {'$set': {'coin_count': new_marketplace_coin_count}})
    
    # Update price history
    coin_price = 100
    price_history = coin_market_collection.find_one()['price_history']
    price_history.append({'price': coin_price, 'date': datetime.now()})
    coin_market_collection.update_one({}, {'$set': {'price_history': price_history}})
    coin_market_collection.update_one({}, {'$set': {'price': coin_price}})

    # Update session data
    session['user_balance'] = new_user_balance
    session['user_coin_count'] = new_user_coin_count

    return redirect('/spot?coin_price=' + str(coin_price))


@app.route('/sell', methods=['POST'])
def sell_coins():
    if 'username' not in session:
        return redirect('/login')

    coins_to_sell = int(request.form['amount'])
    coin_price = coin_market_collection.find_one()['price']
    marketplace = transaction_collection.find_one()
    marketplace_coin_count = marketplace['coin_count']
    user = users_collection.find_one({'username': session['username']})
    user_balance = user.get('balance', 0.0)
    user_coin_count = user.get('coin_count', 0)

    if coins_to_sell > user_coin_count:
        return flash("You need more coin to sell")
    # redirect('/spot')

    total_earning = coins_to_sell * coin_price

    new_user_balance = user_balance + total_earning
    new_user_coin_count = user_coin_count - coins_to_sell
    new_marketplace_coin_count = marketplace_coin_count + coins_to_sell

    # users_collection.update_one({'username': session['username']},
    #                             {'$set': {'balance': new_user_balance}, '$inc': {'coin_count': new_user_coin_count}})
    transaction_collection.update_one({}, {'$set': {'coin_count': new_marketplace_coin_count}})
    coin_market_collection.update_one({}, {'$set': {'price': coin_price}})
    user_selling_collection.insert_one(
        {'username': session['username'], 'number_of_coins': coins_to_sell, 'selling_price': coin_price})

    # Update seller's coin count
    new_seller_coin_count = user_coin_count - coins_to_sell
    users_collection.update_one(
        {'username': session['username']},
        {'$set': {'coin_count': new_seller_coin_count}}
    )

    # Update price history
    coin_price = coin_market_collection.find_one()['price']
    price_history = coin_market_collection.find_one()['price_history']
    price_history.append({'price': coin_price, 'date': datetime.now()})
    coin_market_collection.update_one({}, {'$set': {'price_history': price_history}})
    coin_market_collection.update_one({}, {'$set': {'price': coin_price}})
    
    return redirect('/spot')


@app.route('/myPage', methods=['GET', 'POST'])
def my_page():
    if 'username' not in session:
        return redirect('/login')

    if request.method == 'POST':
        if 'add' in request.form:
            amount = float(request.form['amount'])
            user = users_collection.find_one({'username': session['username']})
            balance = user.get('balance', 0.0)
            new_balance = balance + amount
            users_collection.update_one({'username': session['username']}, {'$set': {'balance': new_balance}})
            update_user_balance(session['username'])
            return redirect('/myPage')
        elif 'withdraw' in request.form:
            amount = float(request.form['amount'])
            user = users_collection.find_one({'username': session['username']})
            balance = user.get('balance', 0.0)

            if balance < amount:
                error_message = 'Insufficient balance!'
                return render_template('myPage.html', error=error_message)

            new_balance = balance - amount
            users_collection.update_one({'username': session['username']}, {'$set': {'balance': new_balance}})
            update_user_balance(session['username'])
            return redirect('/myPage')
    else:
        user = users_collection.find_one({'username': session['username']})
        balance = user.get('balance', 0.0)
        update_user_balance(session['username'])
        return render_template('myPage.html', user_balance=balance)


if __name__ == '__main__':
    app.run(debug=False)