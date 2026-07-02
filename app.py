import streamlit as st
import requests
import streamlit.components.v1 as components
import time
from datetime import datetime, timedelta

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

st.title("BTC 실시간 트레이딩")

# 1. 차트
components.html("""
<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script>
<script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>
""", height=260)

# 2. 실시간 정보 업데이트 루프
placeholder = st.empty()

# 3. 컨트롤러
lev = st.slider("레버리지", 1, 125, 10)
amt = st.number_input("증거금(USDT)", value=100)
c1, c2, c3 = st.columns(3)

if c1.button("롱 진입"):
    if st.session_state.balance >= amt:
        st.session_state.positions.append({'type': '롱', 'entry': get_price(), 'margin': amt, 'lev': lev, 'time': datetime.now()})
        st.session_state.balance -= amt
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 롱 진입({lev}배) | 증거금: {amt}")
        st.rerun()

if c2.button("숏 진입"):
    if st.session_state.balance >= amt:
        st.session_state.positions.append({'type': '숏', 'entry': get_price(), 'margin': amt, 'lev': lev, 'time': datetime.now()})
        st.session_state.balance -= amt
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 숏 진입({lev}배) | 증거금: {amt}")
        st.rerun()

if c3.button("포지션 종료"):
    # 종료 로직: 잔고에 증거금 + 수익금 합산
    for p in st.session_state.positions:
        price = get_price()
        diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
        pnl = (diff / p['entry']) * p['margin'] * p['lev']
        st.session_state.balance += (p['margin'] + pnl)
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 포지션 종료 | 수익: {pnl:+.2f} USDT")
    st.session_state.positions = []
    st.rerun()

# 4. 실시간 데이터 갱신 (루프)
while True:
    price = get_price()
    total_pos_pnl = 0
    with placeholder.container():
        for p in st.session_state.positions:
            diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
            pnl = (diff / p['entry']) * p['margin'] * p['lev']
            total_pos_pnl += pnl
            st.info(f"[{p['type']}] 진입가:{p['entry']:.0f} | 수익:{pnl:+.2f} USDT")
        
        st.metric("실시간 자산 (USDT)", f"{st.session_state.balance + total_pos_pnl:,.2f}", f"{total_pos_pnl:+.2f} USDT")
        st.write(f"현재가: {price:,.2f} USDT")
        
        st.caption("최근 5분간 거래 로그")
        five_min_ago = datetime.now() - timedelta(minutes=5)
        # 로그 필터링 및 출력
        for log in reversed(st.session_state.logs):
            st.text(log)
        
        if st.button("🔄 가상머니 초기화"):
            st.session_state.balance = 10000.0
            st.session_state.positions = []
            st.session_state.logs = []
            st.rerun()
            
    time.sleep(0.5)
