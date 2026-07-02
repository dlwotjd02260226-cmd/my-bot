from flask import Flask, render_template, request, redirect
import requests
import os

app = Flask(__name__)
user_data = {"balance": 10000.0, "btc_amount": 0.0}

def get_okx_price():
    try:
        url = "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT"
        return float(requests.get(url, timeout=3).json()['data'][0]['last'])
    except: return 0.0

@app.route('/')
def home():
    return render_template('index.html', price=get_okx_price(), balance=user_data['balance'], btc=user_data['btc_amount'])

@app.route('/trade', methods=['POST'])
def trade():
    amt = float(request.form.get('amount', 0))
    action = request.form.get('action')
    price = get_okx_price()
    if action == 'buy' and user_data['balance'] >= amt:
        user_data['btc_amount'] += amt / price
        user_data['balance'] -= amt
    elif action == 'sell' and user_data['btc_amount'] > 0:
        user_data['balance'] += user_data['btc_amount'] * price
        user_data['btc_amount'] = 0
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
