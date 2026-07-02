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
    st.session_state.msg = None # 메시지 상태 추가
    st.session_state.msg_type = None # 메시지 타입 추가 (success/error)

# 시세 가져오기
def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=2)
        return float(r.json()['data'][0]['last'])
    except:
        return 0.0

price = get_price()

# 메시지 출력 함수 (깜빡임 방지용)
def show_msg(text, msg_type):
    st.session_state.msg = text
    st.session_state.msg_type = msg_type
    st.rerun()

st.title("BTC 실시간 트레이딩")

# UI 모드 설정
col_mode1, col_mode2 = st.columns(2)
with col_mode1: mode_real = st.radio("매매 모드", ["가상 매매", "실전 매매"], key="is_real", horizontal=True)
with col_mode2: mode_margin = st.radio("증거금 모드", ["격리 (Isolated)", "교차 (Cross)"], key="margin_mode", horizontal=True)

# 트레이딩뷰
components.html("""<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>""", height=260)

# 데이터 및 통계
total_pos_pnl = sum(((price - p['entry']) if p['type']=='롱' else (p['entry']-price))/p['entry']*p['margin']*p['lev'] for p in st.session_state.positions)
current_total_asset = st.session_state.balance + sum(p['margin'] for p in st.session_state.positions) + total_pos_pnl
st.metric("실시간 총 자산 (USDT)", f"{current_total_asset:,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{total_pos_pnl:+.2f} USDT")

# [수정] 메시지 공간 (깜빡임 없음)
msg_container = st.container()
if st.session_state.msg:
    if st.session_state.msg_type == "success": msg_container.success(st.session_state.msg)
    else: msg_container.error(st.session_state.msg)
    time.sleep(1)
    st.session_state.msg = None # 1초 후 메시지 비우기
    st.rerun()
else:
    msg_container.write("") # 메시지 없을 땐 빈 공간만 유지

# 자동 매매 컨트롤
col_auto1, col_auto2 = st.columns(2)
if st.session_state.auto_trading:
    col_auto1.button("🟢 자동 매매 중", disabled=True, use_container_width=True)
    if col_auto2.button("🔴 자동 매매 종료", use_container_width=True):
        st.session_state.auto_trading = False
        show_msg("🔴 자동 매매가 종료되었습니다.", "error")
        for p in st.session_state.positions:
            pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
            st.session_state.balance += (p['margin'] + pnl)
        st.session_state.positions = []
        st.rerun()
else:
    if col_auto1.button("🟢 자동 매매 시작", use_container_width=True):
        st.session_state.auto_trading = True
        show_msg("🟢 자동 매매가 시작되었습니다.", "success")
    col_auto2.button("🔴 자동 매매 종료", disabled=True, use_container_width=True)

st.divider()

# 매매 버튼
b1, b2, b3 = st.columns(3)
if b1.button("롱 진입", use_container_width=True):
    if 100 <= st.session_state.balance:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': 100, 'lev': 10, 'mode': mode_margin, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance -= 100
        show_msg("🟢 롱 포지션 진입하였습니다.", "success")
    else: show_msg("❌ 잔고가 부족합니다.", "error")

if b2.button("숏 진입", use_container_width=True):
    if 100 <= st.session_state.balance:
        st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': 100, 'lev': 10, 'mode': mode_margin, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance -= 100
        show_msg("🔴 숏 포지션 진입하였습니다.", "error")
    else: show_msg("❌ 잔고가 부족합니다.", "error")

if b3.button("❌ 종료", use_container_width=True):
    for p in st.session_state.positions:
        pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*10
        st.session_state.balance += (p['margin'] + pnl)
    st.session_state.positions = []
    show_msg("🔴 모든 포지션이 종료되었습니다.", "error")
    st.rerun()

# 가상머니 초기화 등 나머지 하단 동일
if st.button("🔄 가상머니 초기화", use_container_width=True):
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.rerun()

# 하단 리스트 생략 (기존과 동일)
time.sleep(0.3)
st.rerun()
