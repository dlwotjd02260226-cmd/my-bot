import streamlit as st
import requests
import streamlit.components.v1 as components
import time
from datetime import datetime

st.set_page_config(page_title="BTC Bot", layout="centered")

# 세션 초기화 (데이터 영구 유지)
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

# 실시간 업데이트를 위한 공간
placeholder = st.empty()

# 컨트롤 버튼 (루프 밖)
lev = st.slider("레버리지", 1, 125, 10, key="lev_s")
amt = st.number_input("증거금(USDT)", value=100, key="amt_i")
c1, c2, c3 = st.columns(3)

if c1.button("롱 진입", key="btn_long"):
    st.session_state.positions.append({'type': '롱', 'entry': get_price(), 'margin': amt, 'lev': lev})
    st.rerun()
if c2.button("숏 진입", key="btn_short"):
    st.session_state.positions.append({'type': '숏', 'entry': get_price(), 'margin': amt, 'lev': lev})
    st.rerun()
if c3.button("포지션 종료", key="btn_close"):
    st.rerun()

# 2. 실시간 루프 (투명한 데이터 공개)
while True:
    price = get_price()
    total_pos_pnl = 0
    for p in st.session_state.positions:
        diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
        total_pos_pnl += (diff / p['entry']) * p['margin'] * p['lev']
    
    current_asset = 10000.0 + st.session_state.total_realized_pnl + total_pos_pnl
    
    with placeholder.container():
        # 투명한 시각화 (누적 수익 표시)
        st.metric("실시간 총 자산 (USDT)", f"{current_asset:,.2f}", f"{st.session_state.total_realized_pnl + total_pos_pnl:+.2f} USDT")
        st.write(f"현재 총 누적 수익: {st.session_state.total_realized_pnl + total_pos_pnl:+.2f} USDT")
        
        for p in st.session_
