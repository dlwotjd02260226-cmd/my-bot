import streamlit as st, ccxt, time, pandas as pd, numpy as np, os, json
import streamlit.components.v1 as components
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings("ignore")
os.environ["STREAMLIT_SERVER_SUPPRESS_NOWARNINGS"] = "true"

# [기능 추가] 거시 추세 안전 장치
def check_macro_trend_safeguard(symbol, target_direction):
    try:
        exchange = ccxt.okx()
        ohlcv = exchange.fetch_ohlcv(symbol, '4h', limit=70)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['ma_50'] = df['close'].rolling(window=50).mean()
        curr_p, ma = df['close'].iloc[-1], df['ma_50'].iloc[-1]
        if curr_p < ma * 0.995 and target_direction == "LONG":
            return False, "하락장 진입으로 롱 배팅 차단"
        elif curr_p > ma * 1.005 and target_direction == "SHORT":
            return False, "상승장 진입으로 숏 배팅 차단"
        return True, "거시 추세 안전"
    except Exception:
        return True, "필터 검사 오류"

def show_super_macro_trend_ui(symbol):
    st.markdown("### 🌐 초장기 거시 대추세 브리핑")
    try:
        exchange = ccxt.okx()
        for tf in ['1d', '1w', '1M']:
            ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=40)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['ma20'] = df['close'].rolling(20).mean()
            st.write(f"{tf} 상태: {'상승' if df['close'].iloc[-1] > df['ma20'].iloc[-1] else '하락'}")
    except Exception: pass

# [데이터 관리]
DATA_FILE = "trading_data.json"
def save_data():
    data_to_save = {
        'daily_stats': st.session_state.daily_stats,
        'trade_logs': st.session_state.trade_logs,
        'last_trade_end_time': {k: v.isoformat() for k, v in st.session_state.last_trade_end_time.items()},
        'active_virtual_positions': st.session_state.active_virtual_positions
    }
    with open(DATA_FILE, 'w') as f: json.dump(data_to_save, f)

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                st.session_state.daily_stats = data.get('daily_stats', st.session_state.daily_stats)
                st.session_state.trade_logs = data.get('trade_logs', st.session_state.trade_logs)
                saved_times = data.get('last_trade_end_time', {})
                for k, v in saved_times.items():
                    st.session_state.last_trade_end_time[k] = datetime.fromisoformat(v)
                st.session_state.active_virtual_positions = data.get('active_virtual_positions', st.session_state.active_virtual_positions)
        except Exception: pass

def reset_data():
    if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
    for key in ['daily_stats', 'trade_logs', 'last_trade_end_time', 'active_virtual_positions', 'any_position_active']:
        if key in st.session_state: del st.session_state[key]
    st.rerun()

# [설정 및 초기화]
API_CONFIG = {'apiKey': '600930d1-7207-4939-901b-df2d608f5035', 'secret': 'AE82870F253778F11B4C9D633DBDC803', 'password': 'Eowkdus1203!@', 'enableRateLimit': True, 'options': {'defaultType': 'swap'}}
SYMBOL, TAKER_FEE = 'BTC/USDT:USDT', 0.0005
ALL_TIMEFRAMES = ['5m', '15m', '30m', '1h', '4h']
CD_CONF = {'5m': timedelta(minutes=20), '15m': timedelta(hours=1), '30m': timedelta(hours=2), '1h': timedelta(hours=4), '4h': timedelta(hours=16)}

if 'daily_stats' not in st.session_state: st.session_state.daily_stats = {'total_bets':0, 'wins':0, 'losses':0, 'net_profit':0.0}
if 'trade_logs' not in st.session_state: st.session_state.trade_logs = []
if 'last_trade_end_time' not in st.session_state: st.session_state.last_trade_end_time = {tf: datetime(2000,1,1) for tf in ALL_TIMEFRAMES}
if 'active_virtual_positions' not in st.session_state: st.session_state.active_virtual_positions = {tf: None for tf in ALL_TIMEFRAMES}
load_data()

st.set_page_config(page_title="OKX 지능형 제어 시스템", layout="wide")
st.title("🤖 OKX 멀티 타임프레임 자율매매 시스템")

# [사이드바]
st.sidebar.header("🎛️ 시스템 컨트롤")
is_running = st.sidebar.toggle("⚡ 자율매매 시작", value=False)
if st.sidebar.button("⚠️ 모든 데이터 초기화"): reset_data()
TARGET_TF = st.sidebar.selectbox("타겟 시간대 선택", ALL_TIMEFRAMES, index=3)
구동모드 = st.sidebar.radio("🔄 모드", ('가상모드', '실제모드'))
is_test = (구동모드 == '가상모드')
MARGIN_MODE = st.sidebar.radio("🛡️ 마진", ('isolated', 'cross'))
LEVERAGE = st.sidebar.number_input("🚀 레버리지", value=3)
SL_INPUT = st.sidebar.number_input("📉 손절 (%)", value=2.0)
TP_INPUT = st.sidebar.number_input("📈 익절 (%)", value=5.0)
TEST_BAL = st.sidebar.number_input("🧪 가상 자산", value=5000.0)
MIN_MATCH = st.sidebar.slider("⚙️ 최소 일치 개수", 1, 12, 3)
INVS_RATIO = st.sidebar.slider("💰 투자 비율 (%)", 1, 100, 10) / 100

# [실제 거래소 연동]
exchange = ccxt.okx({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
if not is_test:
    try:
        exchange = ccxt.okx(API_CONFIG)
        exchange.set_margin_mode(MARGIN_MODE.upper(), SYMBOL)
        exchange.set_leverage(int(LEVERAGE), SYMBOL)
    except Exception as e: st.error(f"거래소 연동 실패: {e}")

# [주요 함수들]
def render_tradingview_chart(tf_str):
    tv_tf = "5" if tf_str == "5m" else "15" if tf_str == "15m" else "30" if tf_str == "30m" else "60" if tf_str == "1h" else "240"
    tv_html = f"""<div class="tradingview-widget-container" style="height:550px;width:100%;"><div id="tradingview_chart"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"autosize": true, "symbol": "OKX:BTCUSDT.P", "interval": "{tv_tf}", "timezone": "Asia/Seoul", "theme": "dark", "style": "1", "container_id": "tradingview_chart", "studies": ["MASimple@tv-basicstudies"]}});</script></div>"""
    components.html(tv_html, height=560)

def execute_order(tf, side, amount, curr_price, matched_reasons):
    if st.session_state.get('any_position_active', False): return
    st.session_state['any_position_active'] = True
    entry_time = datetime.now()
    st.session_state.trade_logs.insert(0, f"[{entry_time.strftime('%H:%M:%S')}] {tf} {side.upper()} 진입")
    if is_test:
        st.session_state.active_virtual_positions[tf] = {'side': side, 'entry_price': curr_price}
    else:
        try: exchange.create_market_order(SYMBOL, side, amount)
        except Exception as e: st.error(f"주문 실패: {e}")
    save_data()

# [실행 로직]
show_super_macro_trend_ui(SYMBOL)
ok, msg = check_macro_trend_safeguard(SYMBOL, "LONG")
st.info(f"거시 필터: {msg}")

st.subheader(f"🖥️ 메인 모니터링: {TARGET_TF}")
render_tradingview_chart(TARGET_TF)

if is_running:
    time.sleep(5)
    st.rerun()
