import streamlit as st
import requests
import streamlit.components.v1 as components
import time
from datetime import datetime

st.set_page_config(page_title="BTC Bot", layout="centered")

# --- 세션 초기화 ---
if 'balance' not in st.session_state: st.session_state.balance = 10000.0
if 'positions' not in st.session_state: st.session_state.positions = [] 
if 'logs' not in st.session_state: st.session_state.logs = []
if 'total_realized_pnl' not in st.session_state: st.session_state.total_realized_pnl = 0.0

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

# 2. 실시간 데이터 갱신 루프
# placeholder를 사용하여 깜빡임 없이 숫자만 갱신
placeholder = st.empty()

# 컨트롤 버튼 (오류 방지를 위해 고유 key 필수 부여)
lev = st.slider("레버리지", 1, 125, 10, key="slider_lev")
amt = st.number_input("증거금(USDT)", value=100.0, key="input_amt")

c1, c2, c3 = st.columns(3)
if c1.button("롱 진입", key="btn_long"):
    st.session_state.positions.append({'type': '롱', 'entry': get_price(), 'margin': amt, 'lev': lev})
    st.rerun()
if c2.button("숏 진입", key="btn_short"):
    st.session_state.positions.append({'type': '숏', 'entry': get_price(), 'margin': amt, 'lev': lev})
    st.rerun()
if c3.button("포지션 전체 종료", key="btn_close_all"):
    # 아래 루프에서 계산된 값을 정산
    st.rerun()

# 3. 실시간 업데이트 루프 (에러 방지를 위해 이 안에는 버튼을 최소화)
while True:
    price = get_price()
    total_pos_pnl = 0
    for p in st.session_state.positions:
        diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
        total_pos_pnl += (diff / p['entry']) * p['margin'] * p['lev']
    
    # [핵심] 시작금 10,000 + 누적 수익 + 실시간 평가 수익
    current_asset = 10000.0 + st.session_state.total_realized_pnl + total_pos_pnl
    
    with placeholder.container():
        st.metric("실시간 총 자산 (USDT)", f"{current_asset:,.2f}", f"{st.session_state.total_realized_pnl + total_pos_pnl:+.2f} USDT")
        st.write(f"현재가: {price:,.2f} USDT")
        
        for p in st.session_state.positions:
            pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
            st.info(f"[{p['type']}] 수익: {pnl:+.2f} USDT")

    # 정산 버튼과 초기화 버튼은 루프 밖에서 동작하도록 분리 또는 고유 키 부여
    if st.button("🔄 포지션 정산하기", key="btn_settle"):
        st.session_state.total_realized_pnl += total_pos_pnl
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 정산: {total_pos_pnl:+.2f} USDT")
        st.session_state.positions = []
        st.rerun()
    
    if st.button("🔄 가상머니 초기화", key="btn_reset_all"):
        st.session_state.total_realized_pnl = 0.0
        st.session_state.positions = []
        st.session_state.logs = []
        st.rerun()

    st.caption("최근 거래 로그")
    for log in reversed(st.session_state.logs[-5:]):
        st.text(log)
    
    time.sleep(0.3)
