import pandas as pd
import numpy as np
import json
import os

# =========================================================================
# [건드리지 않은 원본 코드] 주신 코드 토씨 하나 안 건드리고 그대로 유지했습니다.
# =========================================================================
def calculate_sr_score_by_touch(price, df, tf='1h', custom_tf_weights=None,
                                 longevity_bonus_max=0.5, volume_lookback=20):
    """
    과거 캔들의 시간 가중치(Time Decay), 동적 ATR 변동성, 거래량 가중치가 적용된
    순수 터치 빈도 기반 Zero-Lag 지지/저항 분석 함수
    (실전 자동매매 보완판 + 장기 생존 보너스 + 거래량 가중치 + 테스트 피로도 진단)

    longevity_bonus_max: 첫 터치~마지막 터치 폭(생존 기간)이 전체 히스토리를 꽉 채울 때
                         레벨 점수에 추가로 곱해줄 최대 보너스 비율 (기본 0.5 = 최대 +50%)
    volume_lookback: 거래량 상대 비율 계산 시 사용할 이동평균 기간 (기본 20)
    """
    if df is None or df.empty or len(df) < 50:
        return 0.0, 0.0, [], [], "데이터 부족으로 계산 불가"

    if price is None or price <= 0:
        return 0.0, 0.0, [], [], "현재가 오류"

    analysis_df = df.iloc[:-1].copy()
    n_candles = len(analysis_df)

    # =========================================================================
    # [⚙️ 0. 거래량 상대 비율 계산 (Relative Volume)]
    # =========================================================================
    # 'volume' 컬럼이 없으면 모든 캔들을 동일 가중치(1.0)로 처리 (기존 로직과 동일하게 동작)
    has_volume = 'volume' in analysis_df.columns
    if has_volume:
        vol_ma = analysis_df['volume'].rolling(volume_lookback, min_periods=5).mean()
        # 초반 구간(이동평균 미형성)은 1.0(중립)으로 대체
        vol_ratio_raw = (analysis_df['volume'] / vol_ma).fillna(1.0)
        # 극단치(거래량 폭증/급감)로 점수가 튀지 않도록 0.5배~2.0배로 clip
        vol_ratio = vol_ratio_raw.clip(0.5, 2.0).values
    else:
        vol_ratio = np.ones(n_candles)

    # =========================================================================
    # [⚙️ 1. 타임프레임 및 터치 기준 설정]
    # =========================================================================
    DEFAULT_TF_WEIGHTS = {'1h': 1.0, '4h': 1.5, '1d': 2.0}
    tf_weights = custom_tf_weights if custom_tf_weights else DEFAULT_TF_WEIGHTS
    tf_clean = str(tf).lower()
    tf_multiplier = tf_weights.get(tf_clean, 1.0)

    TF_TOUCH_RULES = {
        '1h': {'strong': 7.0, 'medium': 4.0, 'weak': 2.0},
        '4h': {'strong': 4.5, 'medium': 3.0, 'weak': 1.8},
        '1d': {'strong': 3.0, 'medium': 2.0, 'weak': 1.0},
    }
    rule = TF_TOUCH_RULES.get(tf_clean, TF_TOUCH_RULES['1h'])

    TOUCH_CONFIG = {
        'strong': {'min_score': rule['strong'], 'base_score': 100.0, 'label': '강력'},
        'medium': {'min_score': rule['medium'], 'base_score': 50.0,  'label': '중간'},
        'weak':   {'min_score': rule['weak'],   'base_score': 20.0,  'label': '약함'}
    }

    # =========================================================================
    # [⚙️ 2. 동적 변동성(ATR) 기반 오차범위 & 소수점 정밀도 자동 계산]
    # =========================================================================
    high_low = analysis_df['high'] - analysis_df['low']
    high_close = (analysis_df['high'] - analysis_df['close'].shift()).abs()
    low_close = (analysis_df['low'] - analysis_df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1] if n_candles >= 14 else (analysis_df['high'] - analysis_df['low']).mean()

    dynamic_band_pct = (atr / price) * 0.25
    band_pct = max(0.002, min(0.010, dynamic_band_pct))
    distance_pct = 0.040

    if price >= 1000:
        decimals = 2
    elif price >= 1:
        decimals = 4
    else:
        decimals = 6

    # =========================================================================
    # [⚙️ 3. Absolute Anchor Grid 생성]
    # =========================================================================
    step = price * band_pct
    anchor_price = np.floor(price / step) * step
    num_steps = int(distance_pct / band_pct)
    grid_prices = np.array([anchor_price + (i * step) for i in range(-num_steps, num_steps + 1)])

    # =========================================================================
    # [⚙️ 4. 시간 가중치 & 몸통/꼬리 가중치 적용]
    # =========================================================================
    time_weights = np.linspace(0.3, 1.0, n_candles)  # index 0=가장 오래된 봉, -1=가장 최근 봉

    body_min = np.minimum(analysis_df['open'], analysis_df['close'])
    body_max = np.maximum(analysis_df['open'], analysis_df['close'])

    sup_details = []
    res_details = []

    for p_level in grid_prices:
        band_low = p_level - (step / 2)
        band_high = p_level + (step / 2)

        wick_touched = (analysis_df['high'] >= band_low) & (analysis_df['low'] <= band_high)
        body_touched = (body_max >= band_low) & (body_min <= band_high)

        base_touch_weights = np.where(body_touched, 1.2, np.where(wick_touched, 0.5, 0.0))

        # [🆕 거래량 가중치 반영] 터치 강도 = 기본 가중치 × 상대거래량
        # (거래량 없이 스친 터치는 깎이고, 거래량 실린 반등/저항은 더 강하게 인정)
        touch_weights = base_touch_weights * vol_ratio

        effective_touch_score = float((time_weights * touch_weights).sum())
        raw_touch_count = int(wick_touched.sum())

        if effective_touch_score >= TOUCH_CONFIG['weak']['min_score']:
            if effective_touch_score >= TOUCH_CONFIG['strong']['min_score']:
                cfg = TOUCH_CONFIG['strong']
            elif effective_touch_score >= TOUCH_CONFIG['medium']['min_score']:
                cfg = TOUCH_CONFIG['medium']
            else:
                cfg = TOUCH_CONFIG['weak']

            # --- 생존 기간(Longevity) ---
            touched_idx = np.where(base_touch_weights > 0)[0]
            if touched_idx.size > 0:
                first_touch_idx = int(touched_idx[0])
                last_touch_idx = int(touched_idx[-1])
                survival_span = last_touch_idx - first_touch_idx
                span_ratio = survival_span / max(1, n_candles - 1)
            else:
                first_touch_idx = last_touch_idx = survival_span = 0
                span_ratio = 0.0

            longevity_multiplier = 1.0 + (span_ratio * longevity_bonus_max)
            total_level_score = cfg['base_score'] * longevity_multiplier

            # ---------------------------------------------------------------
            # [🆕 테스트 피로도(Test Fatigue) 진단]
            # 이 레벨을 터치할 때마다 거래량이 줄어드는 추세라면 → 방어 에너지 고갈 →
            # "약화(뚫림 위험↑)". 거래량이 유지/증가하는데도 계속 막혔다면 → "유지(흡수)".
            # 터치 3회 미만은 추세 판단이 무의미하므로 "정보부족"으로 표기.
            # ---------------------------------------------------------------
            avg_volume_ratio = float(vol_ratio[touched_idx].mean()) if touched_idx.size > 0 else 1.0

            if touched_idx.size >= 3 and has_volume:
                touch_vols = vol_ratio[touched_idx]
                slope = float(np.polyfit(touched_idx, touch_vols, 1)[0])
                if slope < -0.01:
                    fatigue_label = "약화(뚫림 위험↑)"
                elif slope > 0.01:
                    fatigue_label = "유지(흡수 우세)"
                else:
                    fatigue_label = "중립"
            else:
                fatigue_label = "정보부족(터치<3 또는 거래량 없음)"

            level_info = {
                'price': round(p_level, decimals),
                'touch_count': raw_touch_count,
                'effective_score': round(effective_touch_score, 2),
                'strength': cfg['label'],
                'score': round(total_level_score, 1),
                'first_touch_idx': first_touch_idx,
                'last_touch_idx': last_touch_idx,
                'survival_span': survival_span,
                'longevity_bonus': round(longevity_multiplier, 3),
                'avg_volume_ratio': round(avg_volume_ratio, 2),   # 1.0=평균, 1.5=평균보다 50%↑
                'test_fatigue': fatigue_label                      # 반복 테스트 약화 여부 진단
            }

            if p_level > price:
                res_details.append(level_info)
            else:
                sup_details.append(level_info)

    # =========================================================================
    # [⚙️ 6. 인접 매물대 병합 및 점수 합산]
    # =========================================================================
    def merge_adjacent_levels(details_list):
        if not details_list:
            return []

        sorted_by_price = sorted(details_list, key=lambda x: x['price'])
        merged_levels = []

        for item in sorted_by_price:
            if not merged_levels:
                merged_levels.append(item.copy())
                continue

            prev = merged_levels[-1]
            if abs(item['price'] - prev['price']) / price < band_pct:
                if item['effective_score'] > prev['effective_score']:
                    prev['price'] = item['price']
                    prev['strength'] = item['strength']

                prev['score'] = round(prev['score'] + item['score'] * 0.7, 1)
                prev['touch_count'] += item['touch_count']
                prev['effective_score'] = round(prev['effective_score'] + item['effective_score'] * 0.7, 2)

                prev['first_touch_idx'] = min(prev['first_touch_idx'], item['first_touch_idx'])
                prev['last_touch_idx'] = max(prev['last_touch_idx'], item['last_touch_idx'])
                prev['survival_span'] = prev['last_touch_idx'] - prev['first_touch_idx']
                prev['longevity_bonus'] = round(max(prev['longevity_bonus'], item['longevity_bonus']), 3)

                # [🆕] 병합 시 거래량비율은 터치수 가중 평균으로, 피로도는 더 심각한 쪽을 채택
                total_touches = max(1, prev['touch_count'])
                prev['avg_volume_ratio'] = round(
                    (prev['avg_volume_ratio'] + item['avg_volume_ratio']) / 2, 2
                )
                if item['test_fatigue'] == "약화(뚫림 위험↑)":
                    prev['test_fatigue'] = item['test_fatigue']
            else:
                merged_levels.append(item.copy())

        return sorted(merged_levels, key=lambda x: x['price'])

    clean_sup = merge_adjacent_levels(sup_details)
    clean_res = merge_adjacent_levels(res_details)

    raw_sup_score = sum(item['score'] for item in clean_sup)
    raw_res_score = sum(item['score'] for item in clean_res)

    final_sup_score = raw_sup_score * tf_multiplier
    final_res_score = raw_res_score * tf_multiplier
    final_net_score = final_sup_score - final_res_score

    strong_sup_cnt = sum(1 for item in clean_sup if item['strength'] == "강력")
    strong_res_cnt = sum(1 for item in clean_res if item['strength'] == "강력")

    vol_note = "거래량 가중 적용" if has_volume else "거래량 없음(중립 처리)"
    logic_msg = (
        f"[{tf_clean.upper()} 터치분석] (ATR오차:{band_pct*100:.2f}%) 가중치:{tf_multiplier}x | {vol_note} | "
        f"지지 {len(clean_sup)}개(강력:{strong_sup_cnt}) [+{final_sup_score:.1f}], "
        f"저항 {len(clean_res)}개(강력:{strong_res_cnt}) [-{final_res_score:.1f}] | "
        f"순점수:{final_net_score:.1f}"
    )

    return final_sup_score, final_res_score, clean_sup, clean_res, logic_msg


