import streamlit as st
import json
import time
from datetime import datetime
import streamlit.components.v1 as components
import pandas as pd
import skill

# [엔진 연결용 추가]
import buy_sell_engine

# [데이터 파일에서 읽기: 튜닝 완료]
# 이제 data.json 고정이 아니라, 웹소켓이 실시간으로 갱신하는 1h.json, 4h.json, 1d.json을 동적으로 읽어옵니다.
def get_data_from_file(tf='1h', limit=500):
    try:
        filename = f"{tf.lower()}.json"
        with open(filename, "r") as f:
            data = json.load(f)
            # OKX 웹소켓/API가 주는 9개 로우 데이터 구조를 데이터프레임으로 변환
            df = pd.DataFrame(data)
            # 매매기법(skill) 파일이 정상적으로 읽을 수 있도록 컬럼명을 정확히 매칭합니다.
            df.columns = ['ts', 'o', 'high', 'low', 'close', 'vol', 'volCcy', 'volCcyQuote', 'confirm']
            df[['close', 'high', 'low', 'vol']] = df[['close', 'high', 'low', 'vol']].astype(float)
            
            # 최신 데이터가 위로 가도록 뒤집어서 인덱스를 초기화합니다.
            return df.iloc[::-1].reset_index(drop=True)
    except:
        return None


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
    # [엔진 연결용 추가]
    st.session_state.engine = buy_sell_engine.BuySellEngine()

# 메시지 알림 함수
def set_msg(txt):
    st.session_state.msg_trigger = txt
    if "롱" in txt: st.session_state.msg_color = "#28a745"
    elif "숏" in txt: st.session_state.msg_color = "#dc3545"
    elif "부족" in txt or "종료" in txt: st.session_state.msg_color = "#dc3545"
    else: st.session_state.msg_color = "#333"

# [시세 가져오기 함수: 튜닝 완료]
# 0.1초마다 인터넷 요청을 보내던 requests 기법을 제거하고, 웹소켓이 실시간으로 구워내는 live_price.json 메모리 파일을 읽습니다. (IP 차단 위험 제로)
def get_price():
    try:
        with open("live_price.json", "r") as f:
            price_data = json.load(f)
            return float(price_data.get("price", 0.0))
    except: 
        return 0.0

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
    df = get_data_from_file(tf) # 수정됨
    if df is not None and not df.empty:
        score_sr, supports, resistances, log_msg_sr = skill.calculate_sr_score(price, df) # 수정됨
        score_vol, log_msg_vol = skill.calculate_volume_score(df) # 수정됨
        
        final_score = (score_sr + score_vol) * strategy_tier * t_weight
        total_score += final_score
        log_msg = f"{log_msg_sr} | {log_msg_vol}"
        analysis_summary.append((tf, final_score, supports, resistances, log_msg))

ema_engine = skill.EMASignalEngine() # 수정됨
ema_total_score, ema_results = ema_engine.get_ema_analysis(get_data_from_file) # 수정됨


# --- [EMA 200 추세 기법 추가] ---
df_1h = get_data_from_file('1h') 
long_score, short_score, status = skill.get_dynamic_ema200_score(price, df_1h)

total_score += (long_score + short_score)

st.sidebar.write(f"**EMA 200 감지:** {status}")
st.sidebar.write(f"적용 점수(롱/숏): {long_score}/{short_score}")
# ------------------------------


# [엔진 연결용 추가: 계산된 점수를 엔진에 전달하여 판단 받기]
atr_val = 0.0
if df_1h is not None and not df_1h.empty:
    high_low = df_1h['high'] - df_1h['low']
    atr_val = high_low.rolling(14).mean().iloc[-1]
    if pd.isna(atr_val): atr_val = price * 0.01

market_data = {'atr': atr_val}
ui_settings = {
    'auto_mode': is_auto,
    'risk_pct': 0.02,
    'sl_multiplier': 1.5,
    'rr_ratio': st.session_state.tp_input / st.session_state.sl_input if st.session_state.sl_input > 0 else 2.0
}
decision = st.session_state.engine.get_decision(price, total_score, market_data, ui_settings)


