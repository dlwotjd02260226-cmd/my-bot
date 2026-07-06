import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components

# 페이지 설정
st.set_page_config(page_title="BTC Bot", layout="centered")

# CSS: 메시지 영역 및 스타일
st.markdown("""
    <style>
    .fixed-msg-area {
        height: 70px;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 20px;
        border-radius: 5px;
        font-weight: bold;
        width: 100%;
    }
    .msg-success { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .msg-error { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    </style>
""", unsafe_allow_html=True)

# 세션 상태 초기화
if 'balance' not in st.session_state:
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.session_state.auto_trading = False
    st.session_state.msg = None
    st.session_state.msg_type = None

# 시세 가져오기 함수
def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=2)
        return float(r.json()['data'][0]['last'])
    except:
        return 0.0

price = get_price()

# 제목 글자 크기 조절
st.markdown("<div style='font-size: 24px; font-weight: bold; margin-bottom: 20px;'>BTC 실시간 트레이딩</div>", unsafe_allow_html=True)

# 실전/가상 매매 및 교차/격리 모드 선택
col_mode1, col_mode2 = st.columns(2)
with col_mode1:
    mode_real = st.radio("매매 모드", ["가상 매매", "실전 매매"], key="is_real", horizontal=True)
with col_mode2:
    mode_margin = st.radio("증거금 모드", ["격리 (Isolated)", "교차 (Cross)"], key="margin_mode", horizontal=True)

if mode_real == "실전 매매":
    st.error(f"🚨 실전 매매 모드 ({mode_margin}) 입니다.")
else:
    st.success(f"✅ 가상 매매 모드 ({mode_margin}) 입니다.")

components.html("""
<div id="tv"></div>
<script src="https://s3.tradingview.com/tv.js"></script>
<script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>
""", height=260)

total_pos_pnl = sum(((price - p['entry']) if p['type']=='롱' else (p['entry']-price))/p['entry']*p['margin']*p['lev'] for p in st.session_state.positions)
total_margin_in_pos = sum(p['margin'] for p in st.session_state.positions)
current_total_asset = st.session_state.balance + total_margin_in_pos + total_pos_pnl

total_wins = sum(float(log.split(": ")[-1].replace(" USDT", "")) for log in st.session_state.logs if float(log.split(": ")[-1].replace(" USDT", "")) > 0)
total_losses = sum(float(log.split(": ")[-1].replace(" USDT", "")) for log in st.session_state.logs if float(log.split(": ")[-1].replace(" USDT", "")) <= 0)

st.metric("실시간 총 자산 (USDT)", f"{current_total_asset:,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{total_pos_pnl:+.2f} USDT")

