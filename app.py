import streamlit as st
import requests
import streamlit.components.v1 as components
from datetime import datetime

st.set_page_config(page_title="BTC Bot", layout="centered")

# 세션 초기화
if 'balance' not in st.session_state: st.session_state.balance = 10000.0
if 'positions' not in st.session_state: st.session_state.positions = [] 
if 'logs' not in st.session_state: st.session_state.logs = []

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=2)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

price = get_price()

# 자산 계산
total_pos_val = sum([p['amt'] * (price if p['type'] == '롱' else (2*p['entry'] - price)) for p in st.session_state.positions])
total_asset = st.session_state.balance + total_pos_val
pnl_amt = total_asset - 10000
pnl_pct = (pnl_amt / 10000) * 100

st.metric("실시간 자산 (USDT)", f"{total_asset:,.2f}", f"{pnl_pct:+.2f}% ({pnl_amt:+.2f} USDT)")

# 청산가 표시
if st.session_state.positions:
    liq = min([p['entry'] * (1 - (0.8 / 20)) if p['type'] == '롱' else p['entry'] * (1 + (0.8 / 20)) for p in st.session_state.positions])
    st.error(f"⚠️ 예상 청산가: {liq:,.2f} USDT")

# 컨트롤
lev = st.slider("레버리지", 1, 125, 1)
amt = st.number_input("금액 (USDT)", min_value=1, value=1000)

c1, c2, c3 = st.columns(3)
if c1.button("롱 진입"):
    if st.session_state.balance >= amt:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'amt': (amt*lev)/price})
        st.session_state.balance -= amt
        st.session_state.logs.append(f"롱({lev}배) @ {price:,.0f}")
        st.rerun()
if c2.button("숏 진입"):
    if st.session_state.balance >= amt:
        st.session_state.positions.append({'type': '숏', 'entry': price, 'amt': (amt*lev)/price})
        st.session_state.balance -= amt
        st.session_state.logs.append(f"숏({lev}배) @ {price:,.0f}")
        st.rerun()
if c3.button("포지션 종료"):
    for p in st.session_state.positions:
        profit = (p['amt'] * price) if p['type'] == '롱' else (p['amt'] * (2*p['entry'] - price))
        st.session_state.balance += profit
    st.session_state.positions = []
    st.session_state.logs.append(f"종료 @ {price:,.0f}")
    st.rerun()

# 차트
components.html('<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({"width":"100%","height":
