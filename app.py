import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components

st.set_page_config(page_title="BTC Bot", layout="centered")

# 세션 상태 초기화
if 'init' not in st.session_state:
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.session_state.is_real_mode = False  # 실전 모드 플래그 추가
    st.session_state.init = True

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=0.3)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

price = get_price()
st.title("BTC 실시간 트레이딩")

# 실전/가상 모드 토글 (화면 상단 배치)
st.session_state.is_real_mode = st.toggle("실전 매매 모드 활성화", st.session_state.is_real_mode)

if st.session_state.is_real_mode:
    st.error("🚨 현재 [실전 매매] 모드입니다. 실제 자산이 운용됩니다!")
else:
    st.success("✅ 현재 [가상 매매] 모드입니다.")

components.html("""<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>""", height=260)

# 1. 포지션별 평가 손익
total_pos_pnl = sum(((price - p['entry']) if p['type']=='롱' else (p['entry']-price))/p['entry']*p['margin']*p['lev'] for p in st.session_state.positions)

# 2. 실시간 총 자산
total_margin_in_pos = sum(p['margin'] for p in st.session_state.positions)
current_total_asset = st.session_state.balance + total_margin_in_pos + total_pos_pnl

# 3. 변동 금액
current_fluctuation = total_pos_pnl

# 누적 수익/손실
total_wins = sum(float(log.split(": ")[-1].replace(" USDT", "")) for log in st.session_state.logs if float(log.split(": ")[-1].replace(" USDT", "")) > 0)
total_losses = sum(float(log.split(": ")[-1].replace(" USDT", "")) for log in st.session_state.logs if float(log.split(": ")[-1].replace(" USDT", "")) <= 0)

# UI 출력
st.metric("실시간 총 자산 (USDT)", f"{current_total_asset:,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{current_fluctuation:+.2f} USDT")

st.markdown(f"""
<div style="font-size: 0.9em; margin-bottom: 20px;">
    누적: <span style="color: green;">익절 {total_wins:,.2f}</span> / <span style="color: red;">손절 {total_losses:,.2f}</span> USDT
</div>
""", unsafe_allow_html=True)

# 컨트롤
col1, col2 = st.columns(2)
lev = col1.slider("레버리지", 1, 125, 10, key="lev")
amt = col2.number_input("증거금(USDT)", value=100.0, key="amt")

b1, b2, b3 = st.columns(3)

# 롱 진입
if b1.button("롱 진입", use_container_width=True):
    if st.session_state.is_real_mode:
        st.toast("실전 API 주문을 수행합니다...") # 나중에 여기 API 연동
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance -= amt
        st.rerun()

# 숏 진입
if b2.button("숏 진입", use_container_width=True):
    if st.session_state.is_real_mode:
        st.toast("실전 API 주문을 수행합니다...") # 나중에 여기 API 연동
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance -= amt
        st.rerun()

# 포지션 종료
if b3.button("❌ 종료", use_container_width=True):
    for p in st.session_state.positions:
        pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {p['type']} 종료: {pnl:+.2f} USDT")
        st.session_state.balance += (p['margin'] + pnl)
    st.session_state.positions = []
    st.rerun()

if st.button("🔄 가상머니 초기화", use_container_width=True):
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.rerun()

st.subheader("보유 중인 포지션")
if not st.session_state.positions:
    st.write("보유 포지션 없음")
else:
    for p in st.session_state.positions:
        st.info(f"{p['time']} | {p['type']} | 진입가: {p['entry']} | 증거금: {p['margin']} | 레버리지: {p['lev']}x")

st.subheader("거래 로그")
for log in reversed(st.session_state.logs[-10:]):
    st.text(log)

time.sleep(0.3)
st.rerun()
