"""
order_executor.py — 주문 실행 계층

의사결정(BuyAndSellEngine이 "무엇을 할지" 정하는 것)과
실행("실제로 어떻게 주문을 넣을지")을 분리했습니다.

- PaperOrderExecutor: 실제 주문 없이 요청대로 체결됐다고 가정하는 모의매매용.
  엔진의 기본값입니다. slippage_pct를 0보다 크게 주면 매수는 불리하게 비싸게,
  매도는 불리하게 싸게 체결되는 것까지 흉내내서 더 현실적인 모의매매 결과를 볼 수 있습니다
  (기본 0 = 이전과 동일하게 완벽 체결).

- LiveOrderExecutor: 실거래소 연동 자리입니다. 일부러 미구현 상태로 남겨뒀고
  place_order/close_position을 호출하면 명시적으로 에러가 납니다.
  본인이 쓰는 거래소 SDK로 두 메서드를 직접 채워넣기 전까지는 절대 실주문이 나가지 않습니다.

  🔒 보안 주의사항 (직접 구현하실 때 꼭 확인하세요):
  - 거래소 SDK가 던지는 예외의 문자열 표현(str(e))에 요청/응답 원문이 통째로 들어있는
    경우가 있고, 그 안에 서명값이나 계정 식별정보가 포함될 수 있습니다. 이 예외를 그대로
    로그 파일에 남기지 말고, 필요한 부분만 뽑아서 남기는 걸 권장합니다.
  - API 키/시크릿은 이 파일이나 다른 소스 파일에 절대 하드코딩하지 말고 환경변수나
    별도 설정파일(.gitignore 처리)로 분리하세요.
"""
import time
from abc import ABC, abstractmethod


class OrderExecutor(ABC):
    @abstractmethod
    def place_order(self, direction, size, price, order_type="market"):
        """
        신규 진입 주문. direction: 'LONG' 또는 'SHORT'.
        반환 형식(딕셔너리)은 반드시 아래 키를 포함해야 함:
          {"filled": bool, "avg_fill_price": float, "filled_size": float, "order_id": str}
        """
        raise NotImplementedError

    @abstractmethod
    def close_position(self, direction, size, price):
        """포지션 청산(전량/부분) 주문. 반환 형식은 place_order와 동일."""
        raise NotImplementedError


class PaperOrderExecutor(OrderExecutor):
    """모의매매: 기본은 요청 가격대로 100% 체결. slippage_pct를 주면 불리한 방향으로
    살짝 미끄러진 가격에 체결된 것처럼 시뮬레이션함 (실제 매매와 더 비슷한 결과를 보기 위함)."""

    def __init__(self, slippage_pct: float = 0.0):
        if slippage_pct < 0:
            raise ValueError("slippage_pct는 0 이상이어야 합니다")
        self.slippage_pct = slippage_pct

    def _apply_slippage(self, price, direction, is_entry):
        if self.slippage_pct <= 0:
            return price
        # 매수(LONG 진입 또는 SHORT 청산)는 더 비싸게, 매도(LONG 청산 또는 SHORT 진입)는 더 싸게
        is_buy_action = (direction == "LONG") == is_entry
        factor = (1 + self.slippage_pct) if is_buy_action else (1 - self.slippage_pct)
        return price * factor

    def place_order(self, direction, size, price, order_type="market"):
        fill_price = self._apply_slippage(price, direction, is_entry=True)
        return {"filled": True, "avg_fill_price": fill_price, "filled_size": size,
                "order_id": f"paper-{time.time():.6f}"}

    def close_position(self, direction, size, price):
        fill_price = self._apply_slippage(price, direction, is_entry=False)
        return {"filled": True, "avg_fill_price": fill_price, "filled_size": size,
                "order_id": f"paper-{time.time():.6f}"}


class LiveOrderExecutor(OrderExecutor):
    """
    🚨 실거래용 자리 — 아래 두 메서드는 반드시 본인 거래소 SDK 호출로 채워야 합니다.
    지금 상태로는 호출하면 항상 NotImplementedError가 나서 절대 실주문이 나가지 않습니다.

    채워넣는 예시 형태(실제 동작 검증은 안 됐으니 참고만 하세요):

        def place_order(self, direction, size, price, order_type="market"):
            side = "buy" if direction == "LONG" else "sell"
            order = self.exchange_client.create_order(
                symbol=self.symbol, type=order_type, side=side, amount=size
            )
            return {
                "filled": order["status"] == "closed",
                "avg_fill_price": order.get("average", price),
                "filled_size": order.get("filled", size),
                "order_id": order["id"],
            }
    """

    def __init__(self, exchange_client=None, symbol=None):
        self.exchange_client = exchange_client
        self.symbol = symbol

    def place_order(self, direction, size, price, order_type="market"):
        raise NotImplementedError(
            "실거래 진입 주문이 아직 연결되지 않았습니다. "
            "본인 거래소 SDK로 LiveOrderExecutor.place_order를 구현한 뒤 사용하세요."
        )

    def close_position(self, direction, size, price):
        raise NotImplementedError(
            "실거래 청산 주문이 아직 연결되지 않았습니다. "
            "본인 거래소 SDK로 LiveOrderExecutor.close_position을 구현한 뒤 사용하세요."
        )
