import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components

st.set_page_config(page_title="BTC Bot", layout="centered")

# --- 데이터 상태 관리 ---
if 'balance' not in st.session_state: st.session_state.balance = 10000.0
if 'positions' not in st.session_state: st.session_state.positions = [] 

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

# [핵심] 계산 방식 교정
# 1. 변동 금액: 현재 열려있는 포지션들의 순수익/손실 합계
fluctuation = total_pos_pnl 

# 2. 실시간 총 자산: 시작금(10,000) + 변동 금액
total_asset = 10000.0 + fluctuation

# UI 표시 (위치를 완전히 교체)
st.metric("실시간 총 자산 (USDT)", f"{total_asset:,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{fluctuation:+.2f} USDT")

st.write(f"현재가: {price:,.2f} USDT")

# 컨트롤
col_a, col_b = st.columns(2)
lev = col_a.slider("레버리지", 1, 125, 10, key="slider_lev")
amt = col_b.number_input("증거금(USDT)", value=100.0, key="input_amt")
st.info(f"포지션 규모: {amt * lev:,.0f} USDT")

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

if st.button("❌ 포지션 종료 및 정산하기", key="btn_settle"):
    st.session_state.balance += (sum(p['margin'] for p in st.session_state.positions) + total_pos_pnl)
    st.session_state.positions = []
    st.rerun()

time.sleep(0.3)
st.rerun()
