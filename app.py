import warnings, os, json
warnings.filterwarnings("ignore")
os.environ["STREAMLIT_SERVER_SUPPRESS_NOWARNINGS"] = "true"
import streamlit as st, ccxt, time, pandas as pd, numpy as np
import streamlit.components.v1 as components
from datetime import datetime, timedelta

==========================================
[시스템 기능] 데이터 영구 저장을 위한 설정
==========================================
DATA_FILE = "trading_data.json"

def save_data():
data_to_save = {}
for k, v in st.session_state.items():
if isinstance(v, datetime):
data_to_save[f"dt{k}"] = v.isoformat()
elif isinstance(v, dict) and k == 'last_trade_end_time':
data_to_save[k] = {time_k: time_v.isoformat() for time_k, time_v in v.items()}
else:
try:
json.dumps(v)
data_to_save[k] = v
except:
pass

with open(DATA_FILE, 'w', encoding='utf-8') as f:
json.dump(data_to_save, f, ensure_ascii=False, indent=4)

def load_data():
if os.path.exists(DATA_FILE):
try:
with open(DATA_FILE, 'r', encoding='utf-8') as f:
data = json.load(f)
for k, v in data.items():
if k.startswith("dt"):
real_key = k.replace("dt", "")
st.session_state[real_key] = datetime.fromisoformat(v)
elif k == 'last_trade_end_time':
st.session_state[k] = {time_k: datetime.fromisoformat(time_v) for time_k, time_v in v.items()}
else:
st.session_state[k] = v
except: pass

def reset_data():
if os.path.exists(DATA_FILE):
os.remove(DATA_FILE)
for key in list(st.session_state.keys()):
del st.session_state[key]
st.rerun()


==========================================
[기법 1] AI 추세 및 지지·저항 돌파/반등 매매 (AI-SRB) 로직
==========================================
def analyze_trend_and_levels(symbol, timeframe='1h', limit=50):
try:
exchange = getattr(ccxt, st.session_state.get('active_exchange', 'binance'))()
ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
if df.empty: return {"trend": "Sideways", "support": 0, "resistance": 0}

df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
current_ema = df['ema_20'].iloc[-1]
prev_ema = df['ema_20'].iloc[-2]

if current_ema > prev_ema * 1.001: trend = "Uptrend"
elif current_ema < prev_ema * 0.999: trend = "Downtrend"
else: trend = "Sideways"

highs, lows = df['high'].values, df['low'].values
detected_resistances, detected_supports = [], []

for i in range(2, len(df)-2):
if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
detected_resistances.append(highs[i])
if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
detected_supports.append(lows[i])

resistance = np.median(detected_resistances) if detected_resistances else df['high'].max()
support = np.median(detected_supports) if detected_supports else df['low'].min()

return {"trend": trend, "support": float(support), "resistance": float(resistance), "current_price": float(df['close'].iloc[-1])}
except:
return {"trend": "Error", "support": 0, "resistance": 0}


==========================================
🛡️ [신규 추가] 장기 강력 대추세 판별 필터 엔진 (4시간 봉 MA 50 기준)
==========================================
def check_macro_trend_safeguard(symbol, target_direction):
try:
exchange = getattr(ccxt, st.session_state.get('active_exchange', 'binance'))()
ohlcv = exchange.fetch_ohlcv(symbol, '4h', limit=70)
df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
if df.empty or len(df) < 50: return True, "🟢 데이터 부족으로 검사를 유연하게 통과합니다."

df['ma_50'] = df['close'].rolling(window=50).mean()

current_price = df['close'].iloc[-1]
macro_ma = df['ma_50'].iloc[-1]

upper_bound = macro_ma * 1.005
lower_bound = macro_ma * 0.995

if current_price < lower_bound:
if target_direction == "LONG":
return False, "🔴 4시간 봉 기준 강력 하락장 상태입니다. 롱(LONG) 배팅이 강제로 차단됩니다."
elif current_price > upper_bound:
if target_direction == "SHORT":
return False, "🔵 4시간 봉 기준 강력 상승장 상태입니다. 숏(SHORT) 배팅이 강제로 차단됩니다."

