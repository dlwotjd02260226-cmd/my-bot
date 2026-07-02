import streamlit as st
import requests
import streamlit.components.v1 as components
import time
from datetime import datetime

st.set_page_config(page_title="BTC Bot", layout="centered")

# 세션 초기화
if 'balance' not in st.session_state: st.session_state.balance = 10000.0
if 'positions' not in st.session_state: st.session_state.positions = [] 
if 'logs' not in st.session_state: st.session_state.logs = []

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=0.5)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

# 1. 차트 (맨 위)
components.html("""
<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script>
<script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>
""", height=260)

# 2. 실시간 정보
price = get_price()
total_pos_pnl = 0
for p in st.session_state.positions:
    diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
    total_pos_pnl += (diff / p['entry']) * p['margin'] * p['lev']

st.metric("실시간 자산 (USDT)", f"{st.session_state.balance + total_pos_pnl:,.2f}", f"{total_pos_pnl:+.2f} USDT")

# 포지션 정보
for p in st.session_state.positions:
    pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
    st.info(f"[{p['type']}] 진입가: {p['entry']:.0f} | 수익: {pnl:+.2f} USDT")

# 3. 컨트롤 버튼 (key를 부여하여 중복 ID 오류 방지)
lev = st.slider("레버리지", 1, 125, 10, key="lev_slider")
amt = st.number_input("증거금(USDT)", value=100, key="amt_input")

c1, c2, c3 = st.columns(3)
if c1.button("롱 진입", key="long_btn"):
    st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev})
    st.session_state.balance -= amt
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 롱 진입({lev}배)")
    st.rerun()

if c2.button("숏 진입", key="short_btn"):
    st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev})
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 숏 진입({lev}배)")
    st.session_state.balance -= amt
    st.rerun()

if c3.button("포지션 종료", key="close_btn"):
    st.session_state.balance += (amt + total_pos_pnl)
    st.session_state.positions = []
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 포지션 종료")
    st.rerun()

# 4. 로그 및 초기화
st.caption("최근 거래 로그")
for log in reversed(st.session_state.logs[-5:]):
    st.text(log)

if st.button("🔄 가상머니 초기화", key="reset_btn"):
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.rerun()
