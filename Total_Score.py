import json
import time
import pandas as pd
import skill  # skill.py에서는 순수 매매 기법만 불러옴


# 🛡️ [total_score 전용] EMA 120 추세 검문소 클래스
class EMAGatekeeper:
    def __init__(self, period=120, bonus_score=15, penalty_ratio=0.2):
        self.period = period
        self.bonus_score = bonus_score      # 추세 일치 시 가점 (+15점)
        self.penalty_ratio = penalty_ratio  # 역추세 시 점수 보존 비율 (20%만 인정 = 80% 상쇄)

    def evaluate(self, df_1h, base_long, base_short):
        """1시간봉 차트 기준으로 EMA 120을 계산하여 점수를 가감/상쇄시킵니다."""
        if df_1h is None or len(df_1h) < self.period:
            return base_long, base_short, {"status": "INSUFFICIENT_DATA"}

        df = df_1h.copy()
        df['ema120'] = df['close'].ewm(span=self.period, adjust=False).mean()
        
        current_price = float(df['close'].iloc[-1])
        ema_val = float(df['ema120'].iloc[-1])

        # 🟢 상승장 (가격 >= EMA 120): 롱 가점(+15), 숏 80% 상쇄
        if current_price >= ema_val:
            trend = "BULLISH"
            final_long = base_long + self.bonus_score
            final_short = base_short * self.penalty_ratio
        # 🔴 하락장 (가격 < EMA 120): 숏 가점(+15), 롱 80% 상쇄
        else:
            trend = "BEARISH"
            final_long = base_long * self.penalty_ratio
            final_short = base_short + self.bonus_score

        info = {
            "trend": trend,
            "current_price": round(current_price, 2),
            "ema120": round(ema_val, 2)
        }
        return round(final_long, 2), round(final_short, 2), info


# 🏛️ [점수 총괄 엔진] total_score 메인 클래스
class TotalScoreEngine:
    def __init__(self):
        self.candle_limit = 500
        self.weights = {'1h': 1.0, '4h': 2.0, '1d': 4.0}
        
        # 🎯 EMA 120 검문소를 total_score 내부에서 직접 생성
        self.ema_gatekeeper = EMAGatekeeper(period=120, bonus_score=15, penalty_ratio=0.2)

    def get_live_price(self):
        """실시간 가격 로드 (충돌 방지 로직 적용)"""
        for _ in range(3):
            try:
                with open("live_price.json", "r") as f:
                    data = json.load(f)
                    return float(data['price'])
            except (Exception, json.JSONDecodeError):
                time.sleep(0.02)
        return 0.0

    def get_data(self, tf):
        """타임프레임별 데이터 공급 (데이터 타입 안전 변환 적용)"""
        try:
            data = None
            for _ in range(3):
                try:
                    with open(f"{tf}.json", "r") as f:
                        data = json.load(f)
                        break
                except (Exception, json.JSONDecodeError):
                    time.sleep(0.02)

            if data is None:
                return None

            filtered_data = [
                [row[0], row[1], row[2], row[3], row[4], row[5], row[8]]
                for row in data
            ]
            df = pd.DataFrame(filtered_data, columns=['ts', 'o', 'h', 'l', 'close', 'vol', 'confirm'])
            
            # 💡 [안전장치] 수치형 컬럼들의 데이터 타입을 float로 강제 변환
            # JSON 읽기 시 문자열로 들어오는 현상 및 연산 에러를 100% 방지합니다.
            numeric_cols = ['o', 'h', 'l', 'close', 'vol']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            return df.tail(self.candle_limit).reset_index(drop=True)
        except Exception:
            return None

    def calculate_total_score(self, price):
        """1. skill.py에서 날것의 점수 수집 -> 2. EMA 120 검문소 통과 및 최종 산출"""
        raw_long_total = 0.0
        raw_short_total = 0.0
        analysis_summary = []
        strategy_tier = 1.5

        # 1. skill.py의 순수 기법들로부터 점수 수집
        for tf, t_weight in self.weights.items():
            df = self.get_data(tf)
            if df is not None and not df.empty:
                # skill.py 내부 기법 호출
                score_sr_l, score_sr_s, supps, resis, log_sr = skill.calculate_sr_score(price, df)
                score_vol_l, score_vol_s, log_vol = skill.calculate_volume_score(df)

                # 가중치 계산
                tf_long = (score_sr_l + score_vol_l) * strategy_tier * t_weight
                tf_short = (score_sr_s + score_vol_s) * strategy_tier * t_weight

                raw_long_total += tf_long
                raw_short_total += tf_short

                analysis_summary.append((tf, tf_long - tf_short, supps, resis, f"{log_sr} | {log_vol}"))

        # 2. 🛡️ total_score 내부에 위치한 EMA 120 검문소 통과!
        df_1h = self.get_data('1h')
        final_long, final_short, ema_info = self.ema_gatekeeper.evaluate(
            df_1h=df_1h,
            base_long=raw_long_total,
            base_short=raw_short_total
        )

        # 3. 최종 상쇄 순점수 (롱 점수 - 숏 점수)
        final_score = final_long - final_short

        return final_score, analysis_summary, ema_info
