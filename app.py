import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components

# 페이지 설정
st.set_page_config(page_title="BTC Bot", layout="centered")

# 세션 상태 초기화
if 'balance' not in st.session_state:
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.session_state.auto_trading = False
    st.session_state.msg = None
    st.session_state.msg_type = None

# [수정] CSS로 메시지 컨테이너 및 내부 경고창의 마진/패딩을 완벽 고정
st.markdown("""
    <style>
    .fixed-msg-area {
        height: 70px;
        margin: 0px !important;
        padding: 0px !important;
    }
    div[data-testid="stAlert"] {
        margin-top: 0px !important;
        margin-bottom: 0px !important;
    }
    </style>
""", unsafe_allow_html=True)

# 시세 가져오기 함수
def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=2)
        return float(r.json()['data'][0]['last'])
    except:
        return 0.0

price = get_price()

st.title("BTC 실시간 트레이딩")

# [수정] 경고 메시지 영역 (고정된 높이와 마진 유지)
msg_placeholder = st.container()
with msg_placeholder:
    st.markdown('<div class="fixed-msg-area">', unsafe_allow_html=True)
    if st.session_state.msg:
        if st.session_state.msg_type == "success": st.success(st.session_state.msg)
        else: st.error(st.session_state.msg)
        time.sleep(1)
        st.session_state.msg = None
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# 실전/가상 매매 모드
col_mode1, col_mode2 = st.columns(2)
with col_mode1: mode_real = st.radio("매매 모드", ["가상 매매", "실전 매매"], key="is_real", horizontal=True)
with col_mode2: mode_margin = st.radio("증거금 모드", ["격리 (Isolated)", "교차 (Cross)"], key="margin_mode", horizontal=True)

if mode_real == "실전 매매": st.error(f"🚨 실전 매매 모드 ({mode_margin}) 입니다.")
else: st.success(f"✅ 가상 매매 모드 ({mode_margin}) 입니다.")

components.html("""<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>""", height=260)

# 데이터 및 통계 출력
total_pos_pnl = sum(((price - p['entry']) if p['type']=='롱' else (p['entry']-price))/p['entry']*p['margin']*p['lev'] for p in st.session_state.positions)
st.metric("실시간 총 자산 (USDT)", f"{st.session_state.balance + sum(p['margin'] for p in st.session_state.positions) + total_pos_pnl:,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{total_pos_pnl:+.2f} USDT")

# 컨트롤
col1, col2 = st.columns(2)
lev = col1.slider("레버리지", 1, 125, 10)
amt = col2.number_input("증거금(USDT)", value=100.0)

# 자동 매매 및 매매 버튼 섹션
col_auto1, col_auto2 = st.columns(2)
if st.session_state.auto_trading:
    col_auto1.button("🟢 자동 매매 중", disabled=True, use_container_width=True)
    if col_auto2.button("🔴 자동 매매 종료", use_container_width=True):
        st.session_state.auto_trading = False
        st.session_state.msg = "🔴 자동 매매가 종료되었습니다."; st.session_state.msg_type = "error"; st.rerun()
else:
    if col_auto1.button("🟢 자동 매매 시작", use_container_width=True):
        st.session_state.auto_trading = True
        st.session_state.msg = "🟢 자동 매매가 시작되었습니다."; st.session_state.msg_type = "success"; st.rerun()
    col_auto2.button("🔴 자동 매매 종료", disabled=True, use_container_width=True)

st.divider()

b1, b2, b3 = st.columns(3)
if b1.button("롱 진입", use_container_width=True):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev, 'mode': mode_margin, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance -= amt
        st.session_state.msg = "🟢 롱 포지션 진입 완료!"; st.session_state.msg_type = "success"; st.rerun()
    else: st.session_state.msg = "❌ 잔고 부족!"; st.session_state.msg_type = "error"; st.rerun()

if b2.button("숏 진입", use_container_width=True):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev, 'mode': mode_margin, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance -= amt
        st.session_state.msg = "🔴 숏 포지션 진입 완료!"; st.session_state.msg_type = "error"; st.rerun()
    else: st.session_state.msg = "❌ 잔고 부족!"; st.session_state.msg_type = "error"; st.rerun()

if b3.button("❌ 종료", use_container_width=True):
    st.session_state.positions = []
    st.session_state.msg = "🔴 포지션 종료 하였습니다."; st.session_state.msg_type = "error"; st.rerun()

if st.button("🔄 가상머니 초기화", use_container_width=True):
    st.session_state.balance = 10000.0; st.session_state.positions = []; st.rerun()

# 포지션/로그 표시
st.subheader("보유 중인 포지션")
if not st.session_state.positions: st.write("보유 포지션 없음")
else:
    for p in st.session_state.positions: st.write(f"{p['type']} | {p['entry']} | {p['lev']}x")

st.subheader("거래 로그")
for log in reversed(st.session_state.logs[-10:]): st.text(log)

time.sleep(0.3)
st.rerun()
