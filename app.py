Import streamlit as st
Import requests
Import time
From datetime import datetime
Import streamlit.components.v1 as components
Import pandas as pd

# [필수 엔진 함수]
Def get_klines(tf=’1h’, limit=50):
    url = fhttps://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar={tf}&limit={limit}
    try:
        r = requests.get(url, timeout=2)
        data = r.json().get(‘data’, [])
        if not data: return None
        df = pd.DataFrame(data, columns=[‘ts’, ‘o’, ‘h’, ‘l’, ‘close’, ‘vol’, ‘confirm’])
        df[‘close’] = df[‘close’].astype(float)
        df[‘high’] = df[‘high’].astype(float)
        df[‘low’] = df[‘low’].astype(float)
        return df.iloc[::-1].reset_index(drop=True)
    except: return None

def calculate_sr_score(price, df):
    supports = [df[‘low’].iloc[i] for i in range(5, len(df)-5) if df[‘low’].iloc[i] < df[‘low’].iloc[i-5:i].min() and df[‘low’].iloc[i] < df[‘low’].iloc[i+1:i+6].min()]
    resistances = [df[‘high’].iloc[i] for i in range(5, len(df)-5) if df[‘high’].iloc[i] > df[‘high’].iloc[i-5:i].max() and df[‘high’].iloc[i] > df[‘high’].iloc[i+1:i+6].max()]
    score = 0
    for s in supports[-3:]:
        if abs(price – s) / price < 0.005: score += 3
    for r in resistances[-3:]:
        if abs(price – r) / price < 0.005: score -= 3
    return score, supports, resistances

# 페이지 설정
St.set_page_config(page_title=”BTC Bot”, layout=”centered”)

