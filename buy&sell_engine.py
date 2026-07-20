# buy&sell_engine.py
from buy_sell_checking import BuyAndSellChecking

class BuyAndSellEngine:
    def __init__(self):
        self.checker = BuyAndSellChecking()
    
    def get_decision(self, price):
        # 💡 [형식 유지] 함수명, 매개변수(price), 리턴 구조는 완전히 동일합니다.
        # 💡 [알맹이 변경] 기존에 없던 get_weighted_score 대신, 새로 개편된 웹소켓용 
        # BuyAndSellChecking의 perform_all_calculations(price)를 호출하여 
        # 첫 번째 리턴값인 '최종 점수(total_score)'를 쏙 골라오도록 내부만 안전하게 연결했습니다.
        score, _, _ = self.checker.perform_all_calculations(price)
        
        return score, ("롱 진입" if score >= 25 else "숏 진입" if score <= -25 else "대기")
