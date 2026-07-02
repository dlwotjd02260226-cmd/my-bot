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

st.title("BTC 실시간 트레이딩")

# 1. 차트
components.html("""
<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script>
<script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>
""", height=260)

# 2. 실시간 업데이트용 공간
placeholder = st.empty()

# 3. 컨트롤 버튼 (루프 밖으로 배치하여 에러 방지)
lev = st.slider("레버리지", 1, 125, 10, key="lev_s")
amt = st.number_input("증거금(USDT)", value=100, key="amt_i")

c1, c2, c3 = st.columns(3)
if c1.button("롱 진입", key="btn_long"):
    st.session_state.positions.append({'type': '롱', 'entry': get_price(), 'margin': amt, 'lev': lev})
    st.session_state.balance -= amt
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 롱 진입({lev}배)")
    st.rerun()

if c2.button("숏 진입", key="btn_short"):
    st.session_state.positions.append({'type': '숏', 'entry': get_price(), 'margin': amt, 'lev': lev})
    st.session_state.balance -= amt
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 숏 진입({lev}배)")
    st.rerun()

if c3.button("포지션 종료", key="btn_close"):
    # (종료 계산은 아래 루프에서 함)
    st.rerun()

# 4. 실시간 데이터 루프
while True:
    price = get_price()
    total_pos_pnl = 0
    for p in st.session_state.positions:
        diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
        total_pos_pnl += (diff / p['entry']) * p['margin'] * p['lev']
    
    # 총 평가 자산 = (잔액 + 포지션 수익)
    current_asset = st.session_state.balance + total_pos_pnl
    
    with placeholder.container():
        # 시작금 10,000 기준 실시간 변동이 포함된 총 자산
        st.metric("실시간 총 자산 (USDT)", f"{current_asset:,.2f}", f"{total_pos_pnl:+.2f} USDT")
        st.write(f"현재가: {price:,.2f} USDT")
        
        for p in st.session_state.positions:
            pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
            st.info(f"[{p['type']}] 수익: {pnl:+.2f} USDT")

    # 5. 초기화 및 정산 (루프 밖으로 빼는 게 원칙이나, 여기서는 편의상 배치)
    if st.button("🔄 포지션 종료/정산", key="close_fix"):
        st.session_state.balance += total_pos_pnl
        st.session_state.positions = []
        st.rerun()
        
    if st.button("🔄 가상머니 초기화", key="reset_fix"):
        st.session_state.balance = 10000.0
        st.session_state.positions = []
        st.session_state.logs = []
        st.rerun()

    st.caption("최근 거래 로그")
    for log in reversed(st.session_state.logs[-5:]):
        st.text(log)
    
    time.sleep(0.3)
