import streamlit as st
import requests
import streamlit.components.v1 as components
from datetime import datetime

# 세션 상태 초기화
if 'balance' not in st.session_state: st.session_state.balance = 10000.0
if 'positions' not in st.session_state: st.session_state.positions = [] # [타입, 진입가, 수량]
if 'logs' not in st.session_state: st.session_state.logs = []

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=2)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

price = get_price()
st.title("BTC 실시간 트레이딩 대시보드")

# 1. 자산 실시간 계산 (수익금 표시)
total_pos_val = sum([p['amt'] * (price if p['type'] == '롱' else (2*p['entry'] - price)) for p in st.session_state.positions])
st.metric("현재가", f"{price:,.2f} USDT")
st.metric("실시간 자산", f"{st.session_state.balance + total_pos_val:,.2f} USDT")

# 2. OKX 레버리지 정보 (비트코인 맥스 125배)
st.info("💡 OKX BTC-USDT 최대 레버리지: 125배")

# 차트
components.html(f'<div id="tradingview_chart"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({{"width":"100%","height":300,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tradingview_chart"}});</script>', height=320)

# 매매 로직
amt = st.number_input("배팅 금액 (USDT)", value=1000)
col1, col2, col3 = st.columns(3)

if col1.button("롱 진입"):
    if st.session_state.balance >= amt:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'amt': amt/price})
        st.session_state.balance -= amt
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 롱 진입 @ {price:,.2f}")
        st.rerun()

if col2