return True, "🟢 대추세 흐름이 안전 범위에 있거나 진입 방향과 일치합니다."
except:
return True, "⚠️ 대추세 필터 확인 중 오류가 발생하여 검사를 패스합니다."


==========================================
📊 [신규 UI 기능] 초장기 거시 추세 분석 (1일봉, 주봉, 월봉 통합 분석판)
==========================================
def show_super_macro_trend_ui(symbol):
st.markdown("### 🗺️ 초장기 거시 대추세 브리핑 (최소 한 달 이상 흐름)")
try:
exchange = getattr(ccxt, st.session_state.get('active_exchange', 'binance'))()

# 1일봉, 주봉, 월봉 데이터 로드 (각각 40개씩 확보)
ohlcv_d = exchange.fetch_ohlcv(symbol, '1d', limit=40)
ohlcv_w = exchange.fetch_ohlcv(symbol, '1w', limit=40)
ohlcv_m = exchange.fetch_ohlcv(symbol, '1M', limit=40)

df_d = pd.DataFrame(ohlcv_d, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
df_w = pd.DataFrame(ohlcv_w, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
df_m = pd.DataFrame(ohlcv_m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

# 각 타임프레임별 MA 20 계산
df_d['ma20'] = df_d['close'].rolling(20).mean()
df_w['ma20'] = df_w['close'].rolling(20).mean()
df_m['ma20'] = df_m['close'].rolling(20).mean()

# 현재가 및 각 주기별 이동평균 가격 추출
curr_price = df_d['close'].iloc[-1]
ma_d = df_d['ma20'].iloc[-1]
ma_w = df_w['ma20'].iloc[-1]
ma_m = df_m['ma20'].iloc[-1]

# 상태 판정 (현재가 vs MA 20)
status_d = "🟢 상승세" if curr_price > ma_d else "🔴 하락세"
status_w = "🟢 상승세" if curr_price > ma_w else "🔴 하락세"
status_m = "🟢 상승세" if curr_price > ma_m else "🔴 하락세"

# 종합 점수 스코어링
score = 0
if curr_price > ma_d: score += 1
if curr_price > ma_w: score += 1
if curr_price > ma_m: score += 1

if score == 3:
macro_verdict = "🔥 강력 상승장 (무조건 숏 진입 극도로 조심)"
alert_type = st.success
elif score == 2:
macro_verdict = "📈 상승 우세 (매수세가 조금 더 강한 구간)"
alert_type = st.info
elif score == 1:
macro_verdict = "📉 하락 우세 (매도세가 조금 더 강한 구간)"
alert_type = st.warning
elif score == 0:
macro_verdict = "❄️ 강력 하락장 (무조건 롱 진입 극도로 조심)"
alert_type = st.error
else:
macro_verdict = "⏳ 혼조세 상황"
alert_type = st.info

# UI 출력
alert_type(f"🧐 초장기 종합 진단 결과 : {macro_verdict}")

col1, col2, col3 = st.columns(3)
with col1:
st.metric(label="📅 1일봉 기준 (약 한달 흐름)", value=status_d, delta=f"MA20:  {ma_w:,.1f}")
with col3:
st.metric(label="🌍 월봉 기준 (초장기 패러다임)", value=status_m, delta=f"MA20: $`{ma_m:,.1f}")
st.markdown("---")
except Exception as e:
st.warning(f"⚠️ 초장기 거시 추세 데이터를 불러오는 중 일시적 지연이 발생했습니다: {e}")
st.markdown("---")


==========================================
[통합 엔진] 12가지 형태학적 차트 패턴 및 캔들 기법 독립 검출기
==========================================
def analyze_all_independent_patterns(symbol, timeframe='1h', limit=100, cutoff_time=None):
active_conditions = {}

try:
exchange = getattr(ccxt, st.session_state.get('active_exchange', 'binance'))()
ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
if df.empty or len(df) < 30: return active_conditions

df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')

if cutoff_time is not None:
cutoff_dt = pd.to_datetime(cutoff_time).tz_localize(None)
df['datetime_naive'] = df['datetime'].dt.tz_localize(None)
df = df[df['datetime_naive'] >= cutoff_dt].reset_index(drop=True)
if len(df) < 10:
return active_conditions

# -------------------------------------------------------------
# A 구역. 3가지 독립 캔들 기법 검출 로직
# -------------------------------------------------------------
last_candle = df.iloc[-1]
open_p, close_p, high_p, low_p = last_candle['open'], last_candle['close'], last_candle['high'], last_candle['low']
current_price = close_p

body = abs(close_p - open_p)
total_range = high_p - low_p if (high_p - low_p) > 0 else 0.0001
upper_shadow = high_p - max(open_p, close_p)
lower_shadow = min(open_p, close_p) - low_p

# 1. 망치형 캔들 기법
if (lower_shadow > body * 2) and (upper_shadow / total_range < 0.1):
active_conditions["망치형 캔들 기법"] = "LONG"

# 2. 역망치형 캔들 기법
if (upper_shadow > body * 2) and (lower_shadow / total_range < 0.1):
active_conditions["역망치형 캔들 기법"] = "LONG"

# 3. 도지 캔들 기법
if body / total_range < 0.1:
prev_price = df['close'].iloc[-2]
active_conditions["도지 캔들 기법"] = "LONG" if current_price > prev_price else "SHORT"

# -------------------------------------------------------------
# B 구역. 9가지 독립 차트 형태학적 패턴 검출 로직
# -------------------------------------------------------------
df['is_peak'] = (df['high'] == df['high'].rolling(5, center=True).max())
df['is_trough'] = (df['low'] == df['low'].rolling(5, center=True).min())

peaks_idx = df[df['is_peak']].index[-4:]
troughs_idx = df[df['is_trough']].index[-4:]

if len(peaks_idx) < 3 or len(troughs_idx) < 3: return active_conditions

p_vals = df['high'].loc[peaks_idx].values
t_vals = df['low'].loc[troughs_idx].values

# 4. 헤드 앤 숄더 패턴 기법
if p_vals[-2] > p_vals[-3] and p_vals[-2] > p_vals[-1] and abs(p_vals[-3] - p_vals[-1]) / p_vals[-3] < 0.02:
if current_price < min(p_vals[-3], p_vals[-1]):
active_conditions["헤드 앤 숄더 패턴 기법"] = "SHORT"

# 5. 역 헤드 앤 숄더 패턴 기법
if t_vals[-2] < t_vals[-3] and t_vals[-2] < t_vals[-1] and abs(t_vals[-3] - t_vals[-1]) / t_vals[-3] < 0.02:
active_conditions["역 헤드 앤 숄더 패턴 기법"] = "LONG"

# 6. 상승 깃발형 패턴 기법
if p_vals[-1] < p_vals[-2] and t_vals[-1] < t_vals[-2]:
if (df['close'].iloc[peaks_idx[-2]] - df['close'].iloc[peaks_idx[-2]-10]) > current_price * 0.03:
active_conditions["상승 깃발형 패턴 기법"] = "LONG"

# 7. 하락 깃발형 패턴 기법
if p_vals[-1] > p_vals[-2] and t_vals[-1] > t_vals[-2]:
if (df['close'].iloc[peaks_idx[-2]-10] - df['close'].iloc[peaks_idx[-2]]) > current_price * 0.03:
active_conditions["하락 깃발형 패턴 기법"] = "SHORT"

# 8. 하락 쐐기형 패턴 기법
if p_vals[-1] < p_vals[-2] and t_vals[-1] < t_vals[-2]:
if (p_vals[-2] - p_vals[-1]) > (t_vals[-2] - t_vals[-1]):
active_conditions["하락 쐐기형 패턴 기법"] = "LONG"

# 9. 상승 쐐기형 패턴 기법
if p_vals[-1] > p_vals[-2] and t_vals[-1] > t_vals[-2]:
if (t_vals[-1] - t_vals[-2]) > (p_vals[-1] - p_vals[-2]):
active_conditions["상승 쐐기형 패턴 기법"] = "SHORT"

# 10. 상승 삼각수렴 패턴 기법
if abs(p_vals[-1] - p_vals[-2]) / p_vals[-2] < 0.005 and t_vals[-1] > t_vals[-2]:
active_conditions["상승 삼각수렴 패턴 기법"] = "LONG"

# 11. 하락 삼각수렴 패턴 기법
if abs(t_vals[-1] - t_vals[-2]) / t_vals[-2] < 0.005 and p_vals[-1] < p_vals[-2]:
active_conditions["하락 삼각수렴 패턴 기법"] = "SHORT"

# 12. 컵 앤 핸들 패턴 기법
if abs(p_vals[-3] - p_vals[-1]) / p_vals[-3] < 0.01 and t_vals[-2] < min(t_vals[-3], t_vals[-1]):
if current_price > t_vals[-1]:
active_conditions["컵 앤 핸들 패턴 기법"] = "LONG"

# 13. 박스권 채널 패턴 기법
if abs(p_vals[-1] - p_vals[-2]) / p_vals[-2] < 0.004 and abs(t_vals[-1] - t_vals[-2]) / t_vals[-2] < 0.004:
mid_box = (p_vals[-1] + t_vals[-1]) / 2
active_conditions["박스권 채널 패턴 기법"] = "LONG" if current_price < mid_box else "SHORT"

return active_conditions
except:
return active_conditions


==========================================
[모니터링 UI] 지지선 / 저항선 및 현황판 브리핑 전용 기능
==========================================
def show_me_levels(symbol, timeframe='1h'):
analysis = analyze_trend_and_levels(symbol, timeframe=timeframe)
if analysis.get("trend") != "Error" and analysis.get("support") != 0:
st.markdown("---")
st.markdown("### 👁️ 실시간 지지 · 저항선 눈으로 보기")
col1, col2, col3 = st.columns(3)
with col1: st.metric(label="🔴 저항선 (천장 가격)", value=f"${analysis['resistance']:,}") with col2: st.metric(label="💵 현재가", value=f"${analysis['current_price']:,}")
with col3: st.metric(label="🟢 지지선 (바닥 가격)", value=f"`${analysis['support']:,}")
st.markdown("---")

def show_active_signals_report(current_matched_signals, required_count, cutoff_time):
st.markdown("#### 🎯 실시간 기법 매칭 현황 브리핑")
current_count = len(current_matched_signals)

if cutoff_time:
st.caption(f"안전 가드 작동 중: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} 포지션 마감 이후의 데이터만 새로 계산하는 중입니다.")

if current_count >= required_count:
st.success(f"🔥 진입 조건 충족 완료! ({current_count} / {required_count}) - 대추세 필터를 점검합니다.")
else:
st.info(f"⏳ 조건 미달로 관망 중 ({current_count} / {required_count}) - 포지션 진입을 위해 {required_count - current_count}개의 기법 신호가 더 필요합니다.")

if current_count > 0:
st.markdown("💡 현재 신호 조건이 일치하는 기법 목록:")
for idx, method_name in enumerate(current_matched_signals, 1):
st.markdown(f"{idx}. ✅ {method_name} → 매칭 조건 충족 중")
else:
st.markdown("⚠️ 현재 매수/매도 시그널 조건에 도달한 기법이 없습니다. 시장 관망 및 데이터를 탐색 중입니다.")
st.markdown("---")


==========================================
[Main] Streamlit 대시보드 및 자동매매 핵심 루프
==========================================
def main():
st.set_page_config(page_title="AI 멀티 패턴 자동매매 봇", layout="wide")
st.title("🤖 AI 12가지 독립 기법 멀티 거래 시스템")

load_data()

# 세션 상태 초기화 및 기본값 설정
if 'active_exchange' not in st.session_state: st.session_state['active_exchange'] = 'binance'
if 'target_symbol' not in st.session_state: st.session_state['target_symbol'] = 'BTC/USDT'
if 'required_score' not in st.session_state: st.session_state['required_score'] = 3
if 'bot_direction' not in st.session_state: st.session_state['bot_direction'] = 'LONG'
if 'last_position_closed_at' not in st.session_state: st.session_state['last_position_closed_at'] = None

# 사이드바 설정 영역
st.sidebar.header("⚙️ 봇 기본 제어 및 환경설정")
st.session_state['target_symbol'] = st.sidebar.text_input("🎯 거래 대상 심볼 (예: BTC/USDT)", st.session_state['target_symbol'])
st.session_state['bot_direction'] = st.sidebar.selectbox("📈 진입 노릴 방향성 선택", ["LONG", "SHORT"], index=0 if st.session_state['bot_direction'] == 'LONG' else 1)
st.session_state['required_score'] = st.sidebar.slider("🎯 진입에 필요한 최소 기법 만족 개수 (점수)", 1, 12, st.session_state['required_score'])

st.sidebar.markdown("---")
if st.sidebar.button("🚨 임의 포지션 종료 처리 (현재시간 기준으로 락 부과)"):
st.session_state['last_position_closed_at'] = datetime.now()
st.sidebar.success("포지션 종료 시간 기록 완료! 신규 캔들 스캔을 시작합니다.")
save_data()

if st.sidebar.button("데이터 동기화 초기화 (리셋)"):
reset_data()

# ✨ [신규 레이어 추가] 초장기 거시 대추세 브리핑 UI 대시보드 출력
show_super_macro_trend_ui(st.session_state['target_symbol'])

# 실시간 지지/저항선 UI 시각화
show_me_levels(st.session_state['target_symbol'])

# -------------------------------------------------------------
# 🌟 [1단계] 독립 기법 탐지 및 점수 연동 처리 구간
# -------------------------------------------------------------
matched_methods = []

cutoff = st.session_state['last_position_closed_at']
detected_results = analyze_all_independent_patterns(st.session_state['target_symbol'], timeframe='1h', cutoff_time=cutoff)

for condition_name, signal_side in detected_results.items():
if signal_side == st.session_state['bot_direction']:
matched_methods.append(condition_name)

show_active_signals_report(matched_methods, st.session_state['required_score'], cutoff)

# -------------------------------------------------------------
# 🌟 [2단계] 거시 대추세 필터 레이어 검사 구간
# -------------------------------------------------------------
is_macro_trend_ok, macro_message = check_macro_trend_safeguard(st.session_state['target_symbol'], st.session_state['bot_direction'])

# UI에 현재 거시 대추세 안전 상황 실시간 표시
if "🔴" in macro_message or "🔵" in macro_message:
st.error(macro_message)
else:
st.info(macro_message)

# 최종 점수 계산 및 포지션 진입 판단문
final_score = len(matched_methods)
st.subheader(f"📊 최종 판정 스코어: {final_score}점 / 목표 {st.session_state['required_score']}점")

# 판단 조건: 기법 점수 충족 AND 거시 대추세 필터 통과(True) 여부 동시 체크
if final_score >= st.session_state['required_score']:
if is_macro_trend_ok:
st.success(f"🚀 [진입 최종 승인] 스코어 및 장기 대추세 필터를 모두 완벽히 통과했습니다! 주문 프로세스를 가동합니다.")
else:
st.error(f"🛑 [진입 강제 거부] 기법 점수는 충족했으나, 장기 추세와 정반대되는 역추세 위험 구간이므로 배팅을 원천 차단합니다.")
else:
st.warning("💤 [진입 대기] 조건을 만족하는 독립 기법의 수가 부족합니다. 지속해서 차트를 스캔합니다.")

save_data()

if name == "main":
main()