# =========================================================================
# 🆕 [추가된 부분] 실시간 데이터를 긁어와서 위 함수에 대입하는 역할만 하는 함수
# =========================================================================
def load_live_data_and_analyze(tf='1h'):
    """
    웹소켓 수집기가 저장해둔 파일(live_price.json, 1h.json 등)에서
    데이터를 긁어와서 데이터프레임으로 변환 후 원본 기법 함수에 대입합니다.
    """
    
    # 1. 수집기가 실시간 갱신하는 현재가 파일 긁어오기
    if not os.path.exists("live_price.json"):
        print("⚠️ 실시간 현재가 파일(live_price.json)을 찾을 수 없습니다.")
        return None
        
    with open("live_price.json", "r") as f:
        price_data = json.load(f)
        current_price = float(price_data["price"])

    # 2. 수집기가 실시간 갱신하는 캔들(거래량 포함) 파일 긁어오기
    candle_file = f"{tf.lower()}.json"
    if not os.path.exists(candle_file):
        print(f"⚠️ 실시간 캔들 파일({candle_file})을 찾을 수 없습니다.")
        return None
        
    with open(candle_file, "r") as f:
        raw_candles = json.load(f)
        
    # 3. 긁어온 리스트 데이터를 기법 코드가 인식할 수 있도록 DataFrame으로 변환
    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'volCcy', 'volCcyQuote', 'confirm']
    df = pd.DataFrame(raw_candles, columns=cols)
    
    # 안전하게 숫자로 변환 (volume 데이터가 정확히 대입됨)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # 4. 변환된 실시간 데이터를 위 매매 기법(단 1도 건드리지 않음)에 쏙 대입
    return calculate_sr_score_by_touch(price=current_price, df=df, tf=tf)


