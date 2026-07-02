import streamlit as st
import requests
import streamlit.components.v1 as components

# 세션 상태가 없으면 무조건 초기화 (에러 방지)
if 'balance' not in st.session_state:
    st.session_state.balance = 10000.0
if 'long_btc' not in st.session_state:
    st.session_state.long_btc = 0.0
if 'short_btc' not in st.session_state:
    st.session_state.short_btc = 0.0

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=2)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

price = get_price()

st.title("BTC 실시간 트레이딩 대시보드")
st.write(f"현재가: {price:,.2f} USDT")

# 트레이딩뷰 실시간 차트
chart_code = f"""
<div class="tradingview-widget-container">
  <div id="tradingview_chart"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({{"width": "100%", "height": 400, "symbol": "OKX:BTCUSDT", "interval": "D", "theme": "light", "style": "1", "container_id": "tradingview_chart"}});
  </script>
</div>
"""
components.html(chart_code, height=400)

st.write(f"보유 잔고: {st.session_state.balance:,.2f} USDT")

perc = st.slider("투자 비율 (%)", 1, 100, 10)
amt = st.number_input("배팅 금액 (USDT)", value=int(st.session_state.balance * perc / 100))

col1, col2, col3 = st.columns(3)
if col1.button("롱 진입"):
    if st.session_state.balance >= amt:
        st.session_state.long_btc += amt / price
        st.session_state.balance -= amt
        st.rerun()

if col2.button("숏 진입"):
    if st.session_state.balance >= amt:
        st.session_state.short_btc += amt / price
        st.session_state.balance -= amt
        st.rerun()

if col3.button("포지션 종료"):
    st.session_state.balance += (st.session_state.long_btc + st.session_state.short_btc) * price
    st.session_state.long_btc = 0
    st.session_state.short_btc = 0
    st.rerun()

st.write("---")
st.write(f"현재 롱 보유량: {st.session_state.long_btc:.4f} BTC")
st.write(f"현재 숏 보유량: {st.session_state.short_btc:.4f} BTC")
