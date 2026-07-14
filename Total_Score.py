import pandas as pd
import json
import skill

class BuyAndSellChecking:
    def __init__(self):
        # 1시간, 4시간, 1일봉 가중치 설정 (시간이 커질수록 가중치 증가)
        self.candle_limit = 500
        self.weights = {
            '1h': 1.0, 
            '4h': 2.0, 
            '1d': 4.0
        }

    def get_data(self, tf):
        """[규격 적용] 타임프레임별 500봉 데이터 공급"""
        try:
            # 1h.json, 4h.json, 1d.json 파일로부터 데이터를 읽어옴
            with open(f"{tf}.json", "r") as f:
                data = json.load(f)
                df = pd.DataFrame(data, columns=['ts', 'o', 'h', 'l', 'close', 'vol', 'confirm'])
                # 항상 최신 500봉 유지
                df = df.iloc[::-1].head(self.candle_limit).reset_index(drop=True)
                return df
        except Exception:
            return None

    def perform_all_calculations(self, price):
        # 1. 설정 및 초기화
        total_score = 0
        analysis_summary = []
        strategy_tier = 1.5 
        
        # 2. 타임프레임별 가중치 자동 계산 루프
        for tf, t_weight in self.weights.items():
            df = self.get_data(tf)
            if df is not None and not df.empty:
                score_sr, supports, resistances, log_msg_sr = skill.calculate_sr_score(price, df)
                score_vol, log_msg_vol = skill.calculate_volume_score(df)
                
                final_score = (score_sr + score_vol) * strategy_tier * t_weight
                total_score += final_score
                log_msg = f"{log_msg_sr} | {log_msg_vol}"
                analysis_summary.append((tf, final_score, supports, resistances, log_msg))

        # 3. EMA 분석
        ema_engine = skill.EMASignalEngine()
        ema_total_score, ema_results = ema_engine.get_ema_analysis(self.get_data)
        
        # 4. 1h 기준 EMA 200 추세 로직
        df_1h = self.get_data('1h')
        long_score, short_score, status = skill.get_dynamic_ema200_score(price, df_1h)
        total_score += (long_score + short_score)

        return total_score, analysis_summary, status
