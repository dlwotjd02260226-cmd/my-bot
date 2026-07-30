"""
buy_sell_engine.py — 진입/손절/익절/청산 자동 관리 엔진 (v3)

v3에서 추가된 것: app.py에서 "가상배팅(paper) / 실제배팅(live)" 버튼으로
실행 계층 자체를 실시간 전환할 수 있게 함.

핵심 안전 설계 (중요):
  - 이미 열려있는 포지션은 "진입할 때의 모드"에 그대로 고정됩니다.
    포지션 보유 중에 app.py에서 모드를 바꿔도 그 포지션의 관리/청산은
    원래 모드(같은 executor, 같은 계좌)로 계속 처리됩니다.
    -> 이렇게 안 하면: 가상으로 연 포지션을 실제 API로 청산 시도하거나,
       반대로 실제로 연 포지션을 가상으로만 "청산 처리"해버려서 거래소엔
       진짜 포지션이 그대로 남는 사고가 날 수 있습니다.
  - 포지션이 없을 때(대기 상태)만 모드 전환이 다음 신규 진입에 즉시 반영됩니다.
  - 모의매매(paper)와 실거래(live)는 계좌 잔고와 킬스위치/일일손실한도를
    완전히 분리해서 추적합니다. 가상 손실이 실거래 서킷브레이커를 건드리거나
    그 반대가 되는 일이 없게 하기 위함입니다.
  - live 모드가 선택됐는데 live_executor가 아직 연결 안 됐거나, 연결은 됐는데
    실제 주문 메서드가 아직 미구현(NotImplementedError)이면 진입 자체를
    안전하게 차단하고 이유를 알려줍니다 (죽지 않음).

원본/이전 버전 대비 유지된 것: 전략 트리거 조건과 순서(부분손절/VWAP초과익절/DCA/
1차익절/트레일링/하드스탑, 롱숏 대칭)는 전혀 안 건드렸습니다.

v4에서 보완 (요청하신 대로 연속손실 서킷브레이커 / 48시간 강제청산은 넣지 않았습니다):
  - NaN/가격 오류 가드: price/atr/spread/live_score 중 NaN이나 비정상값이 있으면
    (예전엔 NaN 비교가 조용히 False만 나와서 손절 조건이 무력화될 위험이 있었음)
    신규 진입은 보류, 기존 포지션은 안전한 값으로 대체하며 경고를 남김
  - 실행계층(executor)이 리턴한 체결가/체결수량을 그대로 믿지 않고 검증
    (음수·NaN·비정상적으로 큰 값이면 체결 실패로 처리)
  - 거래소 최소주문수량/소수점자리수 제한 대응 훅 추가 (min_order_size, size_precision)
  - 로그/상태파일 권한을 소유자 전용(0600)으로 제한, 로그 파일 용량 기반 회전 추가
  - 진입/DCA 로그에 그 순간의 market_data/live_score를 같이 남김 (나중에 메타 라벨링
    모델 학습 데이터로 재사용 가능)
  - 같은 프로세스 내 여러 스레드에서 동시 호출해도 안전하도록 락 추가
  - get_status()에 일일손실한도 초과 여부 필드 추가
"""
import json
import math
import os
import threading
import time
from typing import Dict, Any, Tuple, Optional

from order_executor import OrderExecutor, PaperOrderExecutor
from risk_guard import RiskGuard


def _is_bad_number(x) -> bool:
    """None이거나 NaN이거나 숫자가 아니면 True (가격/점수 등 필수 수치 검증용)"""
    if x is None:
        return True
    if isinstance(x, bool):
        return True
    if not isinstance(x, (int, float)):
        return True
    return math.isnan(x)


