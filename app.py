import streamlit as st
import requests
import streamlit.components.v1 as components
import time

st.set_page_config(page_title="BTC Bot", layout="centered")

# 세션 초기화
if 'balance' not in st.session_state: st.session_state.balance = 10000.0
if 'positions' not in st.session_state: st.session_state.positions = [] 

def get_price():
    try:
        # 응답속도 최적화를 위해 최소한의 데이터만 요청
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=0.5)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

st.title("BTC 실시간 트레이딩")

# UI 자리 배치
placeholder = st.empty()

# 차트 위젯 (웹에서 자체 구동되므로 차트는 실시간)
components.html("""
<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script>
<script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>
""", height=260)

# 컨트롤 버튼 (버튼만 여기에 배치)
lev = st.slider("레버리지", 1, 125, 10)
amt = st.number_input("증거금(USDT)", value=100)
c1, c2, c3 = st.columns(3)

if c1.button("롱 진입"):
    st.session_state.positions.append({'type': '롱', 'entry': get_price(), 'margin': amt, 'lev': lev})
    st.session_state.balance -= amt
if c2.button("숏 진입"):
    st.session_state.positions.append({'type': '숏', 'entry': get_price(), 'margin': amt, 'lev': lev})
    st.session_state.balance -= amt
if c3.button("포지션 종료"):
    st.session_state.positions = []
    st.rerun()

# 0.3초 간격 업데이트 (서버 안정성과 반응속도의 균형점)
while True:
    price = get_price()
    total_pos_pnl = 0
    for p in st.session_state.positions:
        diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
        total_pos_pnl += (diff / p['entry']) * p['margin'] * p['lev']
    
    total_asset = st.session_state.balance + total_pos_pnl
    
    with placeholder.container():
        st.metric("실시간 자산 (USDT)", f"{total_asset:,.2f}", f"{total_pos_pnl:+.2f} USDT")
        st.write(f"현재가: {price:,.2f} USDT")
    
    time.sleep(0.3) 
