import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components

st.set_page_config(page_title="BTC Bot", layout="centered")

# --- 1. 초기 세팅 (데이터 영구 유지) ---
if 'balance' not in st.session_state: st.session_state.balance = 10000.0  # 가용 잔액
if 'positions' not in st.session_state: st.session_state.positions = [] 
if 'logs' not in st.session_state: st.session_state.logs = []
if 'total_realized_pnl' not in st.session_state: st.session_state.total_realized_pnl = 0.0

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=0.3)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

# --- 2. 실시간 가격 및 수익 계산 ---
price = get_price()
total_pos_pnl = 0
for p in st.session_state.positions:
    diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
    total_pos_pnl += (diff / p['entry']) * p['margin'] * p['lev']

# --- 3. UI 및 실시간 반영 ---
st.title("BTC 실시간 트레이딩")
components.html("""<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>""", height=260)

# 현재 총 평가 자산 (가용 잔액 + 실현 수익 + 평가 수익)
current_total_asset = st.session_state.balance + st.session_state.total_realized_pnl + total_pos_pnl
st.metric("실시간 총 자산 (USDT)", f"{current_total_asset:,.2f}", f"{total_pos_pnl:+.2f} USDT")
st.write(f"가용 잔액: {st.session_state.balance:,.2f} USDT | 현재가: {price:,.2f}")

# --- 4. 컨트롤 (배팅 로직 강화) ---
col1, col2 = st.columns(2)
lev = col1.slider("레버리지", 1, 125, 10, key="slider_lev")
amt = col2.number_input("증거금(USDT)", value=100.0, key="input_amt")
st.info(f"포지션 규모: {amt * lev:,.0f} USDT (증거금 {amt} * {lev}배)")

c1, c2 = st.columns(2)
# 배팅 제약 로직: 잔액보다 적을 때만 진입 허용
if c1.button("롱 진입", key="btn_long"):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev})
        st.session_state.balance -= amt
        st.rerun()
    else: st.error("증거금이 부족합니다!")

if c2.button("숏 진입", key="btn_short"):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev})
        st.session_state.balance -= amt
        st.rerun()
    else: st.error("증거금이 부족합니다!")

# 포지션 정보
for p in st.session_state.positions:
    pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
    st.warning(f"[{p['type']}] 수익: {pnl:+.2f} USDT")

# --- 5. 종료/정산/로그 ---
if st.button("❌ 포지션 종료 및 정산하기", key="btn_settle"):
    st.session_state.balance += (sum(p['margin'] for p in st.session_state.positions) + total_pos_pnl)
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 정산 완료: {total_pos_pnl:+.2f} USDT")
    st.session_state.positions = []
    st.rerun()

if st.button("🔄 가상머니 초기화", key="btn_reset_all"):
    st.session_state.balance = 10000.0
    st.session_state.total_realized_pnl = 0.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.rerun()

st.caption("최근 거래 로그")
for log in reversed(st.session_state.logs[-5:]):
    st.text(log)

# --- 6. 실시간 루프 (0.3초마다 자동 새로고침) ---
time.sleep(0.3)
st.rerun()