# [엔진 연결용 추가: 오토 모드일 때 자동 진입 수행]
if st.session_state.auto_trading and not st.session_state.positions:
    if decision['action'] == 'LONG' and amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '롱', 'entry': price, 'margin': amt, 'lev': lev, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance -= amt
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 오토매매 | 롱 진입 | 진입가: {price:.2f}")
        set_msg("오토 롱 진입 완료")
        st.rerun()
    elif decision['action'] == 'SHORT' and amt <= st.session_state.balance:
        st.session_state.positions.append({'type': '숏', 'entry': price, 'margin': amt, 'lev': lev, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance -= amt
        st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 오토매매 | 숏 진입 | 진입가: {price:.2f}")
        set_msg("오토 숏 진입 완료")
        st.rerun()


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
    strategies = [
        {"name": "지지 저항 분석", "detected": (len(analysis_summary) > 0)},
        {"name": "거래량 분석", "detected": (len(analysis_summary) > 0)},
        {"name": "EMA 변곡점/정/역배열", "detected": (abs(ema_total_score) > 0)},
        {"name": "EMA 200 추세", "detected": True},
    ]
    detected_strats = [s for s in strategies if s.get('detected')]

    current_name = detected_strats[0]['name'] if detected_strats else "대기 중"
    st.markdown(f"#### 📊 현재 전략: {current_name}")

    with st.expander("🔍 상세 분석 및 전체 기법 현황", expanded=True):
        st.markdown("###### 📋 감지된 기법 상세 내용")
        if not detected_strats:
            st.info("현재 감지된 전략 없음")
        else:
            for s in detected_strats:
                st.markdown(f"---")
                st.markdown(f"###### 🚩 기법: {s['name']}")
                
                if s['name'] == "EMA 200 추세":
                    st.write(f"<small><b>현재 봇의 판단:</b> {status}</small>", unsafe_allow_html=True)
                    st.write(f"<small>1. <b>추세 판단:</b> 현재 가격은 200 EMA {'상단' if '상승' in status else '하단'}에 위치하여 <b>{status}</b>입니다.</small>", unsafe_allow_html=True)
                    st.write(f"<small>2. <b>진입 원칙:</b> {status} 방향에 맞춰 롱/숏 가점 및 감점을 실시간으로 적용합니다.</small>", unsafe_allow_html=True)
                    st.write(f"<small>3. <b>손절 대응:</b> 200 EMA {'하향 이탈' if '상승' in status else '상향 돌파'} 시 추세 훼손으로 간주하고 포지션을 즉시 정리합니다.</small>", unsafe_allow_html=True)
                    st.write("<small>4. <b>횡보/변동성:</b> EMA 근처 횡보 구간은 휩쏘 위험이 높으므로 방향성 확정 후 전략을 수행합니다.</small>", unsafe_allow_html=True)
                    st.write("<small>5. <b>익절 전략:</b> 추세 가속 시 분할 익절하고, 가점 점수가 낮아지면 전량 청산하여 수익을 확보합니다.</small>", unsafe_allow_html=True)
                
                elif s['name'] == "EMA 변곡점/정/역배열":
                    st.write("<small>1. <b>현재 배열 상태:</b> 현재 EMA는 " + ("<b>정배열(상승장)</b> 상태입니다." if ema_total_score > 0 else "<b>역배열(하락장)</b> 상태입니다.") + "</small>", unsafe_allow_html=True)
                    st.write("<small>2. <b>진입 및 대응:</b> " + ("정배열 시 가격이 EMA 지지를 받는 눌림목 구간에서 롱 진입을 노립니다." if ema_total_score > 0 else "역배열 시 가격이 EMA 저항을 받는 반등 구간에서 숏 진입을 노립니다.") + "</small>", unsafe_allow_html=True)
                    st.write("<small>3. <b>변곡점(EMA 수렴):</b> EMA 이평선들이 한 점으로 모이는 구간은 에너지가 응축되는 <b>변곡점</b>입니다. 이 구간에서 급격한 방향 전환이 발생하므로 추격 매수를 자제합니다.</small>", unsafe_allow_html=True)
                    st.write("<small>4. <b>리스크 관리:</b> 이평선 간격이 과도하게 벌어지면 기술적 반등(평균 회귀)이 일어날 수 있으니 익절을 우선시합니다.</small>", unsafe_allow_html=True)

                elif s['name'] == "지지 저항 분석":
                    for tf, f_score, sup, res, log_msg in analysis_summary:
                        st.session_state.total_score += f_score
                        st.write(f"<small><b>[시간대: {tf}]</b></small>", unsafe_allow_html=True)
                        st.write(f"<small>1. <b>현재 상황:</b> 지지선 {sup}, 저항선 {res} 사이에서 시장 변동성을 확인했습니다.</small>", unsafe_allow_html=True)
                        st.write(f"<small>2. <b>돌파 시나리오:</b> {'저항 상향 돌파 시 롱 진입' if f_score > 0 else '지지 하향 이탈 시 숏 진입'}.</small>", unsafe_allow_html=True)
                        st.write("<small>3. <b>리테스트:</b> 돌파 후 해당 지지/저항선을 다시 테스트할 때 지지받지 못하면 '가짜 돌파(휩쏘)'로 간주하고 즉시 손절합니다.</small>", unsafe_allow_html=True)
                        st.write("<small>4. <b>거래량 검증:</b> 거래량이 뒷받침되지 않은 돌파는 신뢰도가 낮으므로 진입 규모를 50% 이하로 낮추어 리스크를 관리합니다.</small>", unsafe_allow_html=True)
                        st.write(f"<small>5. <b>로그 분석:</b> {log_msg}</small>", unsafe_allow_html=True)

    with st.expander("⚙️ 전체 기법 리스트"):
        for strat in strategies:
            col1, col2 = st.columns([0.15, 0.85])
            if strat.get('detected'):
                col1.markdown("<small>🟢</small>", unsafe_allow_html=True)
                col2.markdown(f"<small>◆ {strat['name']}</small>", unsafe_allow_html=True)
            else:
                col1.markdown("", unsafe_allow_html=True)
                col2.markdown(f"<small>◆ {strat['name']}</small>", unsafe_allow_html=True)


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

