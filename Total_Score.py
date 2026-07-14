import pandas as pd
import json
import skill

class BuyAndSellChecking:
    def __init__(self):
        

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
        
