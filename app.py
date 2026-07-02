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

# 2. 버튼 구역 (루프 밖으로 배치하여 오류 원천 차단)
price = get_price()
col1, col2 = st.columns(2)
with col1:
    if st.button("롱 진입", key="btn_long"):
        st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': 100.0, 'lev': 10})
        st.rerun()
with col2:
    if st.button("숏 진입", key="btn_short"):
        st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': 100.0, 'lev': 10})
        st.rerun()

# 포지션 종료 버튼 하나로 통합
if st.button("❌ 포지션 전체 종료 및 정산", key="btn_close_all"):
    total_pos_pnl = 0
    for p in st.session_state.positions:
        diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
        total_pos_pnl += (diff / p['entry']) * p['margin'] * p['lev']
    st.session_state.total_realized_pnl += total_pos_pnl
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 정산: {total_pos_pnl:+.2f} USDT")
    st.session_state.positions = []
    st.rerun()

# 3. 실시간 데이터 표시
total_pos_pnl = 0
for p in st.session_state.positions:
    diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
    total_pos_pnl += (diff / p['entry']) * p['margin'] * p['lev']

# 시작금 10,000 + 누적 수익 + 현재 평가 수익
current_asset = 10000.0 + st.session_state.total_realized_pnl + total_pos_pnl

st.metric("실시간 총 자산 (USDT)", f"{current_asset:,.2f}", f"{st.session_state.total_realized_pnl + total_pos_pnl:+.2f} USDT")

for p in st.session_state.positions:
    pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
    st.info(f"[{p['type']}] 수익: {pnl:+.2f} USDT")

# 4. 초기화
if st.button("🔄 가상머니 초기화", key="btn_reset"):
    st.session_state.total_realized_pnl = 0.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.rerun()

st.caption("최근 거래 로그")
for log in reversed(st.session_state.logs[-5:]):
    st.text(log)
