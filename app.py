import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components
import pandas as pd

# [필수 엔진 함수]
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
    if df is None or len(df) < 10: return 0, [], []
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
    except: return 0.0

price = get_price()

# 제목 UI
st.markdown("<div style='font-size: 42px; font-weight: bold; margin-bottom: 20px;'>BTC 실시간 트레이딩</div>", unsafe_allow_html=True)

# 매매 모드 선택
col_mode1, col_mode2 = st.columns(2)
with col_mode1: mode_real = st.radio("매매 모드", ["가상 매매", "실전 매매"], key="is_real", horizontal=True)
with col_mode2: mode_margin = st.radio("증거금 모드", ["격리 (Isolated)", "교차 (Cross)"], key="margin_mode", horizontal=True)

if mode_real == "실전 매매": st.error(f"🚨 실전 매매 모드 ({mode_margin}) 입니다.")
else: st.success(f"✅ 가상 매매 모드 ({mode_margin}) 입니다.")

components.html("""<div id="tv"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>""", height=260)

# 자산 및 통계
total_pos_pnl = sum(((price - p['entry']) if p['type']=='롱' else (p['entry']-price))/p['entry']*p['margin']*p['lev'] for p in st.session_state.positions)
total_margin_in_pos = sum(p['margin'] for p in st.session_state.positions)
current_total_asset = st.session_state.balance + total_margin_in_pos + total_pos_pnl

total_wins = sum(float(log.split(": ")[-1].replace(" USDT", "")) for log in st.session_state.logs if float(log.split(": ")[-1].replace(" USDT", "")) > 0)
total_losses = sum(float(log.split(": ")[-1].replace(" USDT", "")) for log in st.session_state.logs if float(log.split(": ")[-1].replace(" USDT", "")) <= 0)

st.metric("실시간 총 자산 (USDT)", f"{current_total_asset:,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{total_pos_pnl:+.2f} USDT")

st.markdown(f"""<div style="font-size: 0.9em; margin-bottom: 20px;">누적: <span style="color: green;">익절 {total_wins:,.2f}</span> / <span style="color: red;">손절 {total_losses:,.2f}</span> USDT</div>""", unsafe_allow_html=True)

col1, col2 = st.columns(2)
lev = col1.slider("레버리지", 1, 125, 10)
amt = col2.number_input("증거금(USDT)", value=100.0)

# 메시지 출력 영역
msg_placeholder = st.empty()
if st.session_state.msg:
    c_class = "msg-success" if st.session_state.msg_type == "success" else "msg-error"
    msg_placeholder.markdown(f'<div class="fixed-msg-area {c_class}">{st.session_state.msg}</div>', unsafe_allow_html=True)
    time.sleep(1); st.session_state.msg = None; st.rerun()
else: msg_placeholder.markdown('<div class="fixed-msg-area" style="background-color: transparent;"></div>', unsafe_allow_html=True)

# 자동 매매 섹션
col_auto1, col_auto2 = st.columns(2)
if st.session_state.auto_trading:
    col_auto1.button("🟢 자동 매매 중", disabled=True, use_container_width=True)
    if col_auto2.button("🔴 자동 매매 종료", use_container_width=True):
        st.session_state.auto_trading = False
        st.session_state.msg = "🔴 자동 매매가 종료되었습니다."; st.session_state.msg_type = "error"
        for p in st.session_state.positions:
            pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
            st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {p['type']} 자동 종료: {pnl:+.2f} USDT")
            st.session_state.balance += (p['margin'] + pnl)
        st.session_state.positions = []; st.rerun()
else:
    if col_auto1.button("🟢 자동 매매 시작", use_container_width=True):
        st.session_state.auto_trading = True; st.session_state.msg = "🟢 자동 매매가 시작되었습니다."; st.session_state.msg_type = "success"; st.rerun()
    col_auto2.button("🔴 자동 매매 종료", disabled=True, use_container_width=True)

