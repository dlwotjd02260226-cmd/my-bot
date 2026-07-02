import streamlit as st
import requests
import streamlit.components.v1 as components
import time
from datetime import datetime

st.set_page_config(page_title="BTC Bot", layout="centered")

if 'balance' not in st.session_state: st.session_state.balance = 10000.0
if 'positions' not in st.session_state: st.session_state.positions = []
if 'logs' not in st.session_state: st.session_state.logs = []

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=0.3)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

st.title("BTC 실시간 트레이딩")

# 1. 차트
components.html("""
<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script>
<script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>
""", height=260)

# 2. 실시간 정보 업데이트 자리 (루프용)
placeholder = st.empty()

# 3. 컨트롤 버튼
lev = st.slider("레버리지", 1, 125, 10, key="lev")
amt = st.number_input("증거금(USDT)", value=100, key="amt")
c1, c2, c3 = st.columns(3)

if c1.button("롱 진입", key="long"):
    st.session_state.positions.append({'type': '롱', 'entry': get_price(), 'margin': amt, 'lev': lev})
    st.session_state.balance -= amt
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 롱 진입({lev}배)")
    st.rerun()
if c2.button("숏 진입", key="short"):
    st.session_state.positions.append({'type': '숏', 'entry': get_price(), 'margin': amt, 'lev': lev})
    st.session_state.balance -= amt
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 숏 진입({lev}배)")
    st.rerun()
if c3.button("포지션 종료", key="close"):
    price = get_price()
    for p in st.session_state.positions:
        diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
        pnl = (diff / p['entry']) * p['margin'] * p['lev']
        st.session_state.balance += (p['margin'] + pnl)
    st.session_state.positions = []
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 포지션 종료")
    st.rerun()

# 4. 고속 업데이트 루프
while True:
    price = get_price()
    total_pos_pnl = 0
    with placeholder.container():
        # 평가 자산 = 현재 잔고(진입 제외 금액) + 현재 포지션 평가액
        for p in st.session_state.positions:
            diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
            total_pos_pnl += (diff / p['entry']) * p['margin'] * p['lev']
        
        # 시작금 잔액 별도 표시
        st.metric("가용 잔액 (USDT)", f"{st.session_state.balance:,.2f}")
        st.metric("평가 자산 (USDT)", f"{st.session_state.balance + total_pos_pnl:,.2f}", f"{total_pos_pnl:+.2f} USDT")
        st.write(f"현재가: {price:,.2f} USDT")

    # 5. 초기화 버튼
    if st.button("🔄 가상머니 초기화", key="reset"):
        st.session_state.balance = 10000.0
        st.session_state.positions = []
        st.session_state.logs = []
        st.rerun()

    # 로그
    st.caption("최근 거래 로그")
    for log in reversed(st.session_state.logs[-5:]):
        st.text(log)
    
    time.sleep(0.15) # 0.15초 단위로 극대화된 반응 속도
