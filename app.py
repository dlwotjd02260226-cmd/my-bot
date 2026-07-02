import streamlit as st
import requests
import streamlit.components.v1 as components

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

price = get_price()

# 1. 차트 (최상단)
components.html("""
<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script>
<script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>
""", height=260)

# 2. 자산 계산 및 표시
total_pos_pnl = 0
for p in st.session_state.positions:
    diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
    total_pos_pnl += (diff / p['entry']) * p['margin'] * p['lev']

st.metric("실시간 자산 (USDT)", f"{st.session_state.balance + total_pos_pnl:,.2f}", f"{total_pos_pnl:+.2f} USDT")

# 3. 포지션 상세
for p in st.session_state.positions:
    st.info(f"[{p['type']}] 진입가: {p['entry']:.0f} | 수익: {((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']:+.2f}")

# 4. 컨트롤
lev = st.slider("레버리지", 1, 125, 10)
amt = st.number_input("증거금(USDT)", value=100)
c1, c2, c3 = st.columns(3)

if c1.button("롱 진입"):
    st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev})
    st.session_state.balance -= amt
    st.session_state.logs.append(f"롱 진입({lev}배)")
    st.rerun()
if c2.button("숏 진입"):
    st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev})
    st.session_state.balance -= amt
    st.session_state.logs.append(f"숏 진입({lev}배)")
    st.rerun()
if c3.button("포지션 종료"):
    st.session_state.balance += (amt + total_pos_pnl)
    st.session_state.positions = []
    st.rerun()

# 5. 초기화 및 로그
if st.button("🔄 가상머니 초기화"):
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.rerun()

st.caption("최근 거래 로그")
for log in reversed(st.session_state.logs[-3:]):
    st.text(log)
