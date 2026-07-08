import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components
import pandas as pd

# [필수 엔진 함수들]
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

# CSS
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

components.html("""<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>""", height=260)

# 자산 통계
total_pos_pnl = sum(((price - p['entry']) if p['type']=='롱' else (p['entry']-price))/p['entry']*p['margin']*p['lev'] for p in st.session_state.positions)
st.metric("실시간 총 자산 (USDT)", f"{(st.session_state.balance + sum(p['margin'] for p in st.session_state.positions) + total_pos_pnl):,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{total_pos_pnl:+.2f} USDT")

col1, col2 = st.columns(2)
lev = col1.slider("레버리지", 1, 125, 10)
amt = col2.number_input("증거금(USDT)", value=100.0)

# 메시지 출력
msg_placeholder = st.empty()
if st.session_state.msg:
    c_class = "msg-success" if st.session_state.msg_type == "success" else "msg-error"
    msg_placeholder.markdown(f'<div class="fixed-msg-area {c_class}">{st.session_state.msg}</div>', unsafe_allow_html=True)
    time.sleep(1); st.session_state.msg = None; st.rerun()

# [업그레이드된 분석 엔진]
st.subheader("매매 분석 엔진 상태")
with st.expander("🔍 매매 분석 상세 보기 (펼치기)"):
    time_weights = {'1M': 16.0, '1W': 8.0, '1d': 4.0, '4h': 2.0, '1h': 1.0}
    total_score = 0; analysis_summary = []
    
    for tf, t_weight in time_weights.items():
        df = get_klines(tf)
        if df is not None:
            score, s, r = calculate_sr_score(price, df)
            total_score += (score * 1.5 * t_weight)
            analysis_summary.append((tf, score * 1.5 * t_weight, s, r))
    
    all_s = sorted([s for _, _, s_list, _ in analysis_summary for s in s_list if s < price], reverse=True)
    all_r = sorted([r for _, _, _, r_list in analysis_summary for r in r_list if r > price])
    n_s, n_r = (all_s[0] if all_s else 0), (all_r[0] if all_r else 999999)
    
    st.markdown("### 🤖 상세 매매 판단 근거")
    for p in st.session_state.positions:
        if p['type'] == '롱':
            if abs(price-n_r)/price < 0.003: st.warning(f"✅ **롱 익절 근거:** 가격이 {n_r:.2f} 저항선에 닿았습니다. 이 부근에서는 매도세가 강해지므로 이익을 챙기는 것이 안전합니다.")
            if abs(price-n_s)/price < 0.003: st.error(f"❌ **롱 손절 근거:** 가격이 {n_s:.2f} 지지선을 이탈했습니다. 하락 전환 가능성이 커서 손절을 권장합니다.")
        else:
            if abs(price-n_s)/price < 0.003: st.warning(f"✅ **숏 익절 근거:** 가격이 {n_s:.2f} 지지선에 도달했습니다. 반등 확률이 높아 여기서 종료하는 것이 좋습니다.")
            if abs(price-n_r)/price < 0.003: st.error(f"❌ **숏 손절 근거:** 가격이 {n_r:.2f} 저항선을 뚫었습니다. 상승 추세로의 전환 위험이 있어 손절이 필요합니다.")
            
    st.markdown(f"### 📊 종합 분석 점수: {total_score:.1f}")
    if total_score >= 25: st.success(f"🟢 **롱 진입 권장:** 현재 {n_s:.2f} 부근의 지지선이 강력하여 반등을 기대할 수 있습니다.")
    elif total_score <= -25: st.error(f"🔴 **숏 진입 권장:** 현재 {n_r:.2f} 부근의 저항선이 강하여 하락을 기대할 수 있습니다.")
    else: st.info("⚪ **관망 이유:** 현재 가격이 지지선과 저항선 사이에 있어 방향성이 없습니다. 돌파를 확인 후 진입하세요.")

# 하단 버튼 및 로그 (원본 그대로 유지)
b1, b2, b3 = st.columns(3)
if b1.button("롱 진입"): st.session_state.positions.append({'type':'롱', 'entry':price, 'margin':amt, 'lev':lev, 'time':datetime.now().strftime('%H:%M:%S')}); st.session_state.balance-=amt; st.rerun()
if b2.button("숏 진입"): st.session_state.positions.append({'type':'숏', 'entry':price, 'margin':amt, 'lev':lev, 'time':datetime.now().strftime('%H:%M:%S')}); st.session_state.balance-=amt; st.rerun()
if b3.button("❌ 전체 종료"): st.session_state.positions=[]; st.rerun()
st.subheader("거래 로그")
for log in reversed(st.session_state.logs): st.text(log)
time.sleep(0.3); st.rerun()