# 보유 포지션
st.subheader("보유 중인 포지션")
if not st.session_state.positions: st.write("보유 포지션 없음")
else:
    for p in st.session_state.positions:
        liq_price = p['entry'] * (1 - (1/p['lev'])) if p['type'] == '롱' else p['entry'] * (1 + (1/p['lev']))
        st.markdown(f"""<div style="background-color: #f0f2f6; padding: 10px; border-radius: 10px; margin-bottom: 5px;">
        <div style="font-weight: bold;">{p['time']} | {p['type']} ({p['mode']}) | {p['lev']}x</div>
        <div style="display: flex; justify-content: space-between;"><span>진입가: <b>{p['entry']:.2f}</b></span><span>청산가: <b>{liq_price:.2f}</b></span></div></div>""", unsafe_allow_html=True)

# 매매 분석 엔진 (핵심 상세 설명 로직)
st.subheader("매매 분석 엔진 상태")
with st.expander("🔍 매매 분석 상세 보기 (펼치기)"):
    # 데이터 로직
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
    
    # [설명형 가이드]
    st.markdown("### 🤖 실시간 상세 대응 가이드")
    for p in st.session_state.positions:
        if p['type'] == '롱':
            if abs(price-n_r)/price < 0.003: st.warning(f"✅ **[익절 근거]** {n_r:.2f} 저항선 도달. 매수세가 정체되는 구간이니 수익 실현을 권장합니다.")
            if abs(price-n_s)/price < 0.003: st.error(f"❌ **[손절 근거]** {n_s:.2f} 지지선 이탈. 추가 하락 추세가 우려되므로 손절을 제안합니다.")
        else:
            if abs(price-n_s)/price < 0.003: st.warning(f"✅ **[익절 근거]** {n_s:.2f} 지지선 도달. 여기서 매도세가 꺾일 확률이 높으니 수익을 확보하세요.")
            if abs(price-n_r)/price < 0.003: st.error(f"❌ **[손절 근거]** {n_r:.2f} 저항선 돌파. 상승세로 전환될 확률이 커 손절이 필요합니다.")
            
    decision = "⚪ 시장 관망 (박스권)"
    if total_score >= 25: decision = f"🟢 강력한 롱 진입 구간 ({n_s:.2f} 지지 확인)"
    elif total_score <= -25: decision = f"🔴 강력한 숏 진입 구간 ({n_r:.2f} 저항 확인)"
    st.markdown(f"### 📊 종합 점수: {total_score:.1f}점")
    st.warning(decision)
    for tf, f, s, r in analysis_summary:
        st.markdown(f"**📍 {tf} (점수: {f:.1f})**")
        c1, c2 = st.columns(2)
        c1.write("🛡️ 지지"); c1.table(pd.DataFrame(s[-3:], columns=["Price"])) if s else c1.write("-")
        c2.write("⚔️ 저항"); c2.table(pd.DataFrame(r[-3:], columns=["Price"])) if r else c2.write("-")
        st.divider()

# 버튼 및 로그
st.divider()
b1, b2, b3 = st.columns(3)
if b1.button("롱 진입", use_container_width=True): st.session_state.positions.append({'type':'롱', 'entry':price, 'margin':amt, 'lev':lev, 'mode':mode_margin, 'time':datetime.now().strftime('%H:%M:%S')}); st.session_state.balance -= amt; st.rerun()
if b2.button("숏 진입", use_container_width=True): st.session_state.positions.append({'type':'숏', 'entry':price, 'margin':amt, 'lev':lev, 'mode':mode_margin, 'time':datetime.now().strftime('%H:%M:%S')}); st.session_state.balance -= amt; st.rerun()
if b3.button("❌ 전체 종료", use_container_width=True):
    for p in st.session_state.positions:
        pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {p['type']} 종료: {pnl:+.2f} USDT"); st.session_state.balance += (p['margin'] + pnl)
    st.session_state.positions = []; st.rerun()
if st.button("🔄 가상머니 초기화", use_container_width=True): st.session_state.balance = 10000.0; st.session_state.positions = []; st.session_state.logs = []; st.rerun()
st.subheader("거래 로그")
for log in reversed(st.session_state.logs[-10:]): st.text(log)
time.sleep(0.3); st.rerun()
