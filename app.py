import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components
import pandas as pd

# [필수 엔진 함수: 500개 캔들 호출]
def get_klines(tf='1h', limit=500):
    url = f"https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar={tf}&limit={limit}"
    try:
        r = requests.get(url, timeout=2)
        data = r.json().get('data', [])
        if not data: return None
        df = pd.DataFrame(data, columns=['ts', 'o', 'h', 'l', 'close', 'vol', 'confirm'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['vol'] = df['vol'].astype(float)
        return df.iloc[::-1].reset_index(drop=True)
    except: return None

# [지지 저항선 분석 엔진]
def calculate_sr_score(price, df):
    is_high = (df['high'] > df['high'].shift(1)) & (df['high'] > df['high'].shift(-1))
    is_low = (df['low'] < df['low'].shift(1)) & (df['low'] < df['low'].shift(-1))
    pivots_h = df[is_high][['high', 'vol']].copy()
    pivots_l = df[is_low][['low', 'vol']].copy()
    
    near_h = pivots_h[(pivots_h['high'] - price).abs() / price < 0.007]
    near_l = pivots_l[(pivots_l['low'] - price).abs() / price < 0.007]
    
    avg_vol = df['vol'].mean()
    sup_score = (len(near_l) * 20) + (near_l['vol'].max() / avg_vol * 10 if not near_l.empty else 0)
    res_score = (len(near_h) * 20) + (near_h['vol'].max() / avg_vol * 10 if not near_h.empty else 0)
    
    score = sup_score - res_score
    # 브리핑 내용이 상세하게 표기되도록 수정
    logic_msg = f"지지선 {len(near_l)}개 감지(점수:{sup_score:.1f}), 저항선 {len(near_h)}개 감지(점수:{res_score:.1f})"
    return score, list(near_l['low']), list(near_h['high']), logic_msg

def calculate_volume_score(df):
    avg_vol = df['vol'].mean()
    last_vol = df.iloc[-1]['vol']
    ratio = last_vol / avg_vol
    if ratio < 0.9:
        score = 0
    else:
        score = min((ratio - 0.9) * 100, 100)
    msg = f"거래량 점수: {score:.1f}점 (평균 대비 {ratio:.2f}배)"
    return score, msg

# [ema변곡.정.역배열]
class EMASignalEngine:
    def __init__(self):
        self.weights = {'1M': 5.0, '1W': 4.0, '1d': 3.0, '4h': 2.0, '1h': 1.0}
    
    def calculate_ema_status(self, df):
        e20 = df['close'].rolling(20).mean().iloc[-1]
        e60 = df['close'].rolling(60).mean().iloc[-1]
        e120 = df['close'].rolling(120).mean().iloc[-1]
        e200 = df['close'].rolling(200).mean().iloc[-1]
        
        is_bullish = (e20 > e60 > e120 > e200)
        is_bearish = (e200 > e120 > e60 > e20)
        gap = abs(e20 - e200) / e200
        
        if 0.001 <= gap < 0.005: return "EMA 변곡점", 2
        elif gap >= 0.005:
            if is_bullish: return "EMA 정배열", 8
            elif is_bearish: return "EMA 역배열", -8
        return "횡보", 0

    def get_ema_analysis(self):
        results = []
        total_score = 0
        for tf in ['1h', '4h', '1d', '1W', '1M']:
            df = get_klines(tf)
            if df is not None:
                msg, score = self.calculate_ema_status(df)
                weighted_score = score * self.weights.get(tf, 1)
                total_score += weighted_score
                results.append((tf, msg, weighted_score))
        return total_score, results



# 페이지 설정
st.set_page_config(page_title="BTC Bot", layout="centered")

# [중앙 오버레이 알림 기능 구현]
if 'msg_trigger' not in st.session_state: st.session_state.msg_trigger = None
if 'msg_color' not in st.session_state: st.session_state.msg_color = "#333"

st.markdown("""
    <style>
    .toast-overlay {
        position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
        z-index: 9999; padding: 15px 30px; border-radius: 8px; font-size: 16px; font-weight: bold;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3); background: white; 
        border: 2px solid; white-space: nowrap; text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

if st.session_state.msg_trigger:
    st.markdown(f'<div class="toast-overlay" style="border-color: {st.session_state.msg_color}; color: {st.session_state.msg_color};">{st.session_state.msg_trigger}</div>', unsafe_allow_html=True)
    time.sleep(1.2)
    st.session_state.msg_trigger = None
    st.rerun()

# 세션 상태 초기화
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

# 메시지 알림 함수
def set_msg(txt):
    st.session_state.msg_trigger = txt
    if "롱" in txt: st.session_state.msg_color = "#28a745"
    elif "숏" in txt: st.session_state.msg_color = "#dc3545"
    elif "부족" in txt or "종료" in txt: st.session_state.msg_color = "#dc3545"
    else: st.session_state.msg_color = "#333"

# 시세 가져오기 함수
def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=2)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

price = get_price()

# 제목
st.markdown("<div style='font-size: 42px; font-weight: bold; margin-bottom: 20px;'>BTC 실시간 트레이딩</div>", unsafe_allow_html=True)

# [설정 UI 영역]
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
components.html("""
<div id="tv"></div>
<script src="https://s3.tradingview.com/tv.js"></script>
<script>new TradingView.widget({"width":"100%","height":250,"symbol":"OKX:BTCUSDT","theme":"light","container_id":"tv"});</script>
""", height=260)

# [계산 로직 사전 실행]
time_weights = {'1M': 16.0, '1W': 8.0, '1d': 4.0, '4h': 2.0, '1h': 1.0}
total_score = 0
analysis_summary = []
strategy_tier = 1.5 
for tf, t_weight in time_weights.items():
    df = get_klines(tf)
    if df is not None and not df.empty:
        score_sr, supports, resistances, log_msg_sr = calculate_sr_score(price, df)
        score_vol, log_msg_vol = calculate_volume_score(df)
        
        final_score = (score_sr + score_vol) * strategy_tier * t_weight
        total_score += final_score
        log_msg = f"{log_msg_sr} | {log_msg_vol}"
        analysis_summary.append((tf, final_score, supports, resistances, log_msg))

ema_engine = EMASignalEngine()
ema_total_score, ema_results = ema_engine.get_ema_analysis()
total_score += ema_total_score


# 자동 청산 로직
for p in st.session_state.positions[:]:
    pnl_pct = ((price - p['entry']) if p['type']=='롱' else (p['entry']-price)) / p['entry'] * 100 * p['lev']
    if st.session_state.mode == "수동":
        target_tp, target_sl = st.session_state.tp_input, st.session_state.sl_input
    else:
        target_tp = 3.5 + (max(0, abs(total_score) - 25) / 10) 
        target_sl = 1.5
    
    if pnl_pct >= target_tp or pnl_pct <= -target_sl:
        action = "익절" if pnl_pct > 0 else "손절"
        pnl_val = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
        if pnl_val > 0: st.session_state.wins_total += pnl_val
        else: st.session_state.losses_total += abs(pnl_val)
        
        log_type = "자동" if st.session_state.auto_trading else "수동"
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {log_type}매매 | {p['type']} 포지션 {action} | 진입가: {p['entry']:.2f} | 수익: {pnl_val:+.2f} USDT")
        
        st.session_state.balance += (p['margin'] + pnl_val)
        st.session_state.positions.remove(p)
        st.rerun()

# 자산 계산 로직
total_pos_pnl = sum(((price - p['entry']) if p['type']=='롱' else (p['entry']-price))/p['entry']*p['margin']*p['lev'] for p in st.session_state.positions)
current_total_asset = 10000.0 + st.session_state.wins_total - st.session_state.losses_total + total_pos_pnl

st.metric("실시간 총 자산 (USDT)", f"{current_total_asset:,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{total_pos_pnl:+.2f} USDT")

st.markdown(f"""
<div style="font-size: 16px; margin-bottom: 20px;">
누적: <span style="color: green;">익절 {st.session_state.wins_total:,.2f}</span> / <span style="color: red;">손절 {st.session_state.losses_total:,.2f}</span> USDT
</div>
""", unsafe_allow_html=True)

# 자동 매매 제어 영역
with st.container(border=True):
    if st.session_state.auto_trading:
        st.markdown("<div style='text-align: center; color: green; font-weight: bold; margin-bottom: 10px;'>🟢 현재 상태: 자동 매매 중</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='text-align: center; color: gray; font-weight: bold; margin-bottom: 10px;'>⚪ 현재 상태: 자동 매매 대기 중</div>", unsafe_allow_html=True)
    
    col_auto1, col_auto2 = st.columns(2)
    if st.session_state.auto_trading:
        col_auto1.button("🟢 자동 매매 중", disabled=True, use_container_width=True)
        if col_auto2.button("🔴 자동 매매 종료", use_container_width=True):
            st.session_state.auto_trading = False
            set_msg("자동 매매가 종료되었습니다.")
            st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 자동매매 | 자동 매매 모드 종료")
            for p in st.session_state.positions:
                pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
                if pnl > 0: st.session_state.wins_total += pnl
                else: st.session_state.losses_total += abs(pnl)
                st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 자동매매 | {p['type']} 포지션 강제종료 | 수익: {pnl:+.2f} USDT")
                st.session_state.balance += (p['margin'] + pnl)
            st.session_state.positions = []
            st.rerun()
    else:
        if col_auto1.button("🟢 자동 매매 시작", use_container_width=True):
            st.session_state.auto_trading = True
            st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 시스템 | 자동 매매를 시작했습니다.")
            set_msg("자동 매매가 시작되었습니다.")
            st.rerun()
        col_auto2.button("🔴 자동 매매 종료", disabled=True, use_container_width=True)

st.subheader("보유 중인 포지션")
if not st.session_state.positions:
    st.write("보유 포지션 없음")
else:
    for i, p in enumerate(st.session_state.positions):
        pnl = ((price - p['entry']) if p['type']=='롱' else (p['entry']-price))/p['entry']*p['margin']*p['lev']
        liq_price = p['entry'] * (1 - (1 / p['lev'])) if p['type'] == '롱' else p['entry'] * (1 + (1 / p['lev']))
        
        c_pos1, c_pos2 = st.columns([0.8, 0.2])
        with c_pos1:
            st.markdown(f"""
            <div style="background-color: #f0f2f6; padding: 10px; border-radius: 10px; margin-bottom: 5px; font-size: 16px;">
            <div style="font-weight: bold;">{p['time']} | {p['type']} | {p['lev']}x | 수익손실: <b style="color: {'red' if pnl < 0 else 'blue'};">{pnl:+.2f} USDT</b></div>
            <div style="display: flex; justify-content: space-between;">
            <span>진입가: <b>{p['entry']:.2f}</b></span>
            <span>청산가: <b style="color: red;">{liq_price:.2f}</b></span>
            </div>
            </div>
            """, unsafe_allow_html=True)
        with c_pos2:
            if st.button("종료 X", key=f"close_{i}"):
                if pnl > 0: st.session_state.wins_total += pnl
                else: st.session_state.losses_total += abs(pnl)
                st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 수동매매 | {p['type']} 포지션 수동 종료 | 수익: {pnl:+.2f} USDT")
                st.session_state.balance += (p['margin'] + pnl)
                st.session_state.positions.pop(i)
                set_msg(f"{p['type']} 포지션 정리 완료")
                st.rerun()

# [섹션 분리: 매매 점수와 신호]
st.subheader("매매 신호 상태")
with st.container(border=True):
    st.markdown(f"<p style='font-size: 24px; font-weight: bold;'>📊 종합 매매 점수: {total_score:.1f}점</p>", unsafe_allow_html=True)
    status_col1, status_col2 = st.columns(2)
    if st.session_state.positions:
        p = st.session_state.positions[0]
        pnl_val = ((price - p['entry']) if p['type']=='롱' else (p['entry']-price)) / p['entry'] * 100
        if pnl_val > 0: status_col2.success(f"🟢 익절 신호")
        else: status_col2.error(f"🔴 손절 신호")
    elif total_score >= 25: status_col2.success("🟢 롱 진입 신호")
    elif total_score <= -25: status_col2.error("🔴 숏 진입 신호")
    else: status_col2.warning("⚪ 신호: 대기 중")

# [섹션 분리: 매매 분석 엔진 및 상세 보기]
st.subheader("매매 분석 엔진")
with st.container(border=True):
    # 1. 감지된 전략들 리스트 (이곳에 추후 기법들을 30개 이상 추가하세요)
    strategies = [
        {"name": "지지 저항 분석", "detected": (len(analysis_summary) > 0)},
        {"name": "거래량 분석", "detected": (len(analysis_summary) > 0)},
        {"name": "EMA 변곡점/정/역배열", "detected": (abs(ema_total_score) > 0)},


    ]
    active_strats = [s for s in strategies if s['detected']]

    # 2. 현재 전략 실시간 표시 (감지된 것이 없을 때 예외 처리)
    if not active_strats:
        st.info("📊 현재 전략: 감지된 매매 기법 없음")
    else:
        st.info("📊 현재 전략: 지지 저항 분석")
        for s in active_strats:
            st.markdown(f"**🔥 감지된 전략: {s['name']}**")
    
    # 3. 상세 분석 보기 (감지된 전략만 상세 설명)
            with st.expander("🔍 상세 분석 보기", expanded=True):
                    if not active_strats:
            st.write("📈 **EMA 분석 상세**")
            for tf, msg, sc in ema_results:
                    if msg != "횡보":
                    st.write(f"📍 **[{tf}]** {msg} (가중점수: {sc:.1f})")
            st.write("---")
            st.write("현재 조건에 부합하는 매매 기법 없음.")
                else:
            for s in active_strats:
                if s['name'] == "지지 저항 분석":
                    for tf, f_score, sup, res, log_msg in analysis_summary:
                        st.write(f"📍 **[{tf}]** {log_msg}")

    # 4. 전체 매매 기법 관리 (펼쳐보기)
    with st.expander("⚙️ 전체 매매 기법 리스트 확인"):
        for strat in strategies:
            col_s1, col_s2 = st.columns([0.8, 0.2])
            col_s1.write(f"🔹 {strat['name']}")
            if strat['detected']:
                col_s2.markdown("🟢")

st.divider()
st.subheader("수동 매매")
b1, b2, b3 = st.columns(3)
if b1.button("롱 진입", use_container_width=True):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance -= amt
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 수동매매 | 롱 진입 | 진입가: {price:.2f}")
        set_msg("수동 롱 진입 완료")
        st.rerun()
    else: set_msg("잔액 부족")
if b2.button("숏 진입", use_container_width=True):
    if amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance -= amt
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 수동매매 | 숏 진입 | 진입가: {price:.2f}")
        set_msg("수동 숏 진입 완료")
        st.rerun()
    else: set_msg("잔액 부족")
if b3.button("❌ 전체 종료", use_container_width=True):
    for p in st.session_state.positions:
        pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
        if pnl > 0: st.session_state.wins_total += pnl
        else: st.session_state.losses_total += abs(pnl)
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 수동매매 | 전체 포지션 강제종료 | 수익: {pnl:+.2f} USDT")
    st.session_state.positions = []
    set_msg("전체 포지션 종료")
    st.rerun()
if st.button("🔄 가상머니 초기화", use_container_width=True):
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.session_state.wins_total = 0.0
    st.session_state.losses_total = 0.0
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 시스템 | 가상머니 초기화 완료")
    set_msg("초기화 완료")
    st.rerun()

st.subheader("거래 로그")
for log in reversed(st.session_state.logs[-15:]): st.text(log)
time.sleep(0.3)
st.rerun()
