import streamlit as st
import os
import json
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime

# 페이지 설정
st.set_page_config(page_title="Crypto Bot Dashboard", layout="wide")

# --- 설정 및 데이터 관리 ---
DATA_FILE = "trading_data.json"

def initialize_session_state():
    defaults = {
        'daily_stats': {'total_profit': 0.0, 'win_rate': 0.0},
        'trade_logs': [],
        'last_trade_end_time': {},
        'active_virtual_positions': {},
        'any_position_active': False
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def save_data():
    data_to_save = {k: st.session_state[k] for k in ['daily_stats', 'trade_logs', 'active_virtual_positions']}
    data_to_save['last_trade_end_time'] = {k: v.isoformat() for k, v in st.session_state.last_trade_end_time.items()}
    with open(DATA_FILE, 'w') as f: json.dump(data_to_save, f)

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                st.session_state.update(data)
                for k, v in data.get('last_trade_end_time', {}).items():
                    st.session_state.last_trade_end_time[k] = datetime.fromisoformat(v)
        except: pass

# --- UI 레이아웃 ---
def render_sidebar():
    with st.sidebar:
        st.header("⚙️ Bot Settings")
        api_key = st.text_input("API Key", type="password")
        api_secret = st.text_input("API Secret", type="password")
        
        st.divider()
        if st.button("🔄 데이터 초기화", type="primary"):
            if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
            st.session_state.clear()
            st.rerun()

def render_dashboard():
    st.title("📈 Auto Trading Dashboard")
    
    # 상태 메트릭
    col1, col2, col3 = st.columns(3)
    col1.metric("총 수익", f"{st.session_state.daily_stats['total_profit']:.2f} USDT")
    col2.metric("승률", f"{st.session_state.daily_stats['win_rate']}%")
    col3.metric("상태", "운영 중" if st.session_state.any_position_active else "대기 중")
    
    st.divider()
    
    # 매매 로그 테이블
    st.subheader("📋 최근 매매 로그")
    if st.session_state.trade_logs:
        df = pd.DataFrame(st.session_state.trade_logs)
        st.dataframe(df.tail(10), use_container_width=True)
    else:
        st.info("아직 발생한 매매가 없습니다.")

# --- 메인 실행부 ---
def main():
    initialize_session_state()
    load_data()
    
    render_sidebar()
    render_dashboard()
    
    # 추후 로직 추가:
    # if st.session_state.any_position_active:
    #     run_trading_logic()

if __name__ == "__main__":
    main()
