import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components

st.set_page_config(page_title="BTC Bot", layout="centered")

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

components.html("""<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>""", height=260)

# 1. 포지션별 평가 손익
total_pos_pnl = sum(((price - p['entry']) if p['type']=='롱' else (p['entry']-price))/p['entry']*p['margin']*p['lev'] for p in st.session_state.positions)

# 2. 핵심 로직: 
# 실시간 총 자산 = (잔액 + 현재 진입한 증거금 합계) + 평가 손익
total_margin_in_pos = sum(p['margin'] for p in st.session_state.positions)
current_total_asset = st.session_state.balance + total_margin_in_pos + total_pos_pnl

# 3. 변동 금액 = 오직 평가 손익만
current_fluctuation = total_pos_pnl

# --- [추가] 누적 수익/손실 계산 ---
total_wins = sum(float(log.split(": ")[-1].replace(" USDT", "")) for log in st.session_state.logs if float(log.split(": ")[-1].replace(" USDT", "")) > 0)
total_losses = sum(float(log.split(": ")[-1].replace(" USDT", "")) for log in st.session_state.logs if float(log.split(": ")[-1].replace(" USDT", "")) <= 0)

# UI 출력
st.metric("실시간 총 자산 (USDT)", f"{current_total_asset:,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{current_fluctuation:+.2f} USDT")

# --- [수정] 누적 수익/손실을 작게 한 줄로 표기 ---
st.markdown(f"""
<div style="font-size: 0.9em; margin-bottom: 20px;">
    누적: <span style="color: green;">익절 {total_wins:,.2f}</span> / <span style="color: red;">손절 {total_losses:,.2f}</span> USDT
</div>
""", unsafe_allow_html=True)

# 컨트롤
col1, col2 = st.columns(2)
lev = col1.slider("레버리지", 1, 125, 10, key="lev")
amt = col2.number_input("증거금(USDT)", value=100.0, key="amt")

# [추가] 지정가 입력창 (현재가를 기본값으로 설정)
limit_price = st.number_input("지정가 설정 (USDT)", value=price, step=10.0, key="limit_price")

c1, c2 = st.columns(2)
if c1.button("롱 진입"):
    if amt <= st.session_state.balance:
        # 지정가(limit_price)를 진입가로 사용
        st.session_state.positions.append({'type': '롱', 'entry': limit_price, 'margin': amt, 'lev': lev})
        st.session_state.balance -= amt
        st.rerun()

if c2.button("숏 진입"):
    if amt <= st.session_state.balance:
        # 지정가(limit_price)를 진입가로 사용
        st.session_state.positions.append({'type': '숏', 'entry': limit_price, 'margin': amt, 'lev': lev})
        st.session_state.balance -= amt
        st.rerun()

if st.button("❌ 포지션 종료"):
    for p in st.session_state.positions:
        pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {p['type']} 종료: {pnl:+.2f} USDT")
        # 종료 시 증거금을 다시 잔액으로 돌려주고 수익금을 합산
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
