import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components

st.set_page_config(page_title="BTC Bot", layout="centered")

# --- 강력한 세션 유지 전략 ---
if 'init' not in st.session_state:
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.session_state.init = True

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=0.3)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

price = get_price()
st.title("BTC 실시간 트레이딩")

# 차트
components.html("""<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>""", height=260)

# 실시간 포지션 평가 손익 계산 (손익만)
total_pos_pnl = sum(((price - p['entry']) if p['type']=='롱' else (p['entry']-price))/p['entry']*p['margin']*p['lev'] for p in st.session_state.positions)

# --- 변경된 계산 방식 ---
# 1. 현재 변동 금액(USDT)은 오직 포지션 평가 손익만 보여줌
fluctuation = total_pos_pnl

# 2. 실시간 총 자산은 가용 잔액(balance) + 평가 손익
current_total = st.session_state.balance + total_pos_pnl

# 화면 출력
st.metric("실시간 총 자산 (USDT)", f"{current_total:,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{fluctuation:+.2f} USDT")

# 컨트롤
col1, col2 = st.columns(2)
lev = col1.slider("레버리지", 1, 125, 10, key="lev")
amt = col2.number_input("증거금(USDT)", value=100.0, key="amt")

if st.button("롱 진입"):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev})
        st.session_state.balance -= amt
        st.rerun()

if st.button("숏 진입"):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev})
        st.session_state.balance -= amt
        st.rerun()

if st.button("❌ 포지션 종료"):
    for p in st.session_state.positions:
        pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {p['type']} 종료: {pnl:+.2f} USDT")
        st.session_state.balance += (p['margin'] + pnl)
    st.session_state.positions = []
    st.rerun()

if st.button("🔄 가상머니 초기화"):
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.rerun()

st.subheader("거래 로그")
for log in reversed(st.session_state.logs[-10:]):
    st.text(log)

time.sleep(0.3)
st.rerun()
