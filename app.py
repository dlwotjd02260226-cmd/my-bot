import streamlit as st
import requests
import streamlit.components.v1 as components
from datetime import datetime

# 페이지 설정
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

# 1. 상단 수익률 지표
total_pos_val = sum([p['amt'] * (price if p['type'] == '롱' else (2*p['entry'] - price)) for p in st.session_state.positions])
total_asset = st.session_state.balance + total_pos_val
pnl_pct = ((total_asset - 10000) / 10000) * 100

st.metric("실시간 자산 (USDT)", f"{total_asset:,.2f}", f"{pnl_pct:+.2f}%")

# 2. 컨트롤 영역
lev = st.slider("레버리지 설정", 1, 125, 1)
amt = st.number_input("배팅 금액 (USDT)", min_value=1, value=1000)

col1, col2, col3 = st.columns(3)
if col1.button("롱 진입"):
    if st.session_state.balance >= amt:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'amt': (amt*lev)/price})
        st.session_state.balance -= amt
        st.session_state.logs.append(f"롱 진입({lev}배) @ {price:,.0f}")
        st.rerun()

if col2.button("숏 진입"):
    if st.session_state.balance >= amt:
        st.session_state.positions.append({'type': '숏', 'entry': price, 'amt': (amt*lev)/price})
        st.session_state.balance -= amt
        st.session_state.logs.append(f"숏 진입({lev}배) @ {price:,.0f}")
        st.rerun()

if col3.button("포지션 종료"):
    if st.session_state.positions:
        # 종료 로직: 현재가 기준으로 잔고 환원
        for p in st.session_state.positions:
            profit = (p['amt'] * price) if p['type'] == '롱' else (p['amt'] * (2*p['entry'] - price))
            st.session_state.balance += profit
        st.session_state.positions = []
        st.session_state.logs.append(f"포지션 종료 @ {price:,.0f}")
        st.rerun()

# 3. 차트
components.html('<div id="tv_chart"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv_chart"});</script>', height=260)

# 4. 로그
st.markdown("---")
st.caption("최근 거래 기록")
for log in reversed(st.session_state.logs[-3:]):
    st.text(log)
