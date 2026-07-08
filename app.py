import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components
import pandas as pd

# [필수 엔진 함수 - 원본 로직 유지]
def get_klines(tf='1h', limit=50):
    url = f"https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar={tf}&limit={limit}"
    try:
        r = requests.get(url, timeout=2)
        data = r.json().get('data', [])
        if not data: return None
        df = pd.DataFrame(data, columns=['ts', 'o', 'h', 'l', 'close', 'vol', 'confirm'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        return df.iloc[::-1].reset_index(drop=True)
    except: return None

def calculate_sr_score(price, df):
    supports = [df['low'].iloc[i] for i in range(5, len(df)-5) if df['low'].iloc[i] < df['low'].iloc[i-5:i].min() and df['low'].iloc[i] < df['low'].iloc[i+1:i+6].min()]
    resistances = [df['high'].iloc[i] for i in range(5, len(df)-5) if df['high'].iloc[i] > df['high'].iloc[i-5:i].max() and df['high'].iloc[i] > df['high'].iloc[i+1:i+6].max()]
    score = 0
    for s in supports[-3:]:
        if abs(price - s) / price < 0.005: score += 3
    for r in resistances[-3:]:
        if abs(price - r) / price < 0.005: score -= 3
    return score, supports, resistances

# 페이지 설정
st.set_page_config(page_title="BTC Bot", layout="centered")

# CSS: 메시지 영역 및 스타일
st.markdown("""
    <style>
    .fixed-msg-area { height: 70px; display: flex; align-items: center; justify-content: center; margin-bottom: 20px; border-radius: 5px; font-weight: bold; width: 100%; }
    .msg-success { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .msg-error { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    </style>
""", unsafe_allow_html=True)

# 세션 상태 초기화 (누적 데이터 관리 추가)
if 'balance' not in st.session_state:
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.session_state.auto_trading = False
    st.session_state.msg = None
    st.session_state.msg_type = None
    st.session_state.mode = "수동"
    st.session_state.wins_total = 0.0
    st.session_state.losses_total = 0.0

# 시세 가져오기 함수
def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=2)
        return float(r.json()['data'][0]['last'])
    except:
        return 0.0

price = get_price()

# 제목
st.markdown("<div style='font-size: 42px; font-weight: bold; margin-bottom: 20px;'>BTC 실시간 트레이딩</div>", unsafe_allow_html=True)

# 설정 UI 영역
col_mode1, col_mode2 = st.columns(2)
with col_mode1:
    mode_real = st.radio("매매 모드", ["가상 매매", "실전 매매"], key="is_real", horizontal=True)
with col_mode2:
    mode_margin = st.radio("증거금 모드", ["격리 (Isolated)", "교차 (Cross)"], key="margin_mode", horizontal=True)

if mode_real == "실전 매매": st.error(f"🚨 실전 매매 모드 ({mode_margin}) 입니다.")
else: st.success(f"✅ 가상 매매 모드 ({mode_margin}) 입니다.")

st.subheader("매매 운영 모드 설정")
mode_option = st.radio("운영 모드 선택", ["수동 모드", "오토 모드"], key="mode_radio", horizontal=True)
st.session_state.mode = "오토" if mode_option == "오토 모드" else "수동"

col_set1, col_set2 = st.columns(2)
is_auto = (st.session_state.mode == "오토")
st.session_state.tp_input = col_set1.number_input("익절 (%)", value=2.0, disabled=is_auto)
st.session_state.sl_input = col_set2.number_input("손절 (%)", value=1.0, disabled=is_auto)

col1, col2 = st.columns(2)
lev = col1.number_input("레버리지 (1~125)", min_value=1, max_value=125, value=10)
amt = col2.number_input("배팅 금액(USDT)", value=100.0)
st.divider()

# 차트 표시
components.html("""<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>""", height=260)

# 계산 로직
time_weights = {'1M': 16.0, '1W': 8.0, '1d': 4.0, '4h': 2.0, '1h': 1.0}
total_score = 0
analysis_summary = []
strategy_tier = 1.5 
for tf, t_weight in time_weights.items():
    df = get_klines(tf)
    if df is not None and not df.empty:
        score, supports, resistances = calculate_sr_score(price, df)
        final_score = score * strategy_tier * t_weight
        total_score += final_score
        analysis_summary.append((tf, final_score, supports, resistances))

# 포지션 관리 및 자동 청산 (계산 정확도 보완)
for p in st.session_state.positions[:]:
    pnl_pct = ((price - p['entry']) if p['type']=='롱' else (p['entry']-price)) / p['entry'] * 100 * p['lev']
    target_tp = 3.5 if st.session_state.mode == "오토" else st.session_state.tp_input
    target_sl = 1.5 if st.session_state.mode == "오토" else st.session_state.sl_input
    
    if pnl_pct >= target_tp or pnl_pct <= -target_sl:
        action = "익절" if pnl_pct > 0 else "손절"
        pnl_val = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
        
        # 누적 데이터 업데이트
        if pnl_val > 0: st.session_state.wins_total += pnl_val
        else: st.session_state.losses_total += pnl_val
        
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {p['type']} {action}: {pnl_val:.2f} USDT")
        st.session_state.balance += (p['margin'] + pnl_val)
        st.session_state.positions.remove(p)
        st.rerun()

# 자산 표시
total_pos_pnl = sum(((price - p['entry']) if p['type']=='롱' else (p['entry']-price))/p['entry']*p['margin']*p['lev'] for p in st.session_state.positions)
current_total_asset = st.session_state.balance + sum(p['margin'] for p in st.session_state.positions) + total_pos_pnl
st.metric("실시간 총 자산 (USDT)", f"{current_total_asset:,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{total_pos_pnl:+.2f} USDT")

st.markdown(f"누적: <span style='color: green;'>익절 {st.session_state.wins_total:,.2f}</span> / <span style='color: red;'>손절 {st.session_state.losses_total:,.2f}</span> USDT", unsafe_allow_html=True)

# 자동 매매 UI
with st.container(border=True):
    col_auto1, col_auto2 = st.columns(2)
    if col_auto1.button("🟢 자동 매매 시작"): st.session_state.auto_trading = True
    if col_auto2.button("🔴 자동 매매 종료"): st.session_state.auto_trading = False

# 보유 포지션
st.subheader("보유 중인 포지션")
for p in st.session_state.positions:
    st.write(f"타입: {p['type']} | 진입가: {p['entry']} | 금액: {p['margin']}")

# 분석 상태 및 상세 보기
with st.container():
    st.markdown(f"### 📊 종합 매매 점수: {total_score:.1f}점")
    with st.expander("🔍 매매 분석 상세 보기 (펼치기)"):
        for tf, f_score, sup, res in analysis_summary:
            st.write(f"{tf} 타임프레임 (점수: {f_score:.1f})")
            c1, c2 = st.columns(2)
            c1.table(pd.DataFrame(sup[-3:], columns=["Support"]))
            c2.table(pd.DataFrame(res[-3:], columns=["Resistance"]))

# 수동 모드 버튼
st.divider()
st.subheader("수동 모드")
b1, b2, b3 = st.columns(3)
if b1.button("롱 진입", use_container_width=True):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance -= amt
        st.rerun()
if b2.button("숏 진입", use_container_width=True):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance -= amt
        st.rerun()
if b3.button("❌ 전체 포지션 종료", use_container_width=True):
    for p in st.session_state.positions:
        pnl = ((price - p['entry']) if p['type']=='롱' else (p['entry']-price)) / p['entry'] * p['margin'] * p['lev']
        if pnl > 0: st.session_state.wins_total += pnl
        else: st.session_state.losses_total += pnl
        st.session_state.balance += (p['margin'] + pnl)
    st.session_state.positions = []
    st.rerun()

# 가상머니 초기화 및 로그
if st.button("🔄 가상머니 초기화"):
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.session_state.wins_total = 0.0
    st.session_state.losses_total = 0.0
    st.rerun()

st.subheader("거래 로그")
for log in reversed(st.session_state.logs[-10:]):
    st.text(log)
time.sleep(0.3)
st.rerun()
