import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components
import pandas as pd

# [매물대 엔진 함수]
def get_klines(tf='30m', limit=100):
    url = f"https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar={tf}&limit={limit}"
    try:
        r = requests.get(url, timeout=2)
        data = r.json()['data']
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

# CSS 스타일
st.markdown("""
    <style>
    .fixed-msg-area { height: 70px; display: flex; align-items: center; justify-content: center; margin-bottom: 20px; border-radius: 5px; font-weight: bold; width: 100%; }
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

# 시세 가져오기
def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=2)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

price = get_price()

st.markdown("<div style='font-size: 42px; font-weight: bold; margin-bottom: 20px;'>BTC 실시간 트레이딩</div>", unsafe_allow_html=True)

col_mode1, col_mode2 = st.columns(2)
with col_mode1: mode_real = st.radio("매매 모드", ["가상 매매", "실전 매매"], key="is_real", horizontal=True)
with col_mode2: mode_margin = st.radio("증거금 모드", ["격리 (Isolated)", "교차 (Cross)"], key="margin_mode", horizontal=True)

if mode_real == "실전 매매": st.error(f"🚨 실전 매매 모드 ({mode_margin}) 입니다.")
else: st.success(f"✅ 가상 매매 모드 ({mode_margin}) 입니다.")

components.html("""
<div id="tv"></div>
<script src="https://s3.tradingview.com/tv.js"></script>
<script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>
""", height=260)

# 자산 및 로그 계산
total_pos_pnl = sum(((price - p['entry']) if p['type']=='롱' else (p['entry']-price))/p['entry']*p['margin']*p['lev'] for p in st.session_state.positions)
st.metric("실시간 총 자산 (USDT)", f"{st.session_state.balance + sum(p['margin'] for p in st.session_state.positions) + total_pos_pnl:,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{total_pos_pnl:+.2f} USDT")

col1, col2 = st.columns(2)
lev = col1.slider("레버리지", 1, 125, 10)
amt = col2.number_input("증거금(USDT)", value=100.0)

# 매매 분석 엔진 상태 (신호 성립 시에만 표시)
st.subheader("매매 분석 엔진 상태")
df_30m = get_klines('30m')
if df_30m is not None:
    sr_score, supports, resistances = calculate_sr_score(price, df_30m)
    tf = "30분봉"
    
    # 신호가 있을 때만 강조 표시
    if abs(sr_score) >= 3:
        with st.expander(f"🟢 [신호 발생] {tf} 매매 기법 가동", expanded=True):
            action = "롱(Long)" if sr_score >= 3 else "숏(Short)"
            st.markdown(f"**이유:** {tf}에서 매물대 분석 근거로 **{action}** 추천")
            c1, c2 = st.columns(2)
            c1.write("🛡️ 지지대"); c1.table(pd.DataFrame(supports[-3:], columns=["Price"]))
            c2.write("⚔️ 저항대"); c2.table(pd.DataFrame(resistances[-3:], columns=["Price"]))
    else:
        st.info(f"⚪ {tf} 차트 분석 중: 현재 진입 조건 미성립")
else:
    st.write("데이터 수집 중...")

# 매매 버튼
b1, b2, b3 = st.columns(3)
if b1.button("롱 진입"): 
    st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev, 'mode': mode_margin, 'time': datetime.now().strftime('%H:%M:%S')})
    st.rerun()
if b2.button("숏 진입"): 
    st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev, 'mode': mode_margin, 'time': datetime.now().strftime('%H:%M:%S')})
    st.rerun()
if b3.button("전체 종료"): 
    st.session_state.positions = []
    st.rerun()

st.subheader("거래 로그")
for log in reversed(st.session_state.logs[-10:]): st.text(log)
if st.button("🔄 초기화"): st.rerun()

time.sleep(0.3)
st.rerun()
