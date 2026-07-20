import pandas as pd
import json
import skill
import time

class BuyAndSellChecking:
    def __init__(self):
        # 1시간, 4시간, 1일봉 가중치 설정 (시간이 커질수록 가중치 증가)
        self.candle_limit = 500
        self.weights = {
            '1h': 1.0, 
            '4h': 2.0, 
            '1d': 4.0
        }

    def get_live_price(self):
        """라이브 시장가 파일에서 가격을 안전하게 읽어오는 함수"""
        # [보완] 웹소켓 수집기가 파일에 쓰고 있는 찰나의 순간에 읽어서 발생하는 충돌(에러)을 방지합니다.
        for _ in range(3):
            try:
                with open("live_price.json", "r") as f:
                    data = json.load(f)
                    return float(data['price'])
            except (Exception, json.JSONDecodeError):
                time.sleep(0.02) # 충돌 시 0.02초 후 재시도
        return 0.0

    def get_data(self, tf):
        """[규격 적용] 타임프레임별 500봉 데이터 공급"""
        try:
            # 파일 읽기 동시성 충돌 방지 안전장치
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

            # 💡 [코드 변경 1] 컬럼 개수 불일치 해결
            # 웹소켓이 저장하는 데이터는 9개인데, 기존 형식은 7개 컬럼('ts' ~ 'confirm')을 원합니다.
            # 데이터프레임을 만들기 전에 원하는 7개 데이터만 쏙 골라내어 ValueError를 차단합니다.
            filtered_data = [
                [row[0], row[1], row[2], row[3], row[4], row[5], row[8]]
                for row in data
            ]
            
            df = pd.DataFrame(filtered_data, columns=['ts', 'o', 'h', 'l', 'close', 'vol', 'confirm'])
            
            # 💡 [코드 변경 2] 정렬 방식 개편
            # 새 웹소켓 수집기는 데이터를 이미 [과거 -> 최신] 순으로 정렬해서 저장합니다.
            # 따라서 기존의 역정렬(iloc[::-1])을 실행하면 오히려 데이터가 거꾸로 뒤집힙니다.
            # 뒤집기 없이 맨 뒤의 최신 500봉(.tail)을 정방향 그대로 가져오도록 알맹이만 수정했습니다.
            df = df.tail(self.candle_limit).reset_index(drop=True)
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
