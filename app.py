from flask import Flask, render_template_string
import requests

app = Flask(__name__)
user_data = {"balance": 10000.0, "btc_amount": 0.0, "history": []}

@app.route('/buy')
def buy():
    try:
        url = "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT"
        price = float(requests.get(url).json()['data'][0]['last'])
        if user_data["balance"] >= 100:
            amount = 100 / price
            user_data["btc_amount"] += amount
            user_data["balance"] -= 100
            user_data["history"].append({'type': '매수', 'price': price, 'amount': amount})
    except: pass
    return '<meta http-equiv="refresh" content="0;url=/">'

@app.route('/sell')
def sell():
    try:
        url = "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT"
        price = float(requests.get(url).json()['data'][0]['last'])
        if user_data["btc_amount"] > 0:
            user_data["history"].append({'type': '매도', 'price': price, 'amount': user_data["btc_amount"]})
            user_data["balance"] += user_data["btc_amount"] * price
            user_data["btc_amount"] = 0
    except: pass
    return '<meta http-equiv="refresh" content="0;url=/">'

@app.route('/')
def home():
    try:
        url = "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT"
        current_price = float(requests.get(url).json()['data'][0]['last'])
        last_buy = user_data['history'][-1]['price'] if user_data['history'] and user_data['btc_amount'] > 0 else current_price
        profit_amt = (current_price - last_buy) * user_data['btc_amount'] if user_data['btc_amount'] > 0 else 0
        profit_pct = ((current_price - last_buy) / last_buy) * 100 if user_data['btc_amount'] > 0 else 0
    except: current_price, last_buy, profit_amt, profit_pct = 0, 0, 0, 0

    # 따옴표 3개(triple quotes) 대신 '+'로 연결하여 에러 방지
    html = '<html><body style="font-family:sans-serif; padding:10px; margin:0;">'
    html += '<h2>BTC 실시간 대시보드</h2>'
    html += '<iframe src="https://www.tradingview.com/chart/?symbol=BTCUSDT" width="100%" height="300px" frameborder="0"></iframe>'
    html += '<div style="display:flex; gap:10px; margin:15px 0;">'
    html += '<a href="/buy" style="flex:1"><button style="width:100%; padding:15px; background:#0f9d58; color:white; border:none; border-radius:5px;">매수</button></a>'
    html += '<a href="/sell" style="flex:1"><button style="width:100%; padding:15px; background:#a52714; color:white; border:none; border-radius:5px;">매도</button></a></div>'
    html += '<div style="background:#f0f0f0; padding:15px; border-radius:10px;">'
    html += '<div>보유 상태: ' + (("매수 중 (진입가: " + "{:.2f}".format(last_buy) + ")") if user_data['btc_amount'] > 0 else "대기 중") + '</div>'
    html += '<div style="font-size:26px; font-weight:bold; color:' + ('#008000' if profit_amt >= 0 else '#FF0000') + '">'
    html += "{:+.2f} USDT ({:+.2f}%)".format(profit_amt, profit_pct) + '</div>'
    html += '<div>현재가: ' + "{:.2f}".format(current_price) + ' | 잔고: ' + "{:.2f}".format(user_data['balance']) + ' USDT</div></div>'
    html += '<h3>거래 내역</h3><table style="width:100%; border-collapse:collapse; font-size:14px;">'
    html += '<tr style="background:#ddd;"><th>타입</th><th>가격</th><th>수량</th></tr>'
    html += ''.join(['<tr style="border-bottom:1px solid #ccc; text-align:center;"><td>'+h['type']+'</td><td>'+"{:.2f}".format(h['price'])+'</td><td>'+"{:.4f}".format(h['amount'])+'</td></tr>' for h in reversed(user_data['history'])])
    html += '</table></body></html>'
    return html

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
