import streamlit as st
import requests
from datetime import datetime

st.set_page_config(page_title="BTC Bot", layout="centered")

# --- 데이터 상태 관리 ---
if 'balance' not in st.session_state: st.session_state.balance = 10000.0  # 실제 가용 잔액
if 'positions' not in st.session_state: st.session_state.positions = [] 
if 'logs' not in st.session_state: st.session_state.logs = []
if 'total_realized_pnl' not in st.session_state: st.session_state.total_realized_pnl = 0.0

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=0.3)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

price = get_price()

st.title("BTC 실시간 트레이딩")

# 1. 실시간 데이터 계산
total_pos_pnl = 0
for p in st.session_state.positions:
    diff = (price - p['entry']) if p['type'] == '롱' else (p['entry'] - price)
    total_pos_pnl += (diff / p['entry']) * p['margin'] * p['lev']

# 2. 대시보드 (투명한 자산 공개)
st.metric("실시간 총 자산 (USDT)", f"{st.session_state.balance + total_pos_pnl:,.2f}", f"{total_pos_pnl:+.2f} USDT")
st.write(f"가용 잔액: {st.session_state.balance:,.2f} USDT | 현재가: {price:,.2f}")

# 3. 입력 및 레버리지 계산
col_a, col_b = st.columns(2)
lev = col_a.slider("레버리지", 1, 125, 10, key="slider_lev")
amt = col_b.number_input("증거금(USDT)", value=100.0, key="input_amt")
st.info(f"선택하신 배팅 규모: {amt * lev:,.0f} USDT (증거금 {amt} * {lev}배)")

# 4. 버튼 로직 (잔액 체크 포함)
c1, c2 = st.columns(2)
if c1.button("롱 진입", key="btn_long"):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev})
        st.session_state.balance -= amt
        st.rerun()
    else: st.error("잔액 부족!")

if c2.button("숏 진입", key="btn_short"):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev})
        st.session_state.balance -= amt
        st.rerun()
    else: st.error("잔액 부족!")

# 5. 포지션 및 정산
for p in st.session_state.positions:
    pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
    st.warning(f"[{p['type']}] 수익: {pnl:+.2f} USDT | (증거금: {p['margin']} USDT)")

if st.button("❌ 포지션 종료 및 정산하기", key="btn_settle"):
    st.session_state.balance += (sum(p['margin'] for p in st.session_state.positions) + total_pos_pnl)
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 정산 완료: {total_pos_pnl:+.2f} USDT")
    st.session_state.positions = []
    st.rerun()

if st.button("🔄 가상머니 초기화", key="btn_reset"):
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.rerun()

# 6. 로그
st.caption("최근 거래 로그")
for log in reversed(st.session_state.logs[-5:]):
    st.text(log)
    
# 실시간 반영을 위한 자동 새로고침 (0.3초)
time.sleep(0.3)
st.rerun()
