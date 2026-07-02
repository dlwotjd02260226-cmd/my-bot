import streamlit as st
import requests
import time
from datetime import datetime
import streamlit.components.v1 as components

# ... (기존 설정 및 데이터 관리 로직 동일) ...
if 'init' not in st.session_state:
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.logs = []
    st.session_state.init = True

# [데이터 로직] 종료된 포지션 내역 관리
if 'closed_trades' not in st.session_state: st.session_state.closed_trades = []

def get_price():
    try:
        r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT", timeout=0.3)
        return float(r.json()['data'][0]['last'])
    except: return 0.0

price = get_price()
st.title("BTC 실시간 트레이딩")

# ... (기존 손익 계산 및 자산 계산 로직) ...
total_pos_pnl = sum(((price - p['entry']) if p['type']=='롱' else (p['entry']-price))/p['entry']*p['margin']*p['lev'] for p in st.session_state.positions)
total_margin_in_pos = sum(p['margin'] for p in st.session_state.positions)
current_total_asset = st.session_state.balance + total_margin_in_pos + total_pos_pnl
current_fluctuation = total_pos_pnl

st.metric("실시간 총 자산 (USDT)", f"{current_total_asset:,.2f}")
st.metric("현재 변동 금액 (USDT)", f"{current_fluctuation:+.2f} USDT")

# [핵심] 시각화: 거래 실적 대시보드
st.subheader("📊 실시간 거래 성적")
if st.session_state.closed_trades:
    # 수익/손실만 추출
    pnl_list = [t['pnl'] for t in st.session_state.closed_trades]
    
    # 지표 표시
    col_win, col_loss, col_total = st.columns(3)
    col_win.metric("총 수익 횟수", f"{len([x for x in pnl_list if x > 0])}")
    col_loss.metric("총 손실 횟수", f"{len([x for x in pnl_list if x <= 0])}")
    col_total.metric("누적 수익", f"{sum(pnl_list):,.2f} USDT")
    
    # 시각화 (간단한 막대 그래프 형태)
    st.bar_chart(pnl_list)
else:
    st.info("아직 종료된 거래가 없습니다.")

# ... (컨트롤 버튼 로직) ...
# 포지션 종료 로직에 데이터 추가
if st.button("❌ 포지션 종료"):
    for p in st.session_state.positions:
        pnl = ((price - p['entry'] if p['type']=='롱' else p['entry']-price)/p['entry'])*p['margin']*p['lev']
        # 성적 기록에 저장
        st.session_state.closed_trades.append({'pnl': pnl, 'time': datetime.now().strftime('%H:%M:%S')})
        st.session_state.balance += (p['margin'] + pnl)
    st.session_state.positions = []
    st.rerun()

# 초기화 로직에 성적 삭제 추가
if st.button("🔄 가상머니 초기화"):
    st.session_state.balance = 10000.0
    st.session_state.positions = []
    st.session_state.closed_trades = []
    st.rerun()

# ... (나머지 코드 동일) ...
