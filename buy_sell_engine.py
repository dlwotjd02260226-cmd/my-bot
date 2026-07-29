# buy&sell_engine.py
from Total_Score import TotalScoreCalculator
import time

class BuyAndSellEngine:
    def __init__(self):
        self.calculator = TotalScoreCalculator()
        
        # [진입 및 탈출 기준]
        self.long_threshold = 25
        self.short_threshold = -25
        self.smart_exit_threshold = 20 

        # [상태 관리 메모리]
        self.position = None
        self.avg_price = 0.0          
        self.position_size = 0.0      
        self.highest_price = 0.0
        self.lowest_price = float('inf')
        self.current_additions = 0    
        self.max_additions = 3        

        # [동적 리스크 관리 선 (고정 %가 아닌 실시간 계산으로 바뀜)]
        self.stop_loss = 0.0
        self.take_profit_1 = 0.0
        self.tp_1_hit = False

        self.cooldown_end_time = 0
        self.circuit_breaker = False

    def get_decision(self, price, market_data, event_alert=False):
        """
        [매개변수 설명]
        price: 현재 체결가
        market_data: 딕셔너리 형태 (ATR, 지지/저항선, 호가창 비율 등)
                     예: {'atr': 150, 'support': 60000, 'resistance': 62000, 'bid_ask_ratio': 1.5}
        """
        if self.circuit_breaker:
            return 0, "매매 중지 (서킷 브레이커 작동)"
        
        if event_alert:
            if self.position:
                self._clear_position(cooldown_sec=600)
                return 0, "🚨 이벤트 임박: 기존 포지션 긴급 청산 및 대기"
            return 0, "매매 대기 (이벤트 발생 임박)"

        if time.time() < self.cooldown_end_time:
            return 0, "대기 (쿨다운 중)"

        # ---------------------------------------------------------
        # 🛡️ 1. 포지션 관리 모드 (이미 물려있거나 수익 중일 때)
        # ---------------------------------------------------------
        if self.position is not None:
            live_score = self.calculator.get_total_score(price)
            # ATR 데이터를 넘겨주어 동적 트레일링 스탑에 활용
            action = self._manage_open_position(price, live_score, market_data['atr'])
            
            if action != "대기": 
                return live_score, action
            return live_score, f"{self.position} 유지 중 (평단: {self.avg_price:.2f})"

        # ---------------------------------------------------------
        # ⚔️ 2. 신규 진입 탐색 (깐깐한 3중 필터 적용)
        # ---------------------------------------------------------
        score = self.calculator.get_total_score(price)
        
        if score >= self.long_threshold:
            # [필터 1] 손익비(RR) 계산: 최소 1.5배 이상이어야 진입
            risk = price - market_data['support']
            reward = market_data['resistance'] - price
            if risk <= 0 or (reward / risk) < 1.5:
                return score, f"❌ 롱 진입 거절 (손익비 불량: {reward/risk if risk > 0 else 0:.2f})"
            
            # [필터 2] 호가창 불균형: 매도 벽이 너무 두꺼우면 거절 (비율이 0.8 미만)
            if market_data['bid_ask_ratio'] < 0.8:
                return score, "❌ 롱 진입 거절 (호가창 매도벽 두꺼움)"

            # 모두 통과하면 진입 (ATR 값을 넘겨서 고무줄 스탑로스 세팅)
            self._execute_entry("LONG", price, market_data['atr'])
            return score, "✅ 롱 1차 진입 (필터 통과)"
            
        elif score <= self.short_threshold:
            risk = market_data['resistance'] - price
            reward = price - market_data['support']
            if risk <= 0 or (reward / risk) < 1.5:
                return score, f"❌ 숏 진입 거절 (손익비 불량: {reward/risk if risk > 0 else 0:.2f})"
                
            if market_data['bid_ask_ratio'] > 1.2:
                return score, "❌ 숏 진입 거절 (호가창 매수벽 두꺼움)"

            self._execute_entry("SHORT", price, market_data['atr'])
            return score, "✅ 숏 1차 진입 (필터 통과)"
            
        return score, "대기"

    # =====================================================================
    # [내부 엔진] 
    # =====================================================================

    def _execute_entry(self, direction, price, atr):
        self.position = direction
        self.avg_price = price
        self.highest_price = price
        self.lowest_price = price
        self.current_additions = 0
        self.tp_1_hit = False
        
        # [필터 3] ATR(변동성)을 이용한 동적 스탑로스/익절 세팅
        # 장이 험하면(ATR이 크면) 손절폭이 커지고, 장이 조용하면 손절폭이 타이트해짐
        if direction == "LONG":
            self.stop_loss = price - (atr * 1.5)       # 손절: 평단가 - ATR의 1.5배
            self.take_profit_1 = price + (atr * 2.0)   # 익절: 평단가 + ATR의 2.0배
        elif direction == "SHORT":
            self.stop_loss = price + (atr * 1.5)
            self.take_profit_1 = price - (atr * 2.0)

    def _manage_open_position(self, current_price, live_score, atr):
        if current_price > self.highest_price: self.highest_price = current_price
        if current_price < self.lowest_price: self.lowest_price = current_price

        if self.position == "LONG":
            if live_score <= -self.smart_exit_threshold:
                self._clear_position(cooldown_sec=300)
                return "🚨 스마트 긴급 청산 (추세 반전)"

            # 물레방아 (분할 매수)
            if current_price < self.avg_price - atr and live_score >= self.long_threshold:
                if self.current_additions < self.max_additions:
                    self.avg_price = (self.avg_price + current_price) / 2 
                    self.current_additions += 1
                    return f"💧 롱 물레방아 가동 ({self.current_additions}/{self.max_additions})"
            
            # 1차 익절 및 본절 이동
            if current_price >= self.take_profit_1 and not self.tp_1_hit:
                self.tp_1_hit = True
                self.stop_loss = self.avg_price 
                return "💰 롱 1차 익절 (본절 스탑)"
                
            # 트레일링 스탑 (ATR 기반)
            if self.tp_1_hit:
                trailing_stop_price = self.highest_price - (atr * 1.0) 
                if current_price <= trailing_stop_price:
                    self._clear_position(cooldown_sec=120)
                    return "🚀 롱 동적 트레일링 스탑 (수익 실현)"

            # 기계적 손절
            if current_price <= self.stop_loss:
                self._clear_position(cooldown_sec=300)
                return "✂️ 롱 하드 스탑로스"

        elif self.position == "SHORT":
            if live_score >= self.smart_exit_threshold:
                self._clear_position(cooldown_sec=300)
                return "🚨 스마트 긴급 청산 (추세 반전)"

            if current_price > self.avg_price + atr and live_score <= self.short_threshold:
                if self.current_additions < self.max_additions:
                    self.avg_price = (self.avg_price + current_price) / 2 
                    self.current_additions += 1
                    return f"💧 숏 물레방아 가동 ({self.current_additions}/{self.max_additions})"
            
            if current_price <= self.take_profit_1 and not self.tp_1_hit:
                self.tp_1_hit = True
                self.stop_loss = self.avg_price
                return "💰 숏 1차 익절 (본절 스탑)"
                
            if self.tp_1_hit:
                trailing_stop_price = self.lowest_price + (atr * 1.0)
                if current_price >= trailing_stop_price:
                    self._clear_position(cooldown_sec=120)
                    return "🚀 숏 동적 트레일링 스탑 (수익 실현)"

            if current_price >= self.stop_loss:
                self._clear_position(cooldown_sec=300)
                return "✂️ 숏 하드 스탑로스"

        return "대기"

    def _clear_position(self, cooldown_sec=0):
        self.position = None
        self.avg_price = 0.0
        self.highest_price = 0.0
        self.lowest_price = float('inf')
        self.current_additions = 0
        self.tp_1_hit = False
        if cooldown_sec > 0:
            self.cooldown_end_time = time.time() + cooldown_sec