st.markdown(f"""
<div style="font-size: 0.9em; margin-bottom: 20px;">
누적: <span style="color: green;">익절 {total_wins:,.2f}</span> / <span style="color: red;">손절 {total_losses:,.2f}</span> USDT
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns(2)
lev = col1.slider("레버리지", 1, 125, 10)
amt = col2.number_input("증거금(USDT)", value=100.0)

# 메시지 출력 영역
msg_placeholder = st.empty()
if st.session_state.msg:
    c_class = "msg-success" if st.session_state.msg_type == "success" else "msg-error"
    msg_placeholder.markdown(f'<div class="fixed-msg-area {c_class}">{st.session_state.msg}</div>', unsafe_allow_html=True)
    time.sleep(1)
    st.session_state.msg = None
    st.rerun()
else:
    msg_placeholder.markdown('<div class="fixed-msg-area" style="background-color: transparent;"></div>', unsafe_allow_html=True)

# 자동 매매 섹션
col_auto1, col_auto2 = st.columns(2)
if st.session_state.auto_trading:
    col_auto1.button("🟢 자동 매매 중", disabled=True, use_container_width=True)
    if col_auto2.button("🔴 자동 매매 종료", use_container_width=True):
        st.session_state.auto_trading = False
        st.session_state.msg = "🔴 자동 매매가 종료되었습니다."
        st.session_state.msg_type = "error"
        for p in st.session_state.positions:
            pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
            if p['mode'] == "교차 (Cross)" and (p['margin'] + pnl) <= 0: pnl = -p['margin']
            st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {p['type']} 자동 종료({p['mode']}): {pnl:+.2f} USDT")
            st.session_state.balance += (p['margin'] + pnl)
        st.session_state.positions = []
        st.rerun()
else:
    if col_auto1.button("🟢 자동 매매 시작", use_container_width=True):
        st.session_state.auto_trading = True
        st.session_state.msg = "🟢 자동 매매가 시작되었습니다."
        st.session_state.msg_type = "success"
        st.rerun()
    col_auto2.button("🔴 자동 매매 종료", disabled=True, use_container_width=True)

# 보유 중인 포지션
st.subheader("보유 중인 포지션")
if not st.session_state.positions:
    st.write("보유 포지션 없음")
else:
    for p in st.session_state.positions:
        liq_price = p['entry'] * (1 - (1 / p['lev'])) if p['type'] == '롱' else p['entry'] * (1 + (1 / p['lev']))
        st.markdown(f"""
        <div style="background-color: #f0f2f6; padding: 10px; border-radius: 10px; margin-bottom: 5px;">
        <div style="font-weight: bold;">{p['time']} | {p['type']} ({p['mode']}) | {p['lev']}x</div>
        <div style="display: flex; justify-content: space-between;">
        <span>진입가: <b style="color: blue;">{p['entry']:.2f}</b></span>
        <span>청산가: <b style="color: red;">{liq_price:.2f}</b></span>
        </div>
        </div>
        """, unsafe_allow_html=True)

# 매매 판단 엔진 상태
st.subheader("매매 판단 엔진 상태")
status_col1, status_col2 = st.columns(2)
status_col1.info("📊 현재 전략: 대기중")
status_col2.warning("⚪ 신호: 신호 없음")

with st.expander("🔍 매매 이유 상세 보기 (펼치기)"):
    st.markdown("""
    * 1. 지지/저항 돌파: <span style="color: gray;">대기 중</span>
    * 2. 거래량 분석: <span style="color: gray;">대기 중</span>
    * 3. 고래 체결량: <span style="color: gray;">데이터 수집 전</span>
    * 4. 다이버전스: <span style="color: gray;">데이터 수집 전</span>
    <hr>
    향후 모든 매매 기법의 상세 결과가 여기에 나열됩니다.
    """)

st.divider()

# 매매 버튼
b1, b2, b3 = st.columns(3)
if b1.button("롱 진입", use_container_width=True):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev, 'mode': mode_margin, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance -= amt
        st.session_state.msg = "🟢 롱 포지션 진입 완료!"
        st.session_state.msg_type = "success"
        st.rerun()
    else:
        st.session_state.msg = "❌ 잔고 부족!"
        st.session_state.msg_type = "error"
        st.rerun()

if b2.button("숏 진입", use_container_width=True):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev, 'mode': mode_margin, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance -= amt
        st.session_state.msg = "🔴 숏 포지션 진입 완료!"
        st.session_state.msg_type = "error"
        st.rerun()
    else:
        st.session_state.msg = "❌ 잔고 부족!"
        st.session_state.msg_type = "error"
        st.rerun()

if b3.button("❌ 종료", use_container_width=True):
    for p in st.session_state.positions:
        pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
        if p['mode'] == "교차 (Cross)" and (p['margin'] + pnl) <= 0: pnl = -p['margin']
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {p['type']} 종료({p['mode']}): {pnl:+.2f} USDT")
        st.session_state.balance += (p['margin'] + pnl)
    st.session_state.positions = []
    st.session_state.msg = "🔴 포지션 종료 하였습니다."
    st.session_state.msg_type = "error"
    st.rerun()

if st.button("🔄 가상머니 초기화", use_container_width=True):
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.session_state.auto_trading = False
    st.rerun()

st.subheader("거래 로그")
for log in reversed(st.session_state.logs[-10:]):
    st.text(log)

time.sleep(0.3)
st.rerun()
st.rerun()

