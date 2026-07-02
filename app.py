import asyncio
import json
import logging
from okx.websocket import OkxSocketClient

# 로그 설정 (터미널에서 상태를 확인하기 위함)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class AutoTradeEngine:
    def __init__(self, initial_balance=1000.0):
        self.balance = initial_balance
        self.position = 0.0
        self.entry_price = 0.0
        logging.info(f"가상 매매 시작! 초기 자산: {self.balance} USDT")

    def buy(self, price, amount):
        cost = price * amount
        if self.balance >= cost:
            self.balance -= cost
            self.position += amount
            self.entry_price = price
            logging.info(f"✅ 매수 완료 | 가격: {price} | 잔고: {self.balance:.2f} USDT")
        
    def sell(self, price, amount):
        if self.position >= amount:
            self.balance += price * amount
            self.position -= amount
            profit = (price - self.entry_price) * amount
            logging.info(f"💰 매도 완료 | 가격: {price} | 수익: {profit:.2f} USDT | 잔고: {self.balance:.2f} USDT")

# 엔진 생성
engine = AutoTradeEngine()

def handle_message(message):
    if "data" in message:
        data = message["data"][0]
        price = float(data["last"])
        
        # [전략 로직] 
        # 가격이 60000 이하이면 매수, 60500 이상이면 매도 (간단한 예시)
        if price < 60000 and engine.balance > 100:
            engine.buy(price, 0.01)
        elif price > 60500 and engine.position > 0:
            engine.sell(price, 0.01)

async def main():
    # OKX Public 웹소켓 연결
    ws = OkxSocketClient()
    channels = [{"channel": "tickers", "instId": "BTC-USDT"}]
    
    ws.subscribe(channels, handle_message)
    logging.info("실시간 시세 수신 중...")
    
    # 무한 루프 유지
    await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("프로그램 종료")
