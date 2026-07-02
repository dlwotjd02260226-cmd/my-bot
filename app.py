import streamlit as st
import requests
import streamlit.components.v1 as components

# 초기 세션 상태 설정
if 'balance' not in st.session_state:
    st.session_state.balance = 10000.0
    st.session_state.long_btc = 0.0
    st.session_state.short_btc = 0.0

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=2)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

price = get_price()

st.title("BTC 실시간 트레이딩 대시보드")
st.write(f"현재가: {price:,.2f} USDT")

# 1. 트레이딩뷰 실시간 차트 위젯 추가
chart_code = f"""
<div class="tradingview-widget-container">
  <div id="tradingview_chart"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({{
  "width": "100%", "height": 400, "symbol": "OKX:BTCUSDT",
  "interval": "D", "timezone": "Etc/UTC", "theme": "light", "style": "1",
  "locale": "kr", "toolbar_bg": "#f1f3f6", "enable_publishing": false,
  "container_id": "tradingview_chart"
  }});
  </script>
</div>
"""
components.html(chart_code, height=400)

st.write(f"보유 잔고: {st.session_state.balance:,.2f} USDT")

# 투자 비율 슬라이더 및 금액 입력
perc = st.slider("투자 비율 (%)", 1, 100, 10)
amt = st.number_input("배팅 금액 (USDT)", value=int(st.session_state.balance * perc / 100))

# 2. 버튼 구성 (롱, 숏, 포지션 종료)
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
    # 롱 포지션과 숏 포지션 모두 정리
    st.session_state.balance += (st.session_state.long_btc + st.session_state.short_btc) * price
    st.session_state.long_btc = 0
    st.session_state.short_btc = 0
    st.rerun()

st.write("---")
st.write(f"현재 롱 포지션: {st.session_state.long_btc:.4f} BTC")
st.write(f"현재 숏 포지션: {st.session_state.short_btc:.4f} BTC")
