# buy&sell_engine.py
from buy_sell_checking import BuyAndSellChecking

class BuyAndSellEngine:
    def __init__(self):
        self.checker = BuyAndSellChecking()
    
    def get_decision(self, price):
        score = self.checker.get_weighted_score(price)
        return score, ("롱 진입" if score >= 25 else "숏 진입" if score <= -25 else "대기")
