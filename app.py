import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components
import pandas as pd

# [필수 엔진 함수] - 스윙 매매를 위해 데이터 개수 조정
def get_klines(tf='4h', limit=100):
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
    logic_msg = ""
    for s in supports[-3:]:
        if abs(price - s) / price < 0.005: 
            score += 3
            logic_msg += f"지지선 {s:.2f} 근접. "
    for r in resistances[-3:]:
        if abs(price - r) / price < 0.005: 
            score -= 3
            logic_msg += f"저항선 {r:.2f} 근접. "
    return score, supports, resistances, logic_msg

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

# [계산 로직 사전 실행 - 스윙 매매(주봉, 일봉, 4시간봉) 최적화]
time_weights = {'1W': 8.0, '1d': 4.0, '4h': 2.0}
total_score = 0
analysis_summary = []
strategy_tier = 1.5 
for tf, t_weight in time_weights.items():
    limit_val = 50 if tf == '1W' else 100
    df = get_klines(tf, limit=limit_val)
    if df is not None and not df.empty:
        score, supports, resistances, log_msg = calculate_sr_score(price, df)
        final_score = score * strategy_tier * t_weight
        total_score += final_score
        analysis_summary.append((tf, final_score, supports, resistances, log_msg))
    del df
    time.sleep(0.5)

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
        pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
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
    st.info("📊 현재 전략: 매물대 분석")
    with st.expander("🔍 상세 분석 보기", expanded=True):
        strategies = [
            {"name": "강력한 지지선 반등", "score": 15, "condition": lambda p, s, r: any(abs(p - sup) / p < 0.005 for sup in s), "desc": "강력한 지지선 근접."},
            {"name": "저항선 돌파 실패", "score": -10, "condition": lambda p, s, r: any(abs(p - res) / p < 0.005 for res in r), "desc": "저항선 근접 및 돌파 실패."}
        ]
        active_strategies = []
        for tf, f_score, sup, res, log in analysis_summary:
            for strat in strategies:
                if strat["condition"](price, sup, res):
                    active_strategies.append((tf, strat))
        if not active_strategies: st.write("현재 조건에 부합하는 매매 기법 없음.")
        else:
            for tf, strat in active_strategies:
                st.markdown(f"**[{tf}] {strat['name']}**")
        st.divider()
        for tf, f_score, sup, res, log in analysis_summary:
            st.write(f"📍 {tf} 타임프레임 요약")
            c1, c2 = st.columns(2)
            c1.table(pd.DataFrame(sup[-2:], columns=["지지"]))
            c2.table(pd.DataFrame(res[-2:], columns=["저항"]))

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
time.sleep(20.0)
st.rerun()

