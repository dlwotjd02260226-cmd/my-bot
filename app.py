import streamlit as st
import requests
import streamlit.components.v1 as components
from datetime import datetime

st.set_page_config(page_title="BTC Bot", layout="centered")

# 세션 초기화 (데이터 유지)
if 'balance' not in st.session_state: st.session_state.balance = 10000.0
if 'positions' not in st.session_state: st.session_state.positions = [] 
if 'logs' not in st.session_state: st.session_state.logs = []

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=0.5)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

st.title("BTC 실시간 트레이딩")

price = get_price()

# 차트
components.html("""
<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script>
<script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>
""", height=260)

# 수익 계산
total_pnl = 0
for p in st.session_state.positions:
    diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
    total_pnl += (diff / p['entry']) * p['margin'] * p['lev']

# 자산 표시 (10,000 + 손익)
st.metric("실시간 총 자산 (USDT)", f"{10000.0 + total_pnl:,.2f}", f"{total_pnl:+.2f} USDT")

# 컨트롤
lev = st.slider("레버리지", 1, 125, 10, key="lev_s")
amt = st.number_input("증거금(USDT)", value=100, key="amt_i")

c1, c2, c3 = st.columns(3)
if c1.button("롱 진입", key="btn_long"):
    st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev})
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 롱 진입 @ {price:.0f}")
    st.rerun()

if c2.button("숏 진입", key="btn_short"):
    st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev})
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 숏 진입 @ {price:.0f}")
    st.rerun()

if c3.button("포지션 종료", key="btn_close"):
    for p in st.session_state.positions:
        pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
        st.session_state.logs.append(
            f"[{datetime.now().strftime('%H:%M:%S')}] 종료: {p['type']} @ {price:.0f} | "
            f"진입가: {p['entry']:.0f} | 결과: {pnl:+.2f} USDT"
        )
    st.session_state.positions = []
    st.rerun()

# 포지션 상세
for p in st.session_state.positions:
    pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
    st.info(f"[{p['type']}] 진입가: {p['entry']:.0f} | 수익: {pnl:+.2f} USDT")

# 초기화 버튼
if st.button("🔄 가상머니 초기화", key="btn_reset"):
    st.session_state.positions = []
    st.session_state.logs = []
    st.rerun()

# 로그 기록 (자세히)
st.caption("거래 상세 로그")
for log in reversed(st.session_state.logs[-10:]):
    st.text(log)
