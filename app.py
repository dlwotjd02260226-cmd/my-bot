import streamlit as st
import requests
import streamlit.components.v1 as components
from datetime import datetime

st.set_page_config(page_title="BTC Bot", layout="centered")

# 세션 초기화
if 'balance' not in st.session_state: st.session_state.balance = 10000.0
if 'positions' not in st.session_state: st.session_state.positions = [] 
if 'logs' not in st.session_state: st.session_state.logs = []

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=2)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

price = get_price()

# 포지션별 청산가 계산 함수
def calculate_liq_price(p, lev):
    # 청산가 계산: 레버리지를 반영하여 마진 소진 시점 계산
    if p['type'] == '롱':
        return p['entry'] * (1 - (0.9 / lev)) # 0.9는 유지증거금 고려 예시
    else:
        return p['entry'] * (1 + (0.9 / lev))

# 1. 자산 및 수익금 계산
total_pos_val = sum([p['amt'] * (price if p['type'] == '롱' else (2*p['entry'] - price)) for p in st.session_state.positions])
total_asset = st.session_state.balance + total_pos_val
pnl_amt = total_asset - 10000
pnl_pct = (pnl_amt / 10000) * 100

st.metric("실시간 자산 (USDT)", f"{total_asset:,.2f}", f"{pnl_pct:+.2f}% ({pnl_amt:+.2f} USDT)")

# 청산가 표시
if st.session_state.positions:
    liq_prices = [calculate_liq_price(p, 10) for p in st.session_state.positions] # 기본 레버리지 10배 기준 예시
    st.error(f"⚠️ 예상 청산가: {min(liq_prices):,.2f} USDT")

# 2. 컨트롤 영역
lev = st.slider("레버리지 설정", 1, 125, 1)
amt = st.number_input("배팅 금액 (USDT)", min_value=1, value=1000)

col1, col2, col3 = st.columns(3)
with col1:
    if st.button("롱 진입"):
        if st.session_state.balance >= amt:
            st.session_state.positions.append({'type': '롱', 'entry': price, 'amt': (amt*lev)/price})
            st.session_state.balance -= amt
            st.session_state.logs.append(f"롱 진입({lev}배) @ {price:,.0f}")
            st.rerun()
with col2:
    if st.button("숏 진입"):
        if st.session_state.balance >= amt:
            st.session_state.positions.append({'type': '숏', 'entry': price, 'amt': (amt*lev)/price})
            st.session_state.balance -= amt
            st.session_state.logs.append(f"숏 진입({lev}배) @ {price:,.0f
