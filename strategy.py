import pandas as pd
import requests

# ========================================================
# [이삿짐 도착] app.py에서 가져온 분석 로직들
# ========================================================

# 1. 원본 코드: 지지 저항선 분석 엔진
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
    logic_msg = f"지지선 {len(near_l)}개 감지(점수:{sup_score:.1f}), 저항선 {len(near_h)}개 감지(점수:{res_score:.1f})"
    return score, list(near_l['low']), list(near_h['high']), logic_msg

# 2. 원본 코드: 거래량 분석
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

# 3. 원본 코드: EMA 분석 엔진
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

    def get_ema_analysis(self, get_klines_func):
        results = []
        total_score = 0
        for tf in ['1h', '4h', '1d', '1W', '1M']:
            df = get_klines_func(tf)
            if df is not None:
                msg, score = self.calculate_ema_status(df)
                weighted_score = score * self.weights.get(tf, 1)
                total_score += weighted_score
                results.append((tf, msg, weighted_score))
        return total_score, results

# [strategy.py 파일 맨 아래에 추가]

def get_dynamic_ema200_score(price, df):
    """
    기존 로직과 별개로 작동하는 EMA 200 가감점 판단 엔진
    """
    if df is None or len(df) < 200:
        return 0, 0, "데이터 부족"
        
    ema200 = df['close'].ewm(span=200, adjust=False).mean().iloc[-1]
    is_above = price > ema200
    
    # 롱 포지션 점수: 위에 있으면 가점(+2), 아래면 감점(-2)
    # 숏 포지션 점수: 아래에 있으면 가점(+2), 위에 있으면 감점(-2)
    long_score = 2 if is_above else -2
    short_score = 2 if not is_above else -2
    
    status = "상승 추세(롱 우세)" if is_above else "하락 추세(숏 우세)"
    return long_score, short_score, status
