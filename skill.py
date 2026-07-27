import pandas as pd
import numpy as np
import json
import os
import time

# =========================================================================
# v3 추가 보완 (점수 계산 로직은 전혀 건드리지 않고, 파일 입출력 안정성만 보강함)
#  - 수집기가 파일을 쓰는 도중 읽어서 JSON이 깨지는 경우 대비: 재시도 로직 추가
#  - live_price.json에 시간 정보가 있으면 너무 오래된(멈춘) 데이터인지 감지하는
#    선택적 신선도 체크 추가 (시간 필드가 없으면 자동으로 건너뜀 = 기존 동작과 동일)
#  - 파일 손상/파싱 실패 시 스크립트 전체가 죽지 않고 경고만 띄우고 해당 타임프레임만 건너뜀
# =========================================================================

def _load_json_with_retry(path, retries=3, delay=0.05):
    """
    수집기가 파일을 쓰는 도중과 읽는 시점이 겹치면 JSON이 일시적으로 깨져 보일 수 있어서,
    아주 짧게 텀을 두고 몇 번 재시도한 뒤에도 실패하면 (None, 에러메시지)를 돌려줌.
    점수 계산 로직과는 무관한 순수 파일 읽기 안정성 보강임.
    """
    last_err = None
    for attempt in range(retries):
        try:
            with open(path, "r") as f:
                return json.load(f), None
        except (json.JSONDecodeError, OSError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(delay)
    return None, str(last_err)


def _check_price_staleness(price_data, max_staleness_sec, label=""):
    """
    live_price.json 안에 timestamp/ts/time/updated_at 중 하나라도 있으면 그 값을 기준으로
    현재 시각과의 차이를 계산해서 너무 오래된 데이터면 경고만 띄움.
    해당 필드가 없거나 형식을 알 수 없으면 조용히 건너뜀 (기존 동작과 100% 동일하게 유지).
    """
    if max_staleness_sec is None:
        return
    ts_val = None
    for key in ("timestamp", "ts", "time", "updated_at"):
        if key in price_data:
            ts_val = price_data[key]
            break
    if ts_val is None:
        return
    try:
        ts_num = float(ts_val)
        ts_sec = ts_num / 1000 if ts_num > 1e12 else ts_num  # 밀리초 단위로 추정되면 보정
        age = time.time() - ts_sec
        if age > max_staleness_sec:
            print(f"⚠️ {label}live_price.json이 {age:.0f}초 전 데이터로 보입니다 "
                  f"(허용치 {max_staleness_sec}초) — 수집기가 멈췄을 수 있습니다.")
    except (TypeError, ValueError):
        pass


# =========================================================================
# v2 변경 사항 요약 (원본 로직/구조는 그대로 유지하고, 아래 항목만 수정·추가했습니다)
#
# [버그 수정]
#  1. 캔들 정렬 순서 미검증 → timestamp로 정렬 + confirm 컬럼으로 미확정봉 제거
#     (confirm 컬럼이 없으면 원본 방식인 iloc[:-1]로 자동 폴백)
#  2. 타임프레임 가중치(tf_multiplier)가 레벨별 score엔 안 곱해지고 합산 단계에서만
#     곱해지던 문제 → 레벨 단위로 반영하고 합산 단계 중복 곱셈 제거
#  3. 라이브 파이프라인에 custom_tf_weights / longevity_bonus_max / volume_lookback 등이
#     전달되지 않던 문제 → 전부 전달되도록 연결
#  4. 병합 시 avg_volume_ratio가 "터치수 가중평균"이라는 주석과 다르게 단순평균이던 문제 → 수정
#  5. 데이터부족/현재가오류 상황에서 `if res:`가 항상 True로 평가되던 문제 → 명시적 체크로 수정
#  6. find_confluence_levels의 소수점 자리수가 원본 함수(3단계)와 다른 2단계였던 문제 → 공통 함수로 통일
#  7. 병합 로직이 "직전 병합 결과"와 비교해 체이닝(연쇄 병합)될 수 있던 문제 → 최초 anchor 가격 기준으로 비교
#  + live_price.json 비원자적 중복 읽기, ATR NaN 처리, has_volume가 전부 NaN인 경우,
#    캔들 컬럼 수 미검증 등 보완
#
# [신규 추가 — "사람이 직접 보는 것처럼" 판단하기 위한 정성적 보정]
#  A. 터치 이후 반응(바운스) 강도 — 닿고 나서 실제로 튕겨났는지
#  B. 거부 캔들 모양(꼬리:몸통 비율) — 핀바형 거부 캔들 가중
#  C. 라운드 넘버(심리적 가격) 근접 가산점
#  D. 지지/저항 역할전환(role reversal) 감지
#  E. 레벨 접근 속도(모멘텀) 진단 (정보성 라벨, 점수엔 미반영)
#  F. "신선도"(마지막 터치 이후 경과) 진단
#  → A~D는 하나의 "정성적 보너스"로 묶고 -30%~+80%로 캡을 씌워 점수에 반영 (폭주 방지)
# =========================================================================


def get_price_decimals(price):
    """가격대별 반올림 소수점 자리수 (원본의 3단계 기준을 파일 전체에서 통일해서 사용)"""
    if price >= 1000:
        return 2
    elif price >= 1:
        return 4
    else:
        return 6


def _classify_freshness(last_touch_idx, n_candles):
    candles_since = (n_candles - 1) - last_touch_idx
    ratio = candles_since / max(1, n_candles - 1)
    if ratio > 0.5:
        return "장기 미검증(신선함↑)"
    elif ratio < 0.1:
        return "최근 활발히 테스트"
    else:
        return "보통"


def _classify_reaction(avg_reaction_pct, touch_count):
    if touch_count == 0:
        return "정보부족"
    if avg_reaction_pct >= 1.0:
        return "반응 좋음(잘 튕겨남)"
    elif avg_reaction_pct <= -0.5:
        return "반응 약함(뚫리는 경향)"
    else:
        return "반응 보통"


def calculate_sr_score_by_touch(price, df, tf='1h', custom_tf_weights=None,
                                 longevity_bonus_max=0.5, volume_lookback=20,
                                 reaction_lookback=5):
    """
    과거 캔들의 시간 가중치(Time Decay), 동적 ATR 변동성, 거래량 가중치가 적용된
    순수 터치 빈도 기반 Zero-Lag 지지/저항 분석 함수
    (실전 자동매매 보완판 + 장기 생존 보너스 + 거래량 가중치 + 테스트 피로도 진단
     + 터치 후 반응 / 거부캔들 품질 / 라운드넘버 / 역할전환 / 신선도 진단 추가)

    longevity_bonus_max: 첫 터치~마지막 터치 폭(생존 기간)이 전체 히스토리를 꽉 채울 때
                         레벨 점수에 추가로 곱해줄 최대 보너스 비율 (기본 0.5 = 최대 +50%)
    volume_lookback: 거래량 상대 비율 계산 시 사용할 이동평균 기간 (기본 20)
    reaction_lookback: 터치 이후 반응(바운스)을 측정할 때 몇 개 봉 뒤를 볼지 (기본 5)
    """
    if df is None or df.empty:
        return 0.0, 0.0, [], [], "데이터 부족으로 계산 불가"

    if price is None or price <= 0:
        return 0.0, 0.0, [], [], "현재가 오류"

    df = df.copy()

    # [🆕 버그 수정 1] 캔들 정렬 순서 보장 — 수집기가 최신순(역순)으로 저장했더라도
    # timestamp 기준 오름차순 정렬해서 "index 0=가장 오래된 봉" 가정이 항상 성립하게 함
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
        df = df.sort_values('timestamp', kind='mergesort').reset_index(drop=True)

    # [🆕 버그 수정 1-2] "마지막 행=미확정봉"이라는 위치 추정 대신 confirm 컬럼으로 필터링
    # confirm 컬럼이 없으면(순수 OHLCV만 들어온 경우) 기존 방식(iloc[:-1])으로 폴백
    if 'confirm' in df.columns:
        confirm_num = pd.to_numeric(df['confirm'], errors='coerce')
        analysis_df = df[confirm_num == 1].reset_index(drop=True)
    else:
        analysis_df = df.iloc[:-1].copy()

    n_candles = len(analysis_df)
    if n_candles < 50:
        return 0.0, 0.0, [], [], "데이터 부족으로 계산 불가"

    # =========================================================================
    # [⚙️ 0. 거래량 상대 비율 계산 (Relative Volume)]
    # =========================================================================
    has_volume = 'volume' in analysis_df.columns and analysis_df['volume'].notna().any()
    if has_volume:
        vol_ma = analysis_df['volume'].rolling(volume_lookback, min_periods=5).mean()
        vol_ratio_raw = (analysis_df['volume'] / vol_ma).fillna(1.0)
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

    # [🆕 버그 수정] ATR이 NaN이 되는 경우를 암묵적 min/max 동작에 맡기지 않고 명시적으로 처리
    if pd.isna(atr) or atr <= 0:
        band_pct = 0.010
    else:
        dynamic_band_pct = (atr / price) * 0.25
        band_pct = max(0.002, min(0.010, dynamic_band_pct))
    distance_pct = 0.040

    decimals = get_price_decimals(price)

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
    candle_range = (analysis_df['high'] - analysis_df['low']).replace(0, np.nan)
    upper_wick = (analysis_df['high'] - body_max)
    lower_wick = (body_min - analysis_df['low'])
    closes = analysis_df['close'].values

    # 🆕 [B. 거부 캔들 품질] 캔들별 위/아래 꼬리 비율 (0~1)
    upper_wick_ratio = (upper_wick / candle_range).fillna(0.0).clip(0, 1).values
    lower_wick_ratio = (lower_wick / candle_range).fillna(0.0).clip(0, 1).values

    sup_details = []
    res_details = []

    REACTION_SCALE = 12.0
    REJECTION_BONUS_MAX = 0.30
    ROUND_NUMBER_BONUS_MAX = 0.15
    ROLE_REVERSAL_BONUS = 0.15

    for p_level in grid_prices:
        band_low = p_level - (step / 2)
        band_high = p_level + (step / 2)

        wick_touched = (analysis_df['high'] >= band_low) & (analysis_df['low'] <= band_high)
        body_touched = (body_max >= band_low) & (body_min <= band_high)

        base_touch_weights = np.where(body_touched, 1.2, np.where(wick_touched, 0.5, 0.0))
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

            is_support = p_level <= price

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

            # 🆕 [A. 터치 후 반응(바운스) 강도]
            reaction_pcts = []
            for idx in touched_idx:
                future_idx = idx + reaction_lookback
                if future_idx < n_candles and closes[idx] > 0:
                    pct_move = (closes[future_idx] - closes[idx]) / closes[idx]
                    reaction_pcts.append(pct_move if is_support else -pct_move)
            avg_reaction_pct = float(np.mean(reaction_pcts) * 100) if reaction_pcts else 0.0
            reaction_bonus = float(np.clip(avg_reaction_pct / 100 * REACTION_SCALE, -0.20, 0.35))
            reaction_label = _classify_reaction(avg_reaction_pct, len(reaction_pcts))

            # 🆕 [B. 거부 캔들 모양(꼬리 품질)]
            if touched_idx.size > 0:
                relevant_wick_ratio = lower_wick_ratio if is_support else upper_wick_ratio
                avg_wick_ratio = float(relevant_wick_ratio[touched_idx].mean())
            else:
                avg_wick_ratio = 0.0
            rejection_bonus = avg_wick_ratio * REJECTION_BONUS_MAX

            # 🆕 [C. 라운드 넘버(심리적 가격) 근접 가산점]
            near_round_number = False
            round_number_bonus = 0.0
            if p_level > 0:
                magnitude = 10 ** np.floor(np.log10(p_level))
                candidates = [magnitude * m for m in (0.1, 0.25, 0.5, 1, 2, 2.5, 5, 10)]
                nearest = min(candidates, key=lambda c: abs(c - p_level))
                distance_ratio = abs(nearest - p_level) / p_level
                if distance_ratio <= band_pct:
                    closeness = 1.0 - (distance_ratio / band_pct)
                    round_number_bonus = closeness * ROUND_NUMBER_BONUS_MAX
                    near_round_number = True

            # 🆕 [D. 지지/저항 역할전환(role reversal) 감지]
            early_window = max(5, n_candles // 3)
            early_closes = closes[:early_window]
            if is_support:
                role_reversal = bool((early_closes < band_low).mean() > 0.5)
            else:
                role_reversal = bool((early_closes > band_high).mean() > 0.5)

            # 🆕 [E. 레벨 접근 속도(모멘텀) — 정보성 진단, 점수엔 미반영]
            approach_speeds = []
            for idx in touched_idx:
                start = max(0, idx - 3)
                if idx > start:
                    pre_range = (analysis_df['high'].iloc[start:idx] - analysis_df['low'].iloc[start:idx]).mean()
                    approach_speeds.append(pre_range / price if price > 0 else 0.0)
            if approach_speeds:
                avg_speed = float(np.mean(approach_speeds))
                approach_label = "급격한 접근" if avg_speed > band_pct * 1.5 else "완만한 접근"
            else:
                approach_label = "정보부족"

            # 🆕 [F. "신선도" — 마지막 터치 이후 경과]
            freshness_label = _classify_freshness(last_touch_idx, n_candles)

            # 정성적 보너스(A~D)를 하나로 묶어 -30%~+80%로 캡 → 폭주 방지
            qualitative_bonus = reaction_bonus + rejection_bonus + round_number_bonus
            qualitative_bonus += (ROLE_REVERSAL_BONUS if role_reversal else 0.0)
            qualitative_multiplier = 1.0 + float(np.clip(qualitative_bonus, -0.30, 0.80))

            # [🆕 버그 수정 2] tf_multiplier를 레벨 단위 점수에도 반영
            total_level_score = (
                cfg['base_score'] * longevity_multiplier * tf_multiplier * qualitative_multiplier
            )

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
                'avg_volume_ratio': round(avg_volume_ratio, 2),
                'test_fatigue': fatigue_label,
                'reaction_pct': round(avg_reaction_pct, 2),
                'reaction_label': reaction_label,
                'rejection_wick_ratio': round(avg_wick_ratio, 2),
                'near_round_number': near_round_number,
                'role_reversal': role_reversal,
                'approach_speed': approach_label,
                'freshness': freshness_label,
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
                new_item = item.copy()
                new_item['_anchor_price'] = item['price']  # [🆕 버그 수정 7] 체이닝 방지용 고정 기준점
                merged_levels.append(new_item)
                continue

            prev = merged_levels[-1]
            # [🆕 버그 수정 7] prev의 (계속 바뀔 수 있는) price가 아니라 최초 anchor와 비교
            if abs(item['price'] - prev['_anchor_price']) / price < band_pct:
                prev_touches = prev['touch_count']
                item_touches = item['touch_count']
                total_touches = max(1, prev_touches + item_touches)

                if item['effective_score'] > prev['effective_score']:
                    prev['price'] = item['price']
                    prev['strength'] = item['strength']

                prev['score'] = round(prev['score'] + item['score'] * 0.7, 1)
                prev['effective_score'] = round(prev['effective_score'] + item['effective_score'] * 0.7, 2)

                prev['first_touch_idx'] = min(prev['first_touch_idx'], item['first_touch_idx'])
                prev['last_touch_idx'] = max(prev['last_touch_idx'], item['last_touch_idx'])
                prev['survival_span'] = prev['last_touch_idx'] - prev['first_touch_idx']
                prev['longevity_bonus'] = round(max(prev['longevity_bonus'], item['longevity_bonus']), 3)

                # [🆕 버그 수정 4] 터치수 가중평균으로 정확히 계산
                prev['avg_volume_ratio'] = round(
                    (prev['avg_volume_ratio'] * prev_touches + item['avg_volume_ratio'] * item_touches) / total_touches, 2
                )
                prev['reaction_pct'] = round(
                    (prev['reaction_pct'] * prev_touches + item['reaction_pct'] * item_touches) / total_touches, 2
                )
                prev['rejection_wick_ratio'] = round(
                    (prev['rejection_wick_ratio'] * prev_touches + item['rejection_wick_ratio'] * item_touches) / total_touches, 2
                )
                prev['touch_count'] = prev_touches + item_touches

                if item['test_fatigue'] == "약화(뚫림 위험↑)":
                    prev['test_fatigue'] = item['test_fatigue']
                prev['near_round_number'] = prev['near_round_number'] or item['near_round_number']
                prev['role_reversal'] = prev['role_reversal'] or item['role_reversal']
                prev['reaction_label'] = _classify_reaction(prev['reaction_pct'], prev['touch_count'])
                prev['freshness'] = _classify_freshness(prev['last_touch_idx'], n_candles)
            else:
                new_item = item.copy()
                new_item['_anchor_price'] = item['price']
                merged_levels.append(new_item)

        for lvl in merged_levels:
            lvl.pop('_anchor_price', None)

        return sorted(merged_levels, key=lambda x: x['price'])

    clean_sup = merge_adjacent_levels(sup_details)
    clean_res = merge_adjacent_levels(res_details)

    # [🆕 버그 수정 2] 레벨별 score에 이미 tf_multiplier가 반영돼 있으므로 여기서 다시 곱하지 않음
    final_sup_score = sum(item['score'] for item in clean_sup)
    final_res_score = sum(item['score'] for item in clean_res)
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
# 실시간 데이터를 긁어와서 위 함수에 대입하는 역할만 하는 함수
# =========================================================================
def load_live_data_and_analyze(tf='1h', current_price=None, custom_tf_weights=None,
                                longevity_bonus_max=0.5, volume_lookback=20,
                                reaction_lookback=5, data_dir=".", max_price_staleness_sec=None):
    """
    웹소켓 수집기가 저장해둔 파일(live_price.json, 1h.json 등)에서
    데이터를 긁어와서 데이터프레임으로 변환 후 분석 함수에 대입합니다.

    current_price: 이미 다른 곳에서 읽어온 현재가가 있으면 넘겨서 중복 파일 읽기를 피함
    max_price_staleness_sec: live_price.json 안에 timestamp/ts/time/updated_at 같은
      시간 필드가 있을 경우, 이 값(초)보다 오래된 데이터면 경고만 띄움 (기본 None=미사용).
      해당 필드가 아예 없으면 신선도 체크는 조용히 건너뜀 — 기존 동작과 동일하게 유지됨.
    나머지 파라미터는 모두 calculate_sr_score_by_touch로 그대로 전달됨
      ([🆕 버그 수정 3] 기존엔 이 파라미터들이 라이브 파이프라인까지 안 이어졌음)
    """
    price_path = os.path.join(data_dir, "live_price.json")
    candle_path = os.path.join(data_dir, f"{tf.lower()}.json")

    if current_price is None:
        if not os.path.exists(price_path):
            print(f"⚠️ 실시간 현재가 파일({price_path})을 찾을 수 없습니다.")
            return None
        # 🆕 [안정성 보완] 수집기가 쓰는 도중 읽어 JSON이 깨지는 경우를 대비한 재시도
        price_data, err = _load_json_with_retry(price_path)
        if price_data is None:
            print(f"⚠️ 실시간 현재가 파일({price_path}) 파싱 실패: {err}")
            return None
        current_price = float(price_data["price"])
        _check_price_staleness(price_data, max_price_staleness_sec)  # 🆕 선택적 신선도 체크

    if not os.path.exists(candle_path):
        print(f"⚠️ 실시간 캔들 파일({candle_path})을 찾을 수 없습니다.")
        return None

    # 🆕 [안정성 보완] 캔들 파일도 동일하게 재시도 안전 읽기로 변경
    raw_candles, err = _load_json_with_retry(candle_path)
    if raw_candles is None:
        print(f"⚠️ [{tf}] 캔들 파일 파싱 실패: {err}")
        return None

    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'volCcy', 'volCcyQuote', 'confirm']

    # 🆕 [거래량 라이브 데이터 점검 1] 캔들 한 줄의 컬럼 수가 예상(9개)과 다르면
    # 조용히 밀려서 잘못 매핑되지 않도록 여기서 걸러서 알려줌
    if raw_candles:
        actual_len = len(raw_candles[0])
        if actual_len != len(cols):
            print(f"⚠️ [{tf}] 캔들 데이터 컬럼 수가 예상과 다릅니다 (예상 {len(cols)}개, 실제 {actual_len}개). "
                  f"수집기 응답 포맷이 바뀌었을 수 있으니 cols 리스트를 확인하세요.")
            return None

    df = pd.DataFrame(raw_candles, columns=cols)

    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # 🆕 [거래량 라이브 데이터 점검 2] volume이 전부 결측/0이면 실제로는 거래량이
    # 안 들어오고 있다는 뜻이므로, 조용히 중립(1.0) 처리되기 전에 눈에 띄게 경고
    if df['volume'].isna().all() or (df['volume'].fillna(0) == 0).all():
        print(f"⚠️ [{tf}] volume 데이터가 비어있거나 전부 0입니다 — 거래량 가중치가 중립(1.0)으로만 적용됩니다. "
              f"수집기가 실제로 거래량 필드를 저장하고 있는지 확인하세요.")

    return calculate_sr_score_by_touch(
        price=current_price, df=df, tf=tf,
        custom_tf_weights=custom_tf_weights,
        longevity_bonus_max=longevity_bonus_max,
        volume_lookback=volume_lookback,
        reaction_lookback=reaction_lookback,
    )


# =========================================================================
# 1H/4H/1D 다중 타임프레임 통합 및 중첩(Confluence) 추출 엔진
# =========================================================================
ERROR_MESSAGES = {"데이터 부족으로 계산 불가", "현재가 오류"}


def analyze_all_timeframes_and_confluence(band_pct=0.005, custom_tf_weights=None,
                                           longevity_bonus_max=0.5, volume_lookback=20,
                                           reaction_lookback=5, data_dir=".",
                                           max_price_staleness_sec=None):
    """
    1시간, 4시간, 일봉 데이터를 모두 수집/분석한 뒤,
    서로 다른 타임프레임에서 가격대가 겹치는(Confluence) '초강력 마스터 매물대'를 찾아냅니다.

    max_price_staleness_sec: live_price.json에 시간 필드가 있을 때만 동작하는 선택적
      신선도 체크. 기본 None=미사용(기존과 동일). 자세한 내용은 load_live_data_and_analyze 참고.
    """
    tfs = ['1h', '4h', '1d']
    all_results = {}

    price_path = os.path.join(data_dir, "live_price.json")
    if not os.path.exists(price_path):
        print(f"❌ 현재가 파일({price_path})을 찾을 수 없어 분석을 시작할 수 없습니다.")
        return
    # 🆕 [안정성 보완] 재시도 안전 읽기로 교체 (여전히 한 번만 읽어서 아래에 동일하게 전달)
    price_data, err = _load_json_with_retry(price_path)
    if price_data is None:
        print(f"❌ 현재가 파일({price_path}) 파싱 실패: {err}")
        return
    current_price = float(price_data["price"])
    _check_price_staleness(price_data, max_price_staleness_sec)  # 🆕 선택적 신선도 체크

    print("\n🔍 [1H / 4H / 1D 전체 타임프레임 실시간 분석 시작]")
    print("-" * 65)

    for tf in tfs:
        res = load_live_data_and_analyze(
            tf, current_price=current_price,
            custom_tf_weights=custom_tf_weights,
            longevity_bonus_max=longevity_bonus_max,
            volume_lookback=volume_lookback,
            reaction_lookback=reaction_lookback,
            data_dir=data_dir,
            max_price_staleness_sec=max_price_staleness_sec,
        )
        # [🆕 버그 수정 5] res가 None이 아니어도 에러 메시지 튜플일 수 있으므로 명시적으로 확인
        if res is not None and res[4] not in ERROR_MESSAGES:
            all_results[tf] = res
            print(f"✅ {res[4]}")
        else:
            reason = res[4] if res is not None else "파일 없음"
            print(f"⚠️ {tf.upper()} 데이터를 불러오지 못했습니다 ({reason}). 수집기 실행 여부를 확인하세요.")

    if not all_results:
        print("❌ 분석할 수 있는 데이터가 없습니다.")
        return

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

    def find_confluence_levels(levels_list):
        if not levels_list:
            return []

        sorted_levels = sorted(levels_list, key=lambda x: x['price'])
        merged = []
        merge_decimals = get_price_decimals(current_price)  # [🆕 버그 수정 6] 원본과 동일한 3단계 기준

        def new_cluster(item):
            return {
                'price': item['price'],
                '_anchor_price': item['price'],  # [🆕 버그 수정 7] 체이닝 방지
                'scores': [item['score']],
                'tfs': [item['tf']],
                'strengths': [item['strength']],
                'touch_counts': [item['touch_count']],
                'fatigues': [item['test_fatigue']],
                'reactions': [item['reaction_label']],
                'role_reversals': [item['role_reversal']],
                'round_numbers': [item['near_round_number']],
            }

        for item in sorted_levels:
            if not merged:
                merged.append(new_cluster(item))
                continue

            prev = merged[-1]
            if abs(item['price'] - prev['_anchor_price']) / current_price <= band_pct:
                prev['price'] = round((prev['price'] + item['price']) / 2, merge_decimals)
                prev['scores'].append(item['score'])
                if item['tf'] not in prev['tfs']:
                    prev['tfs'].append(item['tf'])
                prev['strengths'].append(item['strength'])
                prev['touch_counts'].append(item['touch_count'])
                prev['fatigues'].append(item['test_fatigue'])
                prev['reactions'].append(item['reaction_label'])
                prev['role_reversals'].append(item['role_reversal'])
                prev['round_numbers'].append(item['near_round_number'])
            else:
                merged.append(new_cluster(item))

        final_master_levels = []
        for m in merged:
            tf_count = len(m['tfs'])

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
            reaction_status = ("🙆 반응 좋음" if any("좋음" in r for r in m['reactions'])
                                else "🙅 반응 약함" if any("약함" in r for r in m['reactions'])
                                else "➖ 보통")
            extra_tags = []
            if any(m['role_reversals']):
                extra_tags.append("역할전환")
            if any(m['round_numbers']):
                extra_tags.append("라운드넘버")

            final_master_levels.append({
                'price': m['price'],
                'master_score': master_score,
                'tfs': "/".join(m['tfs']),
                'tf_count': tf_count,
                'grade': grade,
                'total_touches': sum(m['touch_counts']),
                'fatigue': fatigue_status,
                'reaction': reaction_status,
                'tags': ",".join(extra_tags) if extra_tags else "-",
            })

        return sorted(final_master_levels, key=lambda x: x['price'])

    master_supports = find_confluence_levels(raw_supports)
    master_resistances = find_confluence_levels(raw_resistances)

    print("\n" + "=" * 65)
    print(f"🎯 [최종 통합 마스터 분석 결과] (현재가: {current_price})")
    print("=" * 65)

    print("\n🔻 [마스터 지지선 (현재가 아래 가까운 순)]")
    sups_below = [s for s in master_supports if s['price'] < current_price]
    for s in sorted(sups_below, key=lambda x: x['price'], reverse=True)[:4]:
        print(f" 💰 가격: {s['price']:>9} | 점수: {s['master_score']:>6.1f}점 | "
              f"포함봉: {s['tfs']:<8} | 등급: {s['grade']} | 상태: {s['fatigue']} {s['reaction']} | 태그: {s['tags']}")

    print("\n🔺 [마스터 저항선 (현재가 위 가까운 순)]")
    res_above = [r for r in master_resistances if r['price'] > current_price]
    for r in sorted(res_above, key=lambda x: x['price'])[:4]:
        print(f" 🚨 가격: {r['price']:>9} | 점수: {r['master_score']:>6.1f}점 | "
              f"포함봉: {r['tfs']:<8} | 등급: {r['grade']} | 상태: {r['fatigue']} {r['reaction']} | 태그: {r['tags']}")
    print("=" * 65)


if __name__ == "__main__":
    analyze_all_timeframes_and_confluence(band_pct=0.005)