class BuyAndSellEngine:
    def __init__(self, initial_equity: float = 10000.0,
                 paper_executor: Optional[OrderExecutor] = None,
                 live_executor: Optional[OrderExecutor] = None,
                 risk_guard_paper: Optional[RiskGuard] = None,
                 risk_guard_live: Optional[RiskGuard] = None,
                 state_dir: str = ".",
                 log_path: Optional[str] = None,
                 max_position_value_mult: float = 3.0,
                 min_stop_distance_pct: float = 0.001,
                 auto_risk_pct: float = 0.01,
                 daily_loss_limit_pct: float = 0.05,
                 min_order_size: float = 0.0,
                 size_precision: Optional[int] = None,
                 max_holding_seconds: int = 43200,
                 log_max_bytes: int = 20_000_000):
        """
        min_order_size / size_precision: 🆕 거래소 최소주문수량·소수점 자릿수 제한 대응.
            LiveOrderExecutor를 실제로 연결하기 전에 본인 거래소 규칙에 맞게 채워두면,
            계산된 사이즈가 그 규칙에 안 맞을 때 진입을 스킵하고 이유를 알려줍니다.
        log_max_bytes: 🆕 trade_log.jsonl이 이 크기를 넘으면 자동으로 회전(백업)합니다.
        """
        self.taker_fee_pct = 0.0005

        # 🆕 [가상/실제 실행계층 분리]
        self.paper_executor = paper_executor or PaperOrderExecutor()
        self.live_executor = live_executor  # None = 아직 실거래 미연결 (app.py에서 나중에 넣어도 됨)

        # 🆕 [가상/실제 계좌 잔고 분리 추적]
        self.equity = {'paper': initial_equity, 'live': initial_equity}

        # 🆕 [가상/실제 리스크가드 분리, 킬스위치 파일은 공유(둘 다 동시 정지)]
        self.risk_guards = {
            'paper': risk_guard_paper or RiskGuard(state_dir=state_dir, daily_loss_limit_pct=daily_loss_limit_pct,
                                                    state_filename="risk_guard_state_paper.json"),
            'live': risk_guard_live or RiskGuard(state_dir=state_dir, daily_loss_limit_pct=daily_loss_limit_pct,
                                                  state_filename="risk_guard_state_live.json"),
        }
        for mode in ('paper', 'live'):
            self.risk_guards[mode].set_day_start_equity(self.equity[mode])

        self.log_path = log_path or os.path.join(state_dir, "trade_log.jsonl")
        self.log_max_bytes = log_max_bytes

        self.max_position_value_mult = max_position_value_mult
        self.min_stop_distance_pct = min_stop_distance_pct
        self.auto_risk_pct = auto_risk_pct
        self.min_order_size = min_order_size
        self.size_precision = size_precision

        self._lock = threading.RLock()  # 🆕 스레드 안전 (같은 프로세스 내에서만 보호됨)

        # ⚙️ [포지션 및 상태 메모리]
        self.position: Optional[str] = None
        self.active_mode: Optional[str] = None  # 🆕 이 포지션이 'paper'/'live' 중 어디로 열렸는지 고정
        self.avg_price: float = 0.0
        self.position_size: float = 0.0
        self.entry_time: float = 0.0
        self.running_mode_start_time: float = 0.0

        self.highest_price: float = 0.0
        self.lowest_price: float = float('inf')

        self.current_additions = 0
        self.stop_loss: float = 0.0
        self.take_profit_1: float = 0.0
        self.max_dollar_risk: float = 0.0

        self.tp_1_hit: bool = False
        self.partial_stop_hit: bool = False
        self.escape_mode: bool = False
        self.cooldown_end_time: Dict[str, float] = {'paper': 0.0, 'live': 0.0}  # 모드별 분리
        self.max_holding_seconds: int = max_holding_seconds

    # =====================================================================
    # 🆕 가상/실제 실행계층 선택
    # =====================================================================
    def _get_executor(self, mode: str) -> Tuple[Optional[OrderExecutor], Optional[str]]:
        if mode == 'live':
            if self.live_executor is None:
                return None, "🚨 실제배팅 모드가 선택됐지만 live_executor가 아직 연결되지 않았습니다."
            return self.live_executor, None
        return self.paper_executor, None

    def _safe_execute(self, executor: OrderExecutor, method: str, *args, **kwargs):
        """실행계층 호출을 감싸서, live_executor가 아직 미구현(NotImplementedError)이거나
        거래소 쪽에서 예외가 나도 엔진 전체가 죽지 않고 안전하게 실패 처리되게 함."""
        try:
            return getattr(executor, method)(*args, **kwargs), None
        except NotImplementedError as e:
            return None, f"🚨 실거래 주문 함수가 아직 구현되지 않았습니다: {e}"
        except Exception as e:
            # 🆕 예외 메시지를 길이 제한 — 거래소 SDK 예외에 요청/응답 원문이 통째로 담겨
            # 민감정보가 로그에 그대로 남는 걸 방지 (완전한 해결책은 아니니 LiveOrderExecutor
            # 구현 시 가능하면 더 구체적으로 예외를 잡아서 필요한 내용만 전달하는 걸 권장)
            safe_msg = str(e)[:200]
            return None, f"🚨 주문 실행 중 오류: {safe_msg}"

    def _validate_order_result(self, order, requested_size: float, requested_price: float) -> Tuple[bool, str]:
        """🆕 executor가 리턴한 체결 결과를 그대로 믿지 않고 검증. 버그가 있는 LiveOrderExecutor
        구현체가 이상한 값을 리턴해도 그게 그대로 포지션/계좌에 반영되지 않도록 막는 안전장치."""
        if order is None or not order.get("filled"):
            return False, "체결 실패"
        fill_price = order.get("avg_fill_price")
        fill_size = order.get("filled_size")
        if _is_bad_number(fill_price) or fill_price <= 0:
            return False, f"체결가 값이 비정상적입니다: {fill_price}"
        if _is_bad_number(fill_size) or fill_size <= 0:
            return False, f"체결수량 값이 비정상적입니다: {fill_size}"
        if requested_size > 0 and fill_size > requested_size * 1.01:
            return False, f"체결수량({fill_size})이 요청수량({requested_size})보다 비정상적으로 많습니다"
        if requested_price > 0 and abs(fill_price - requested_price) / requested_price > 0.05:
            print(f"⚠️ 체결가({fill_price})가 요청가({requested_price}) 대비 5% 이상 벗어났습니다 - 슬리피지 확인 필요")
        return True, ""

    # =====================================================================
    # 🆕 수동/자동 모드(전략 파라미터) 우선순위 해석
    # =====================================================================
    def _resolve_trading_params(self, market_data: Dict[str, Any], ui_settings: Dict[str, Any]) -> Dict[str, Any]:
        mode = ui_settings.get('mode', 'auto')
        regime = market_data.get('market_regime', 'RANGING')

        if mode == 'manual':
            sl_multiplier = ui_settings.get('sl_multiplier', 1.5)
            tp_multiplier = sl_multiplier * ui_settings.get('rr_ratio', 2.0)
            risk_pct = ui_settings.get('risk_pct', self.auto_risk_pct)
            allow_dca = ui_settings.get('allow_dca', False)
            max_dca_count = ui_settings.get('max_dca_count', 3)
        else:
            mode = 'auto'
            if regime == 'TRENDING':
                sl_multiplier, tp_multiplier = 1.0, 3.0
            else:
                sl_multiplier, tp_multiplier = 2.0, 1.0
            risk_pct = self.auto_risk_pct
            allow_dca = market_data.get('allow_dca', False)
            max_dca_count = market_data.get('max_dca_count', 3)

        # 🛡️ 추세장 물타기 금지는 모드와 무관한 안전 규칙 (수동으로도 못 끔)
        if regime == 'TRENDING':
            allow_dca = False

        return {
            'mode': mode, 'sl_multiplier': sl_multiplier, 'tp_multiplier': tp_multiplier,
            'risk_pct': risk_pct, 'allow_dca': allow_dca, 'max_dca_count': max_dca_count,
        }

    def _log_trade(self, event: str, **kwargs):
        entry = {"ts": time.time(), "event": event, **kwargs}
        try:
            self._rotate_log_if_needed()
            with open(self.log_path, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            try:
                os.chmod(self.log_path, 0o600)  # 🆕 소유자 전용 권한 (금융 데이터)
            except OSError:
                pass  # 일부 OS/파일시스템 미지원 - 무시해도 치명적이지 않음
        except OSError as e:
            print(f"⚠️ 거래 로그 기록 실패: {e}")

    def _rotate_log_if_needed(self):
        """🆕 로그 파일이 너무 커지면(기본 20MB) 백업 파일로 옮기고 새로 시작"""
        try:
            if os.path.exists(self.log_path) and os.path.getsize(self.log_path) >= self.log_max_bytes:
                backup_path = f"{self.log_path}.{int(time.time())}.bak"
                os.replace(self.log_path, backup_path)
        except OSError as e:
            print(f"⚠️ 로그 회전 실패(무시하고 계속 기록 시도): {e}")

    # =====================================================================
    # 메인 진입점 — 🆕 스레드 락 + 가격/점수 유효성 검증 후 실제 로직(_get_decision_impl)으로 위임
    # =====================================================================
    def get_decision(self, price: float, live_score: float,
                      market_data: Dict[str, Any], ui_settings: Dict[str, Any]) -> Tuple[float, str]:
        # 🆕 [버그 수정] price/live_score가 없거나 NaN이거나 0 이하이면 여기서 바로 차단.
        # (NaN 비교는 파이썬에서 항상 False가 나와서, 이 검증이 없으면 손절 조건이
        #  조용히 무력화될 수 있음 — 신규진입 뿐 아니라 기존 포지션 관리도 막아야 안전함)
        if _is_bad_number(price) or price <= 0:
            return 0, f"대기 (가격 데이터 오류: {price})"
        if _is_bad_number(live_score):
            return 0, f"대기 (점수 데이터 오류: {live_score})"

        with self._lock:  # 🆕 같은 프로세스 내 동시 호출로부터 상태 보호
            return self._get_decision_impl(price, live_score, market_data, ui_settings)

    def _get_decision_impl(self, price: float, live_score: float,
                            market_data: Dict[str, Any], ui_settings: Dict[str, Any]) -> Tuple[float, str]:
        market_data = market_data or {}
        ui_settings = ui_settings or {}

        atr = market_data.get('atr')
        current_spread = market_data.get('spread')

        # 🆕 None뿐 아니라 NaN도 "데이터 없음"과 동일하게 취급
        data_incomplete = _is_bad_number(atr) or _is_bad_number(current_spread)
        if data_incomplete:
            if self.position is None:
                return 0, "대기 (market_data 불완전: atr/spread 없음 - 신규 진입 보류)"
            atr = atr if not _is_bad_number(atr) else max(self.avg_price * 0.005, 1e-9)
            current_spread = current_spread if not _is_bad_number(current_spread) else self.avg_price * 0.0005
            print("⚠️ market_data에 atr/spread가 없어 임시 대체값으로 기존 포지션을 관리합니다.")

        if current_spread > (atr * 0.1):
            return 0, "대기 (호가 공백 큼 - 슬리피지 보호)"

        params = self._resolve_trading_params(market_data, ui_settings)
        forced_action = ui_settings.get('forced_action') if params['mode'] == 'manual' else None

        # -----------------------------------------------------------
        # 🛡️ 기존 포지션 관리 — 진입 당시 고정된 self.active_mode를 계속 사용 (모드 전환 무시)
        # -----------------------------------------------------------
        if self.position is not None:
            mode = self.active_mode
            executor, err = self._get_executor(mode)
            if executor is None:
                # 이 상황은 이론상 거의 안 생기지만(진입 때 이미 확인했으므로), 방어적으로 처리
                return live_score, f"⚠️ 포지션 관리 중 실행계층 문제: {err}"

            if forced_action == 'CLOSE':
                self._clear_position(price, executor, mode, reason="수동 강제청산", cooldown_sec=60)
                return live_score, "🖐️ 수동 강제 청산 완료"

            action = self._manage_open_position(price, live_score, market_data, atr, current_spread,
                                                 params, executor, mode)
            if action != "대기":
                return live_score, action

            status = (f"[{mode.upper()}] {self.position} 진행중 (평단: {self.avg_price:.2f}, "
                      f"🛑 SL: {self.stop_loss:.2f}, 전략모드: {params['mode']})")
            if self.escape_mode:
                status += " ⚠️ [Escape Mode]"
            elif self.tp_1_hit:
                status += " 🏃 [Running Mode]"
            return live_score, status

        # -----------------------------------------------------------
        # 신규 진입: 지금 이 순간의 trading_mode(paper/live)를 새로 확인
        # -----------------------------------------------------------
        trading_mode = ui_settings.get('trading_mode', 'paper')
        if trading_mode not in ('paper', 'live'):
            trading_mode = 'paper'

        # 쿨다운도 모드별로 분리 체크 (live 청산 쿨다운이 paper 신규진입까지 막지 않게)
        if time.time() < self.cooldown_end_time[trading_mode]:
            return 0, f"대기 ([{trading_mode.upper()}] 쿨다운 작동 중)"

        executor, err = self._get_executor(trading_mode)
        if executor is None:
            return 0, err

        can_enter, block_reason = self.risk_guards[trading_mode].can_open_new_position()
        if not can_enter:
            return 0, f"[{trading_mode.upper()}] {block_reason}"

        entry_signal = forced_action if forced_action in ("LONG", "SHORT") else market_data.get('entry_signal')
        if entry_signal in ("LONG", "SHORT"):
            ok, reason = self._execute_entry(entry_signal, price, atr, current_spread, market_data,
                                              params, executor, trading_mode)
            if not ok:
                return live_score, f"⚠️ 진입 실패: {reason}"
            return live_score, (f"✅ [{trading_mode.upper()}] {entry_signal} 진입 완료 "
                                 f"(수량: {self.position_size:.6f}, 전략모드: {params['mode']})")

        return live_score, "매매 대기중"

    # =====================================================================
    # 신규 진입 실행
    # =====================================================================
    def _execute_entry(self, direction: str, price: float, atr: float, spread: float,
                        market_data: Dict[str, Any], params: Dict[str, Any],
                        executor: OrderExecutor, mode: str) -> Tuple[bool, str]:
        equity = self.equity[mode]
        risk_pct = params['risk_pct']
        self.max_dollar_risk = equity * risk_pct

        stop_distance = atr * params['sl_multiplier']
        profit_distance = atr * params['tp_multiplier']

        min_stop_distance = price * self.min_stop_distance_pct
        stop_distance = max(stop_distance, min_stop_distance)

        stop_loss = price - stop_distance if direction == "LONG" else price + stop_distance
        take_profit_1 = price + profit_distance if direction == "LONG" else price - profit_distance

        raw_size = self.max_dollar_risk / stop_distance
        max_position_value = equity * self.max_position_value_mult
        size = min(raw_size, max_position_value / price)
        if size < raw_size:
            print(f"⚠️ 계산된 포지션 크기가 상한을 초과해서 축소 적용됨 ({raw_size:.6f} -> {size:.6f})")

        # 🆕 거래소 소수점 자릿수/최소주문수량 규칙 적용 (본인 거래소 규칙에 맞게 생성자에서 설정)
        if self.size_precision is not None:
            size = round(size, self.size_precision)
        if size < self.min_order_size:
            reason = f"계산된 수량({size})이 최소주문수량({self.min_order_size})보다 작습니다"
            self._log_trade("entry_skipped", mode=mode, direction=direction, price=price, reason=reason)
            return False, reason

        order, err = self._safe_execute(executor, "place_order", direction, size, price)
        ok, verr = self._validate_order_result(order, size, price)  # 🆕 체결 결과 검증
        if not ok:
            self._log_trade("entry_failed", mode=mode, direction=direction, price=price, size=size,
                             error=err or verr)
            return False, err or verr

        self.position = direction
        self.active_mode = mode  # 이 포지션을 어떤 모드로 관리할지 고정
        self.avg_price = order.get("avg_fill_price", price)
        self.position_size = order.get("filled_size", size)
        self.highest_price = self.avg_price
        self.lowest_price = self.avg_price
        self.entry_time = time.time()

        self.current_additions = 0
        self.tp_1_hit = False
        self.partial_stop_hit = False
        self.escape_mode = False
        self.stop_loss = stop_loss
        self.take_profit_1 = take_profit_1

        # 🆕 나중에 메타 라벨링 모델 학습 데이터로 쓸 수 있도록 그 순간의 시장 컨텍스트를 같이 남김
        market_snapshot = {k: market_data.get(k) for k in
                            ('atr', 'spread', 'market_regime', 'vwap', 'model_confidence') if k in market_data}
        self._log_trade("entry", mode=mode, direction=direction, price=self.avg_price, size=self.position_size,
                         stop_loss=self.stop_loss, take_profit_1=self.take_profit_1,
                         strategy_mode=params['mode'], risk_pct=risk_pct,
                         market_snapshot=market_snapshot)
        return True, ""

    def _get_true_breakeven_price(self, current_price: float, current_spread: float) -> float:
        dynamic_slippage_pct = (current_spread / self.avg_price)
        total_fee_cost = (self.taker_fee_pct * 2) + dynamic_slippage_pct + 0.0005
        if self.position == "LONG":
            return self.avg_price * (1 + total_fee_cost)
        else:
            return self.avg_price * (1 - total_fee_cost)

    # =====================================================================
    # 기존 포지션 관리 (전략 트리거 조건/순서는 원본과 동일)
    # =====================================================================
    def _manage_open_position(self, current_price: float, live_score: float, market_data: Dict[str, Any],
                               atr: float, current_spread: float, params: Dict[str, Any],
                               executor: OrderExecutor, mode: str) -> str:
        vwap = market_data.get('vwap', current_price)

        if current_price > self.highest_price:
            self.highest_price = current_price
        if current_price < self.lowest_price:
            self.lowest_price = current_price

        if market_data.get('urgent_exit_signal', False):
            self._clear_position(current_price, executor, mode, reason="토탈스코어 긴급경고", cooldown_sec=300)
            return "🚨 토탈 스코어 경고: 즉각 시장가 대피 엑시트!"

        if not self.escape_mode and not self.tp_1_hit and (time.time() - self.entry_time) > self.max_holding_seconds:
            self.escape_mode = True
            self.take_profit_1 = self._get_true_breakeven_price(current_price, current_spread)
            return "⚠️ 시간 초과: 기회비용 확보를 위해 타겟을 본절가로 하향 (Escape Mode)"

        allow_dca = params['allow_dca']
        max_dca_count = params['max_dca_count']

        if self.position == "LONG":
            if live_score < -10 and not self.partial_stop_hit and not self.tp_1_hit:
                self.partial_stop_hit = True
                cut_size = self.position_size * 0.3
                self._clear_position(current_price, executor, mode,
                                      reason=f"스코어하락({live_score:.1f}) 부분손절", partial_size=cut_size)
                return f"🛡️ 리스크 사전 축소: 스코어 하락({live_score:.1f})으로 30% 부분 손절 진행"

            if self.tp_1_hit and ((current_price - vwap) / vwap) > 0.03:
                self._clear_position(current_price, executor, mode, reason="VWAP 초과슈팅 긴급익절", cooldown_sec=1800)
                return "🚀 초과 슈팅(VWAP 괴리) 감지: 묻지도 따지지도 않고 전량 익절!"

            if (allow_dca and not self.escape_mode and not self.tp_1_hit
                    and current_price < (self.avg_price - atr) and self.current_additions < max_dca_count):
                msg = self._try_dca("LONG", current_price, atr, executor, mode)
                if msg:
                    return msg

            if current_price >= self.take_profit_1:
                if self.escape_mode:
                    self._clear_position(current_price, executor, mode, reason="Escape Mode 자금회수", cooldown_sec=60)
                    return "⏰ 자금 회수 엑시트 완료 (본절+수수료 챙김)"
                elif not self.tp_1_hit:
                    self.tp_1_hit = True
                    self.running_mode_start_time = time.time()
                    cut_size = self.position_size * 0.5
                    self._clear_position(current_price, executor, mode, reason="1차 타겟 익절", partial_size=cut_size)
                    true_be = self._get_true_breakeven_price(current_price, current_spread)
                    self.stop_loss = max(self.stop_loss, true_be)
                    return f"💰 1차 타겟 익절! 방어선(BE) {self.stop_loss:.2f}로 상향 (손해 불가)"

            if self.tp_1_hit:
                hours_in_running = (time.time() - self.running_mode_start_time) / 3600.0
                dynamic_atr_multiplier = max(0.5, 1.5 - (hours_in_running * 0.1))
                trailing_stop = self.highest_price - (atr * dynamic_atr_multiplier)
                if trailing_stop > self.stop_loss:
                    self.stop_loss = trailing_stop

            if current_price <= self.stop_loss:
                reason = "추적 엑시트" if self.tp_1_hit else "하드 스탑로스"
                self._clear_position(current_price, executor, mode, reason=reason,
                                      cooldown_sec=120 if self.tp_1_hit else 300)
                return f"✂️ 롱 포지션 청산 ({reason})"

        elif self.position == "SHORT":
            if live_score > 10 and not self.partial_stop_hit and not self.tp_1_hit:
                self.partial_stop_hit = True
                cut_size = self.position_size * 0.3
                self._clear_position(current_price, executor, mode,
                                      reason=f"스코어상승({live_score:.1f}) 부분손절", partial_size=cut_size)
                return f"🛡️ 리스크 사전 축소: 스코어 상승({live_score:.1f})으로 30% 부분 손절 진행"

            if self.tp_1_hit and ((vwap - current_price) / vwap) > 0.03:
                self._clear_position(current_price, executor, mode, reason="VWAP 초과하락 긴급익절", cooldown_sec=1800)
                return "🚀 하방 덤핑(VWAP 괴리) 감지: 시장가 전량 익절!"

            if (allow_dca and not self.escape_mode and not self.tp_1_hit
                    and current_price > (self.avg_price + atr) and self.current_additions < max_dca_count):
                msg = self._try_dca("SHORT", current_price, atr, executor, mode)
                if msg:
                    return msg

            if current_price <= self.take_profit_1:
                if self.escape_mode:
                    self._clear_position(current_price, executor, mode, reason="Escape Mode 자금회수", cooldown_sec=60)
                    return "⏰ 자금 회수 엑시트 완료 (본절+수수료 챙김)"
                elif not self.tp_1_hit:
                    self.tp_1_hit = True
                    self.running_mode_start_time = time.time()
                    cut_size = self.position_size * 0.5
                    self._clear_position(current_price, executor, mode, reason="숏 1차 타겟 익절", partial_size=cut_size)
                    true_be = self._get_true_breakeven_price(current_price, current_spread)
                    self.stop_loss = min(self.stop_loss, true_be)
                    return f"💰 숏 1차 타겟 익절! 방어선(BE) {self.stop_loss:.2f}로 하향"

            if self.tp_1_hit:
                hours_in_running = (time.time() - self.running_mode_start_time) / 3600.0
                dynamic_atr_multiplier = max(0.5, 1.5 - (hours_in_running * 0.1))
                trailing_stop = self.lowest_price + (atr * dynamic_atr_multiplier)
                if trailing_stop < self.stop_loss:
                    self.stop_loss = trailing_stop

            if current_price >= self.stop_loss:
                reason = "추적 엑시트" if self.tp_1_hit else "하드 스탑로스"
                self._clear_position(current_price, executor, mode, reason=reason,
                                      cooldown_sec=120 if self.tp_1_hit else 300)
                return f"✂️ 숏 포지션 청산 ({reason})"

        return "대기"

    # =====================================================================
    # 물타기(DCA)
    # =====================================================================
    def _try_dca(self, direction: str, current_price: float, atr: float,
                 executor: OrderExecutor, mode: str) -> Optional[str]:
        new_size = self.position_size * 0.5
        new_avg = ((self.avg_price * self.position_size) + (current_price * new_size)) / (self.position_size + new_size)
        new_total_size = self.position_size + new_size
        new_stop = (new_avg - (self.max_dollar_risk / new_total_size) if direction == "LONG"
                    else new_avg + (self.max_dollar_risk / new_total_size))

        min_gap = current_price * self.min_stop_distance_pct
        invalid = (direction == "LONG" and new_stop >= current_price - min_gap) or \
                  (direction == "SHORT" and new_stop <= current_price + min_gap)
        if invalid:
            print("⚠️ 물타기 시도했으나 계산된 손절가가 현재가와 너무 가까워(또는 역전) 이번 물타기는 건너뜀")
            return None

        order, err = self._safe_execute(executor, "place_order", direction, new_size, current_price)
        ok, verr = self._validate_order_result(order, new_size, current_price)  # 🆕 체결 결과 검증
        if not ok:
            self._log_trade("dca_failed", mode=mode, direction=direction, price=current_price,
                             size=new_size, error=err or verr)
            return None

        filled_size = order.get("filled_size", new_size)
        fill_price = order.get("avg_fill_price", current_price)
        self.avg_price = ((self.avg_price * self.position_size) + (fill_price * filled_size)) / (self.position_size + filled_size)
        self.position_size += filled_size
        self.current_additions += 1
        self.stop_loss = (self.avg_price - (self.max_dollar_risk / self.position_size) if direction == "LONG"
                           else self.avg_price + (self.max_dollar_risk / self.position_size))

        self._log_trade("dca_add", mode=mode, direction=direction, price=current_price, size=filled_size,
                         new_avg=self.avg_price, new_stop=self.stop_loss)
        return f"💧 기계적 물량 추가 - 새 평단: {self.avg_price:.2f} (스탑로스 보정 완료)"

    # =====================================================================
    # 청산 (전량/부분)
    # =====================================================================
    def _clear_position(self, exit_price: float, executor: OrderExecutor, mode: str,
                         reason: str = "", cooldown_sec: int = 0,
                         partial_size: Optional[float] = None) -> Optional[float]:
        close_size = partial_size if partial_size is not None else self.position_size
        close_size = min(close_size, self.position_size)  # 🆕 방어적 clamp (요청 수량이 보유량을 못 넘게)
        direction = self.position
        entry_price = self.avg_price

        order, err = self._safe_execute(executor, "close_position", direction, close_size, exit_price)
        ok, verr = self._validate_order_result(order, close_size, exit_price)  # 🆕 체결 결과 검증
        if not ok:
            # 청산 주문 자체가 실패/비정상이면 포지션을 함부로 지우지 않음(실제로 아직 열려있을 수 있으므로)
            self._log_trade("exit_failed", mode=mode, direction=direction, price=exit_price,
                             size=close_size, reason=reason, error=err or verr)
            print(f"🚨 청산 주문 실패/검증실패 — 포지션을 그대로 유지합니다: {err or verr}")
            return None

        filled_price = order.get("avg_fill_price", exit_price)
        filled_size = order.get("filled_size", close_size)

        gross = (filled_price - entry_price) * filled_size if direction == "LONG" else (entry_price - filled_price) * filled_size
        fees = (entry_price + filled_price) * filled_size * self.taker_fee_pct
        pnl = gross - fees

        self.equity[mode] += pnl  # 🆕 해당 모드(paper/live)의 계좌에만 반영
        self.risk_guards[mode].record_realized_pnl(pnl)

        is_full_close = partial_size is None or filled_size >= self.position_size - 1e-12
        self._log_trade("exit" if is_full_close else "partial_exit",
                         mode=mode, direction=direction, entry_price=entry_price, exit_price=filled_price,
                         size=filled_size, pnl=pnl, reason=reason, account_equity=self.equity[mode])

        if is_full_close:
            self._reset_position_state()
            if cooldown_sec > 0:
                self.cooldown_end_time[mode] = time.time() + cooldown_sec
        else:
            self.position_size -= filled_size

        return pnl

    def _reset_position_state(self):
        self.position = None
        self.active_mode = None
        self.avg_price = 0.0
        self.position_size = 0.0
        self.highest_price = 0.0
        self.lowest_price = float('inf')
        self.current_additions = 0
        self.tp_1_hit = False
        self.partial_stop_hit = False
        self.escape_mode = False

    # =====================================================================
    # 🆕 app.py 대시보드 표시용 — 읽기 전용, 아무 상태도 바꾸지 않음
    # =====================================================================
    def get_status(self, current_price: Optional[float] = None) -> Dict[str, Any]:
        unrealized_pnl = None
        if self.position is not None and current_price is not None:
            if self.position == "LONG":
                unrealized_pnl = (current_price - self.avg_price) * self.position_size
            else:
                unrealized_pnl = (self.avg_price - current_price) * self.position_size

        return {
            "position": self.position,
            "active_mode": self.active_mode,
            "avg_price": self.avg_price,
            "position_size": self.position_size,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "tp_1_hit": self.tp_1_hit,
            "escape_mode": self.escape_mode,
            "unrealized_pnl": unrealized_pnl,
            "paper_equity": self.equity['paper'],
            "live_equity": self.equity['live'],
            "kill_switch_on": self.risk_guards['paper'].is_kill_switch_on(),  # 킬스위치는 공유 파일
            "paper_daily_pnl": self.risk_guards['paper'].today_realized_pnl,
            "live_daily_pnl": self.risk_guards['live'].today_realized_pnl,
            "paper_daily_loss_limit_hit": self.risk_guards['paper'].is_daily_loss_limit_hit(),  # 🆕
            "live_daily_loss_limit_hit": self.risk_guards['live'].is_daily_loss_limit_hit(),  # 🆕
        }
