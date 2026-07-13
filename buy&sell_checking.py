import pandas as pd
import json
import strategy

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

    def check_all_weighted(self, price):
        """가중치가 적용된 자동 점수 산출 로직"""
        total_weighted_score = 0
        analysis_details = []
        
        for tf, weight in self.weights.items():
            df = self.get_data(tf)
            if df is not None and not df.empty:
                # strategy.py 모듈의 기존 함수 호출
                long_score, short_score, status = strategy.get_dynamic_ema200_score(price, df)
                
                # 가중치 적용 점수 산출
                weighted_score = (long_score - short_score) * weight
                total_weighted_score += weighted_score
                analysis_details.append(f"{tf}: {status}({weighted_score:.1f})")
        
        return total_weighted_score, analysis_details
