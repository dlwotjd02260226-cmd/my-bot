import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components

st.set_page_config(page_title="BTC Bot", layout="centered")

# --- 데이터 상태 관리 ---
if 'balance' not in st.session_state: st.session_state.balance = 10000.0
if 'positions' not in st.session_state: st.session_state.positions = [] 
if 'logs' not in st.session_state: st.session_state.logs = []

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=0.3)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

price = get_price()
st.title("BTC 실시간 트레이딩")

# 차트
components.html("""<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>""", height=260)

# 실시간 평가 손익 계산
total_pos_pnl = 0
for p in st.session_state.positions:
    diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
    total_pos_pnl += (diff / p['entry']) * p['margin'] * p['lev']

# UI 배치
# 총 자산: 현재 가용 잔액 + 평가 손익
current_total = st.session_state.balance + total_pos_pnl
st.metric("실시간 총 자산 (USDT)", f"{current_total:,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{current_total - 10000.0:+.2f} USDT")
st.write(f"현재가: {price:,.2f} USDT")

# 컨트롤
col_a, col_b = st.columns(2)
lev = col_a.slider("레버리지", 1, 125, 10, key="slider_lev")
amt = col_b.number_input("증거금(USDT)", value=100.0, key="input_amt")

c1, c2 = st.columns(2)
if c1.button("롱 진입", key="btn_long"):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev})
        st.session_state.balance -= amt
        st.rerun()

if c2.button("숏 진입", key="btn_short"):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev})
        st.session_state.balance -= amt
        st.rerun()

# 1. 포지션 종료 (가상머니 유지, 포지션만 정리)
if st.button("❌ 포지션 종료", key="btn_close"):
    for p in st.session_state.positions:
        pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
        log_entry = f"[{datetime.now().strftime('%H:%M:%S')}] {p['type']} 진입@{p['entry']:.1f} → 종료@{price:.1f} | 결과: {pnl:+.2f} USDT"
        st.session_state.logs.append(log_entry)
        # 잔액에 증거금 + 수익 합산
        st.session_state.balance += (p['margin'] + pnl)
    st.session_state.positions = []
    st.rerun()

# 2. 가상머니 초기화 (잔액과 로그를 완전히 리셋)
if st.button("🔄 가상머니 초기화", key="btn_reset_all"):
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.rerun()

# 로그 출력
st.subheader("거래 로그")
for log in reversed(st.session_state.logs[-10:]):
    st.text(log)

time.sleep(0.3)
st.rerun()
