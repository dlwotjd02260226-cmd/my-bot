import streamlit as st
import requests

# 초기 데이터 설정
if 'balance' not in st.session_state:
    st.session_state.balance = 10000.0
    st.session_state.btc = 0.0

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=2)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

price = get_price()

st.title("BTC 실시간 대시보드")
st.write(f"현재가: {price:,.2f} USDT")
st.write(f"잔고: {st.session_state.balance:,.2f} USDT | 보유: {st.session_state.btc:.4f} BTC")

# 입력 폼
perc = st.slider("투자 비율 (%)", 1, 100, 10)
amt = st.number_input("배팅 금액 (USDT)", value=int(st.session_state.balance * perc / 100))

col1, col2 = st.columns(2)
if col1.button("매수"):
    if st.session_state.balance >= amt:
        st.session_state.btc += amt / price
        st.session_state.balance -= amt
        st.rerun()

if col2.button("매도"):
    if st.session_state.btc > 0:
        st.session_state.balance += st.session_state.btc * price
        st.session_state.btc = 0
        st.rerun()