# CSS: 메시지 영역 및 스타일
St.markdown(“””
    <style>
    .fixed-msg-area { height: 70px; display: flex; align-items: center; justify-content: center; margin-bottom: 20px; border-radius: 5px; font-weight: bold; width: 100%; }
    .msg-success { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .msg-error { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    </style>
“””, unsafe_allow_html=True)

# 세션 상태 초기화
If ‘balance’ not in st.session_state:
    St.session_state.balance = 10000.0
    St.session_state.positions = []
    St.session_state.logs = []
    St.session_state.auto_trading = False
    St.session_state.msg = None
    St.session_state.msg_type = None

# 시세 가져오기 함수
Def get_price():
    Try:
        R = requests.get(https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT, timeout=2)
        Return float(r.json()[‘data’][0][‘last’])
    Except:
        Return 0.0

Price = get_price()

# 제목
St.markdown(“<div style=’font-size: 42px; font-weight: bold; margin-bottom: 20px;’>BTC 실시간 트레이딩</div>”, unsafe_allow_html=True)

# 실전/가상 매매 및 교차/격리 모드 선택
Col_mode1, col_mode2 = st.columns(2)
With col_mode1:
    Mode_real = st.radio(“매매 모드”, [“가상 매매”, “실전 매매”], key=”is_real”, horizontal=True)
With col_mode2:
    Mode_margin = st.radio(“증거금 모드”, [“격리 (Isolated)”, “교차 (Cross)”], key=”margin_mode”, horizontal=True)

If mode_real == “실전 매매”:
    St.error(f”🚨 실전 매매 모드 ({mode_margin}) 입니다.”)
Else:
    St.success(f”✅ 가상 매매 모드 ({mode_margin}) 입니다.”)

Components.html(“””
<div id=”tv”></div>
<script src=https://s3.tradingview.com/tv.js></script>
<script>new TradingView.widget({“width”:”100%”,”height”:250,”symbol”:”OKX:BTCUSDT”,”theme”:”light”,”container_id”:”tv”});</script>
“””, height=260)

Total_pos_pnl = sum(((price – p[‘entry’]) if p[‘type’]==’롱’ else (p[‘entry’]-price))/p[‘entry’]*p[‘margin’]*p[‘lev’] for p in st.session_state.positions)
Total_margin_in_pos = sum(p[‘margin’] for p in st.session_state.positions)
Current_total_asset = st.session_state.balance + total_margin_in_pos + total_pos_pnl

Total_wins = sum(float(log.split(“: “)[-1].replace(“ USDT”, “”)) for log in st.session_state.logs if float(log.split(“: “)[-1].replace(“ USDT”, “”)) > 0)
Total_losses = sum(float(log.split(“: “)[-1].replace(“ USDT”, “”)) for log in st.session_state.logs if float(log.split(“: “)[-1].replace(“ USDT”, “”)) <= 0)

St.metric(“실시간 총 자산 (USDT)”, f”{current_total_asset:,.2f}”)
St.metric(“현재 변동 금액 (USDT)”, f”{total_pos_pnl:+.2f} USDT”)

St.markdown(f”””
<div style=”font-size: 16px; margin-bottom: 20px;”>
누적: <span style=”color: green;”>익절 {total_wins:,.2f}</span> / <span style=”color: red;”>손절 {total_losses:,.2f}</span> USDT
</div>
“””, unsafe_allow_html=True)

Col1, col2 = st.columns(2)
Lev = col1.slider(“레버리지”, 1, 125, 10)
Amt = col2.number_input(“증거금(USDT)”, value=100.0)

# 메시지 출력 영역
Msg_placeholder = st.empty()
If st.session_state.msg:
    C_class = “msg-success” if st.session_state.msg_type == “success” else “msg-error”
    Msg_placeholder.markdown(f’<div class=”fixed-msg-area {c_class}”>{st.session_state.msg}</div>’, unsafe_allow_html=True)
    Time.sleep(1)
    St.session_state.msg = None
    St.rerun()
Else:
    Msg_placeholder.markdown(‘<div class=”fixed-msg-area” style=”background-color: transparent;”></div>’, unsafe_allow_html=True)

# 자동 매매 섹션
Col_auto1, col_auto2 = st.columns(2)
If st.session_state.auto_trading:
    Col_auto1.button(“🟢 자동 매매 중”, disabled=True, use_container_width=True)
    If col_auto2.button(“🔴 자동 매매 종료”, use_container_width=True):
        St.session_state.auto_trading = False
        St.session_state.msg = “🔴 자동 매매가 종료되었습니다.”
        St.session_state.msg_type = “error”
        For p in st.session_state.positions:
            Pnl = ((price – p[‘entry’] if p[‘type’]==’롱’ else p[‘entry’]-price)/p[‘entry’])*p[‘margin’]*p[‘lev’]
            If p[‘mode’] == “교차 (Cross)” and (p[‘margin’] + pnl) <= 0: pnl = -p[‘margin’]
            St.session_state.logs.append(f”[{datetime.now().strftime(‘%H:%M:%S’)}] {p[‘type’]} 자동 종료({p[‘mode’]}): {pnl:+.2f} USDT”)
            St.session_state.balance += (p[‘margin’] + pnl)
        St.session_state.positions = []
        St.rerun()
Else:
    If col_auto1.button(“🟢 자동 매매 시작”, use_container_width=True):
        St.session_state.auto_trading = True
        St.session_state.msg = “🟢 자동 매매가 시작되었습니다.”
        St.session_state.msg_type = “success”
        St.rerun()
    Col_auto2.button(“🔴 자동 매매 종료”, disabled=True, use_container_width=True)

# 보유 중인 포지션
St.subheader(“보유 중인 포지션”)
If not st.session_state.positions:
    St.write(“보유 포지션 없음”)
Else:
    For p in st.session_state.positions:
        Liq_price = p[‘entry’] * (1 – (1 / p[‘lev’])) if p[‘type’] == ‘롱’ else p[‘entry’] * (1 + (1 / p[‘lev’]))
        St.markdown(f”””
        <div style=”background-color: #f0f2f6; padding: 10px; border-radius: 10px; margin-bottom: 5px; font-size: 16px;”>
        <div style=”font-weight: bold;”>{p[‘time’]} | {p[‘type’]} ({p[‘mode’]}) | {p[‘lev’]}x</div>
        <div style=”display: flex; justify-content: space-between;”>
        <span>진입가: <b style=”color: blue;”>{p[‘entry’]:.2f}</b></span>
        <span>청산가: <b style=”color: red;”>{liq_price:.2f}</b></span>
        </div>
        </div>
        “””, unsafe_allow_html=True)

# [계산 로직 사전 실행]
Time_weights = {‘1M’: 16.0, ‘1W’: 8.0, ‘1d’: 4.0, ‘4h’: 2.0, ‘1h’: 1.0}
Total_score = 0
Analysis_summary = []
Strategy_tier = 1.5 
For tf, t_weight in time_weights.items():
    Df = get_klines(tf)
    If df is not None and not df.empty:
        Score, supports, resistances = calculate_sr_score(price, df)
        Final_score = score * strategy_tier * t_weight
        Total_score += final_score
        Analysis_summary.append((tf, final_score, supports, resistances))
Decision = “⚪ 시장 관망”
If total_score >= 25: decision = “🟢 강력한 롱 진입 구간”
Elif total_score <= -25: decision = “🔴 강력한 숏 진입 구간”

# [1. 종합 매매 점수 칸]
With st.container(border=True):
    St.markdown(f”<p style=’font-size: 24px; font-weight: bold;’>📊 종합 매매 점수: {total_score:.1f}점</p>”, unsafe_allow_html=True)

# [2. 매매 분석 엔진 상태 칸]
With st.container(border=True):
    St.markdown(“<p style=’font-size: 22px; font-weight: bold;’>매매 분석 엔진 상태</p>”, unsafe_allow_html=True)
    Status_col1, status_col2 = st.columns(2)
    Status_col1.info(“📊 현재 전략: 매물대 분석”)
    Status_col2.warning(“⚪ 신호: 계산 중”)
    
    With st.expander(“🔍 매매 분석 상세 보기 (펼치기)”):
        St.markdown(“<p style=’font-size: 20px; font-weight: bold;’>📋 기법별 상세 분석 근거</p>”, unsafe_allow_html=True)
        If total_score > 10: st.markdown(“<p style=’font-size: 16px; color: green;’>✅ **분석: 지지 구간 강세** - 종합 점수가 지지 우위를 가리킵니다.</p>”, unsafe_allow_html=True)
        Elif total_score < -10: st.markdown(“<p style=’font-size: 16px; color: red;’>✅ **분석: 저항 구간 강세** - 종합 점수가 저항 우위를 가리킵니다.</p>”, unsafe_allow_html=True)
        Else: st.markdown(“<p style=’font-size: 16px; color: grey;’>✅ **분석: 중립** - 방향성 확인 필요.</p>”, unsafe_allow_html=True)
        
        St.markdown(“<p style=’font-size: 20px; font-weight: bold;’>💡 최종 행동 가이드</p>”, unsafe_allow_html=True)
        If total_score >= 25: 
            St.markdown(“<p style=’font-size: 16px;’>👉 **롱 진입:** 종합 점수가 매우 강한 롱을 가리킵니다. 조건 충족 시 진입합니다.</p>”, unsafe_allow_html=True)
        Elif total_score <= -25: 
            St.markdown(“<p style=’font-size: 16px;’>👉 **숏 진입:** 종합 점수가 매우 강한 숏을 가리킵니다. 조건 충족 시 진입합니다.</p>”, unsafe_allow_html=True)
        Else: 
            St.markdown(“<p style=’font-size: 16px;’>👉 **모니터링:** 최적의 타점을 위해 신호를 실시간으로 계산하고 있습니다.</p>”, unsafe_allow_html=True)

        For tf, f_score, sup, res in analysis_summary:
            St.markdown(f”<p style=’font-size: 18px; font-weight: bold;’>📍 {tf} 차트 (가중 점수: {f_score:.1f})</p>”, unsafe_allow_html=True)
            C1, c2 = st.columns(2)
            C1.markdown(“<p style=’font-size: 16px;’>🛡️ 지지</p>”, unsafe_allow_html=True)
            C1.table(pd.DataFrame(sup[-3:], columns=[“Price”]))
            C2.markdown(“<p style=’font-size: 16px;’>⚔️ 저항</p>”, unsafe_allow_html=True)
            C2.table(pd.DataFrame(res[-3:], columns=[“Price”]))
            St.divider()

St.divider()

# 매매 버튼
B1, b2, b3 = st.columns(3)
If b1.button(“롱 진입”, use_container_width=True):
    If amt <= st.session_state.balance:
        St.session_state.positions.append({‘type’: ‘롱’, ‘entry’: price, ‘margin’: amt, ‘lev’: lev, ‘mode’: mode_margin, ‘time’: datetime.now().strftime(‘%H:%M:%S’)})
        St.session_state.balance -= amt
        St.session_state.msg = “🟢 롱 포지션 진입 완료!”
        St.session_state.msg_type = “success”
        St.rerun()
    Else:
        St.session_state.msg = “❌ 잔고 부족!”
        St.session_state.msg_type = “error”
        St.rerun()

If b2.button(“숏 진입”, use_container_width=True):
    If amt <= st.session_state.balance:
        St.session_state.positions.append({‘type’: ‘숏’, ‘entry’: price, ‘margin’: amt, ‘lev’: lev, ‘mode’: mode_margin, ‘time’: datetime.now().strftime(‘%H:%M:%S’)})
        St.session_state.balance -= amt
        St.session_state.msg = “🔴 숏 포지션 진입 완료!”
        St.session_state.msg_type = “error”
        St.rerun()
    Else:
        St.session_state.msg = “❌ 잔고 부족!”
        St.session_state.msg_type = “error”
        St.rerun()

If b3.button(“❌ 전체 포지션 종료”, use_container_width=True):
    For p in st.session_state.positions:
        Pnl = ((price – p[‘entry’] if p[‘type’]==’롱’ else p[‘entry’]-price)/p[‘entry’])*p[‘margin’]*p[‘lev’]
        If p[‘mode’] == “교차 (Cross)” and (p[‘margin’] + pnl) <= 0: pnl = -p[‘margin’]
        St.session_state.logs.append(f”[{datetime.now().strftime(‘%H:%M:%S’)}] {p[‘type’]} 종료({p[‘mode’]}): {pnl:+.2f} USDT”)
        St.session_state.balance += (p[‘margin’] + pnl)
    St.session_state.positions = []
    St.session_state.msg = “🔴 포지션 종료 하였습니다.”
    St.session_state.msg_type = “error”
    St.rerun()

If st.button(“🔄 가상머니 초기화”, use_container_width=True):
    St.session_state.balance = 10000.0
    St.session_state.positions = []
    St.session_state.logs = []
    St.session_state.auto_trading = False
    St.rerun()

St.subheader(“거래 로그”)
For log in reversed(st.session_state.logs[-10:]):
    St.text(log)

Time.sleep(0.3)
St.rerun()



