# buy&sell_engine.py
from Total_Score import TotalScoreCalculator  # 계산을 전담하는 Total_Score.py 연동
from shared_hub import hub                    # 0.1초마다 데이터를 주고받는 메모리 장부 연동

class BuyAndSellEngine:
    def __init__(self):
        # Total_Score.py 파일 안의 계산기 클래스를 불러와 장착합니다.
        self.calculator = TotalScoreCalculator()
        
        # ⚙️ [진입 기준 점수 설정판] - 필요시 수치만 수정 가능
        self.long_threshold = 25    # +25점 이상이면 롱 진입
        self.short_threshold = -25  # -25점 이하이면 숏 진입

    def get_decision(self, price):
        # 1. 지지/저항 점수가 상쇄 적용된 최종 총점을 불러옵니다.
        score = self.calculator.get_total_score(price)
        
        # 2. [기존 리턴 구조 유지] 상쇄된 총점에 따른 최종 롱/숏/대기 판정
        if score >= self.long_threshold:
            decision = "롱 진입"
        elif score <= self.short_threshold:
            decision = "숏 진입"
        else:
            decision = "대기"
            
        return score, decision
