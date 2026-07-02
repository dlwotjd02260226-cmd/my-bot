import asyncio
from okx.websocket import OkxSocketClient

# 가상 계좌 클래스 (테스트용)
class PaperTradingEngine:
    def __init__(self, initial_balance=1000.0):
        self.balance = initial_balance  # 초기 가상 자산 (1000 USDT)
        self.position = 0.0             # 현재 보유 코인 수량
        print(f"가상 계좌 개설 완료! 초기 자산: {self.balance} USDT")

    def buy(self, price, amount):
        cost = price * amount
        if self.balance >= cost:
            self.balance -= cost
            self.position += amount
            print(f"✅ [매수] 가격: {price} | 수량: {amount} | 잔고: {self.balance:.2f} USDT")
        else:
            print("❌ [매수 실패] 잔액 부족")

    def sell(self, price, amount):
        if self.position >= amount:
            self.balance += price * amount
            self.position -= amount
            print(f"💰 [매도] 가격: {price} | 수량: {amount} | 잔고: {self.balance:.2f} USDT")
        else:
            print("❌ [매도 실패] 보유 수량 부족")

# 엔진 인스턴스 생성
engine = PaperTradingEngine()

# 메시지 핸들러에서 가상 매매 로직 수행
def handle_message(message):
    if "data" in message:
        data = message["data"][0]
        price = float(data["last"])
        print(f"현재가: {price}")
        
        # [테스트 로직] 가격이 60000보다 낮으면 무조건 매수 (예시)
        if price < 60000 and engine.balance > 100:
            engine.buy(price, 0.001)
        # [테스트 로직] 가격이 60100보다 높으면 무조건 매도
        elif price > 60100 and engine.position > 0:
            engine.sell(price, 0.001)

async def main():
    ws = OkxSocketClient()
    channels = [{"channel": "tickers", "instId": "BTC-USDT"}]
    ws.subscribe(channels, handle_message)
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