# =========================================================================
# 🆕 [수정 및 추가 영역] 1H/4H/1D 다중 타임프레임 통합 및 중첩(Confluence) 추출 엔진
# =========================================================================
def analyze_all_timeframes_and_confluence(band_pct=0.005):
    """
    1시간, 4시간, 일봉 데이터를 모두 수집/분석한 뒤,
    서로 다른 타임프레임에서 가격대가 겹치는(Confluence) '초강력 마스터 매물대'를 찾아냅니다.
    """
    tfs = ['1h', '4h', '1d']
    all_results = {}
    
    print("\n🔍 [1H / 4H / 1D 전체 타임프레임 실시간 분석 시작]")
    print("-" * 65)
    
    # 1. 세 가지 타임프레임 각각 분석 실행
    for tf in tfs:
        res = load_live_data_and_analyze(tf)
        if res:
            all_results[tf] = res
            sup_score, res_score, sup_list, res_list, msg = res
            print(f"✅ {msg}")
        else:
            print(f"⚠️ {tf.upper()} 데이터를 불러오지 못했습니다. 수집기 실행 여부를 확인하세요.")

    if not all_results:
        print("❌ 분석할 수 있는 데이터가 없습니다.")
        return

    # 현재가 가져오기
    if not os.path.exists("live_price.json"):
        return
    with open("live_price.json", "r") as f:
        current_price = float(json.load(f)["price"])

    # 2. 모든 타임프레임의 지지/저항 데이터 수집
    raw_supports = []
    raw_resistances = []

    for tf, (sup_score, res_score, sup_list, res_list, msg) in all_results.items():
        for s in sup_list:
            item = s.copy()
            item['tf'] = tf.upper()
            raw_supports.append(item)
        for r in res_list:
            item = r.copy()
            item['tf'] = tf.upper()
            raw_resistances.append(item)

    # 3. 다중 타임프레임 중첩(Confluence) 추출 로직
    def find_confluence_levels(levels_list):
        if not levels_list:
            return []
        
        sorted_levels = sorted(levels_list, key=lambda x: x['price'])
        merged = []

        for item in sorted_levels:
            if not merged:
                merged.append({
                    'price': item['price'],
                    'scores': [item['score']],
                    'tfs': [item['tf']],
                    'strengths': [item['strength']],
                    'touch_counts': [item['touch_count']],
                    'fatigues': [item['test_fatigue']]
                })
                continue

            prev = merged[-1]
            # 오차범위(기본 0.5%) 이내로 서로 다른/같은 봉의 매물대가 겹치면 합침
            if abs(item['price'] - prev['price']) / current_price <= band_pct:
                prev['price'] = round((prev['price'] + item['price']) / 2, 2 if current_price >= 1000 else 4)
                prev['scores'].append(item['score'])
                if item['tf'] not in prev['tfs']:
                    prev['tfs'].append(item['tf'])
                prev['strengths'].append(item['strength'])
                prev['touch_counts'].append(item['touch_count'])
                prev['fatigues'].append(item['test_fatigue'])
            else:
                merged.append({
                    'price': item['price'],
                    'scores': [item['score']],
                    'tfs': [item['tf']],
                    'strengths': [item['strength']],
                    'touch_counts': [item['touch_count']],
                    'fatigues': [item['test_fatigue']]
                })

        # 가산점 부여 및 최종 등급 결정
        final_master_levels = []
        for m in merged:
            tf_count = len(m['tfs'])  # 겹친 타임프레임 개수 (1개, 2개, 3개)
            
            # 🔥 중첩 가산점 (2개 봉 겹침 = +30% 보너스, 3개 봉 모두 겹침 = +80% 초강력 보너스)
            confluence_bonus = 1.0
            if tf_count == 2:
                confluence_bonus = 1.3
            elif tf_count >= 3:
                confluence_bonus = 1.8

            base_total_score = sum(m['scores'])
            master_score = round(base_total_score * confluence_bonus, 1)

            if tf_count >= 3:
                grade = "🔥🔥 [3개 봉 완벽중첩] 절대 매물대"
            elif tf_count == 2:
                grade = "🔥 [2개 봉 중첩] 마스터 매물대"
            elif "강력" in m['strengths']:
                grade = "⭐ 단일 강력"
            else:
                grade = "🔹 일반"

            fatigue_status = "⚠️ 약화진행" if "약화(뚫림 위험↑)" in m['fatigues'] else "✅ 탄탄함"

            final_master_levels.append({
                'price': m['price'],
                'master_score': master_score,
                'tfs': "/".join(m['tfs']),
                'tf_count': tf_count,
                'grade': grade,
                'total_touches': sum(m['touch_counts']),
                'fatigue': fatigue_status
            })

        return sorted(final_master_levels, key=lambda x: x['price'])

    master_supports = find_confluence_levels(raw_supports)
    master_resistances = find_confluence_levels(raw_resistances)

    # 4. 최종 통합 마스터 분석 결과 출력
    print("\n" + "=" * 65)
    print(f"🎯 [최종 통합 마스터 분석 결과] (현재가: {current_price})")
    print("=" * 65)
    
    print("\n🔻 [마스터 지지선 (현재가 아래 가까운 순)]")
    sups_below = [s for s in master_supports if s['price'] < current_price]
    for s in sorted(sups_below, key=lambda x: x['price'], reverse=True)[:4]:
        print(f" 💰 가격: {s['price']:>9} | 점수: {s['master_score']:>6.1f}점 | "
              f"포함봉: {s['tfs']:<8} | 등급: {s['grade']} | 상태: {s['fatigue']}")

    print("\n🔺 [마스터 저항선 (현재가 위 가까운 순)]")
    res_above = [r for r in master_resistances if r['price'] > current_price]
    for r in sorted(res_above, key=lambda x: x['price'])[:4]:
        print(f" 🚨 가격: {r['price']:>9} | 점수: {r['master_score']:>6.1f}점 | "
              f"포함봉: {r['tfs']:<8} | 등급: {r['grade']} | 상태: {r['fatigue']}")
    print("=" * 65)


# =========================================================================
# 실행 테스트 (1H, 4H, 1D 실시간 수집 데이터 기반 다중 중첩 분석)
# =========================================================================
if __name__ == "__main__":
    analyze_all_timeframes_and_confluence(band_pct=0.005)
