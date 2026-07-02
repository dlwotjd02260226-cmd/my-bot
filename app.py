import streamlit as st
import requests
import time
import json
import os
from datetime import datetime
import streamlit.components.v1 as components

# --- 영구 데이터 저장 로직 ---
DATA_FILE = "trading_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"balance": 10000.0, "positions": [], "logs": []}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# 데이터 불러오기
data = load_data()
if 'balance' not in st.session_state: st.session_state.balance = data["balance"]
if 'positions' not in st.session_state: st.session_state.positions = data["positions"]
if 'logs' not in st.session_state: st.session_state.logs = data["logs"]

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=0.3)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

price = get_price()
st.title("BTC 실시간 트레이딩")

# 차트
components.html("""<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>""", height=260)

# 실시간 평가 손익
total_pos_pnl = sum(((price - p['entry']) if p['type']=='롱' else (p['entry']-price))/p['entry']*p['margin']*p['lev'] for p in st.session_state.positions)

current_total = st.session_state.balance + total_pos_pnl
st.metric("실시간 총 자산 (USDT)", f"{current_total:,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{current_total - 10000.0:+.2f} USDT")

# 컨트롤
col_a, col_b = st.columns(2)
lev = col_a.slider("레버리지", 1, 125, 10, key="slider_lev")
amt = col_b.number_input("증거금(USDT)", value=100.0, key="input_amt")

c1, c2 = st.columns(2)
if c1.button("롱 진입", key="btn_long"):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev})
        st.session_state.balance -= amt
        save_data({"balance": st.session_state.balance, "positions": st.session_state.positions, "logs": st.session_state.logs})
        st.rerun()

if c2.button("숏 진입", key="btn_short"):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev})
        st.session_state.balance -= amt
        save_data({"balance": st.session_state.balance, "positions": st.session_state.positions, "logs": st.session_state.logs})
        st.rerun()

if st.button("❌ 포지션 종료", key="btn_close"):
    for p in st.session_state.positions:
        pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {p['type']} 결과: {pnl:+.2f} USDT")
        st.session_state.balance += (p['margin'] + pnl)
    st.session_state.positions = []
    save_data({"balance": st.session_state.balance, "positions": st.session_state.positions, "logs": st.session_state.logs})
    st.rerun()

if st.button("🔄 가상머니 초기화", key="btn_reset"):
    save_data({"balance": 10000.0, "positions": [], "logs": []})
    st.rerun()

st.subheader("거래 로그")
for log in reversed(st.session_state.logs[-10:]):
    st.text(log)

time.sleep(0.3)
st.rerun()
