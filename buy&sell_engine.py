# buy&sell_engine.py
from Total_Score import TotalScoreCalculator  # 계산을 전담하는 Total_Score.py 연동
from shared_hub import hub                    # 0.1초마다 데이터를 주고받는 메모리 장부 연동

class BuyAndSellEngine:
    def __init__(self):
        # Total_Score.py 파일 안의 계산기 클래스를 불러와 장착합니다.
        self.calculator = TotalScoreCalculator()
    
    def get_decision(self, price):
        # 1. 메모리 장부와 연동된 계산기를 통해 현재가의 최종 점수를 뽑아냅니다.
        score = self.calculator.get_total_score(price)
        
        # 2. [형식 유지] 점수 기준에 따른 최종 롱/숏/대기 텍스트 판정을 리턴합니다.
        return score, ("롱 진입" if score >= 25 else "숏 진입" if score <= -25 else "대기")
