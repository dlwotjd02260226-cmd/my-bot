import pandas as pd
import time
from datetime import datetime
import ccxt # API 연결을 위한 라이브러리

--- API 설정 (config.py가 있다면 거기서 불러오고, 없으면 아래에 직접 입력하세요) ---
API_KEY = "600930d1-7207-4939-901b-df2d608f5035"
SECRET_KEY = "AE82870F253778F11B4C9D633DBDC803"
PASSPHRASE = "Eowkdus1203!@"

거래소 객체 초기화
exchange = ccxt.okx({
'apiKey': API_KEY,
'secret': SECRET_KEY,
'password': PASSPHRASE,
'options': {'defaultType': 'swap'}
})

--- 1. 시스템 통합 상태 관리 ---
system_state = {
"is_position_active": False,
"current_position": None,
"min_entry_score": 70, # 진입 기준 점수
"sl_percent": 2.0, # 손절 마지노선 (%)
"tp_percent": 5.0, # 익절 타겟 (%)
"last_pattern_type": None, # 패턴 재진입 차단용
"market_data": {
"long_short_ratio": 0.5 # OKX 실시간 데이터 공간
}
}

--- 2. 시각화 및 유틸리티 ---
def get_mobile_bar(val, max_val, segments=10):
filled = min(int((val / max_val) * segments), segments)
return f"|{'█'filled}{'-'(segments-filled)}|"

def display_dashboard(current_price, current_score):
print("\n" + "="*35)
print(f" [관제탑] {datetime.now().strftime('%H:%M:%S')}")
print("="*35)
print(f" 가격: {current_price:,.2f} USDT")
print(f" 롱숏: {system_state['market_data']['long_short_ratio']:.2f} {get_mobile_bar(system_state['market_data']['long_short_ratio'], 1.0)}")
print(f" 점수: {current_score} / {system_state['min_entry_score']}")
print(f" 손절: {system_state['sl_percent']:.1f}% {get_mobile_bar(system_state['sl_percent'], 10.0)}")
print("="*35)

--- 3. 통합 매매 엔진 ---
def get_unified_signal(df, current_score):
if system_state['is_position_active']:
return None, None, None, None, 0

# 데이터 지표 및 전략 계산
df = get_indicators(df)
last = df.iloc[-1]
long_signals, short_signals, detected_pattern = process_strategies(df)

# 롱숏 비율 기반 보정 (LSR < 0.5: 숏우세=롱유리)
lsr = system_state['market_data']['long_short_ratio']
lsr_bonus_long = 10 if lsr < 0.5 else 0
lsr_bonus_short = 10 if lsr > 0.5 else 0

# 패턴 중복 재진입 차단
if system_state['last_pattern_type'] is not None and detected_pattern == system_state['last_pattern_type']:
if is_pattern_forming(df): return None, None, None, None, 0
else: system_state['last_pattern_type'] = None

total_long = len(long_signals) + current_score + lsr_bonus_long
total_short = len(short_signals) + current_score + lsr_bonus_short
entry = last['close']

# 진입 판별 (롱)
if total_long >= system_state['min_entry_score']:
tech_sl = df['low'].iloc[-10:].min()
percent_sl = entry * (1 - (system_state['sl_percent'] / 100))
sl = max(tech_sl, percent_sl) # 더 좁은 손절값 선택
tp = entry + (entry - sl) * 2

system_state.update({"is_position_active": True, "current_position": "LONG", "last_pattern_type": detected_pattern})
return "LONG", entry, sl, tp, (1000 * 0.02) / (entry - sl)

# 진입 판별 (숏)
if total_short >= system_state['min_entry_score']:
tech_sl = df['high'].iloc[-10:].max()
percent_sl = entry * (1 + (system_state['sl_percent'] / 100))
sl = min(tech_sl, percent_sl) # 더 좁은 손절값 선택
tp = entry - (sl - entry) * 2

system_state.update({"is_position_active": True, "current_position": "SHORT", "last_pattern_type": detected_pattern})
return "SHORT", entry, sl, tp, (1000 * 0.02) / (sl - entry)

return None, None, None, None, 0

--- 4. 메인 시스템 루프 ---
def run_trading_system():
while True:
try:
# 1. API 데이터 수신부
# df = exchange.fetch_ohlcv('BTC/USDT:USDT', timeframe='15m', limit=100)
# df = pd.DataFrame(df, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

# score = calculate_score(df) # 님이 만드신 계산 함수
# price = df['close'].iloc[-1]

# 2. 시스템 구동
# display_dashboard(price, score)
# signal, entry, sl, tp, size = get_unified_signal(df, score)

# 3. 주문 실행 예시
# if signal: exchange.create_order('BTC/USDT:USDT', 'market', signal.lower(), size)

time.sleep(2)
except Exception as e:
print(f"오류 발생: {e}")
time.sleep(10)

if name == "main":
run_trading_system()
