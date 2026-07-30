"""
risk_guard.py — 계좌 레벨 안전장치 (킬스위치 + 일일 손실 서킷브레이커)

왜 엔진 클래스 안에 안 넣고 따로 뺐는지:
  - 나중에 매매기법/엔진 인스턴스가 여러 개로 늘어나도 "계좌 전체 기준" 안전장치는
    하나로 공유돼야 하기 때문 (엔진 A는 괜찮은데 B가 손실 냈다고 A까지 막혀야 함)
  - 프로세스가 재시작돼도(서버 재부팅, 배포 등) 오늘 손실 누적치가 사라지면 안 되므로
    파일에 상태를 저장함

v2에서 보완:
  - 상태 저장을 원자적 쓰기(임시파일 -> os.replace)로 바꿔서, 쓰는 도중 프로세스가
    죽어도 기존 파일이 손상되지 않게 함 (손상되면 오늘 손실 누적치가 조용히 0으로
    리셋되면서 서킷브레이커가 무력화될 수 있었음)
  - 상태 파일 권한을 소유자만 읽기/쓰기 가능하게 제한 (금융 정보이므로)
  - 같은 프로세스 내 여러 스레드에서 동시에 호출해도 안전하도록 락 추가
    (단, 여러 '프로세스'가 같은 상태파일을 동시에 쓰는 경우까지는 보호하지 않음 —
     그런 구조라면 OS 파일 잠금이 추가로 필요하니 알려주세요)
"""
import json
import os
import threading
from datetime import date


class RiskGuard:
    def __init__(self, state_dir=".", daily_loss_limit_pct=0.05, kill_switch_filename="KILL_SWITCH",
                 state_filename="risk_guard_state.json"):
        """
        daily_loss_limit_pct: 하루 시작 자본 대비 이 비율만큼 손실나면 신규 진입 차단 (기본 5%)
        kill_switch_filename: 이 이름의 파일이 존재하기만 하면 즉시 신규 진입 차단
                               (사람이 그냥 빈 파일 하나 만들면 되니 제일 빠른 비상정지 수단)
        state_filename: 오늘 실현손익 등을 저장할 파일명. 모의매매/실거래를 서로 다른 파일로
                        분리 추적하고 싶을 때(권장) 서로 다른 값을 넣어서 인스턴스를 2개 만들면 됨.
        """
        if not (0 < daily_loss_limit_pct <= 1.0):
            raise ValueError(f"daily_loss_limit_pct는 0과 1 사이여야 합니다 (받은 값: {daily_loss_limit_pct})")

        self.state_dir = state_dir
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.kill_switch_path = os.path.join(state_dir, kill_switch_filename)
        self.state_path = os.path.join(state_dir, state_filename)
        self.today_realized_pnl = 0.0
        self.day_start_equity = None
        self._today = None
        self._lock = threading.RLock()  # 🆕 같은 프로세스 내 스레드 안전
        self._load_state()

    def _load_state(self):
        with self._lock:
            today = str(date.today())
            if os.path.exists(self.state_path):
                try:
                    with open(self.state_path, "r") as f:
                        data = json.load(f)
                    if data.get("date") == today:
                        self.today_realized_pnl = data.get("today_realized_pnl", 0.0)
                        self.day_start_equity = data.get("day_start_equity")
                        self._today = today
                        return
                except (json.JSONDecodeError, OSError):
                    pass  # 손상된 상태 파일은 무시하고 오늘 기준으로 새로 시작
            self.today_realized_pnl = 0.0
            self.day_start_equity = None
            self._today = today
            self._save_state()

    def _save_state(self):
        # 🆕 원자적 쓰기: 임시 파일에 먼저 쓰고 os.replace로 교체 -> 쓰는 도중 죽어도
        # 기존 파일이 반쯤 쓰인 상태로 손상되지 않음 (읽을 때는 항상 완전한 이전 버전이거나 완전한 새 버전만 보임)
        tmp_path = self.state_path + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump({
                    "date": self._today,
                    "today_realized_pnl": self.today_realized_pnl,
                    "day_start_equity": self.day_start_equity,
                }, f)
            os.replace(tmp_path, self.state_path)
            try:
                os.chmod(self.state_path, 0o600)  # 🆕 소유자만 읽기/쓰기 (금융 데이터라 권한 제한)
            except OSError:
                pass  # 일부 OS/파일시스템에서는 미지원 - 무시해도 치명적이지 않음
        except OSError as e:
            print(f"⚠️ risk_guard 상태 저장 실패(파일 쓰기 오류): {e}")

    def set_day_start_equity(self, equity):
        """그날 첫 기준 자본을 등록 (이미 등록돼 있으면 무시 — 하루에 한 번만 고정)"""
        with self._lock:
            if self._today != str(date.today()):
                self._load_state()
            if self.day_start_equity is None:
                self.day_start_equity = equity
                self._save_state()

    def record_realized_pnl(self, pnl):
        """포지션 청산/부분청산 때마다 실현손익을 여기 누적시켜야 서킷브레이커가 의미가 있음"""
        with self._lock:
            self._load_state()  # 날짜가 자정을 넘겼을 수 있으니 매번 재확인 후 누적
            self.today_realized_pnl += pnl
            self._save_state()

    def is_kill_switch_on(self):
        return os.path.exists(self.kill_switch_path)

    def is_daily_loss_limit_hit(self):
        with self._lock:
            self._load_state()
            if not self.day_start_equity or self.day_start_equity <= 0:
                return False
            loss_pct = -self.today_realized_pnl / self.day_start_equity
            return loss_pct >= self.daily_loss_limit_pct

    def can_open_new_position(self):
        """신규 진입 가능 여부. 기존 포지션 관리(청산 등)는 이 체크와 무관하게 항상 가능해야 함."""
        if self.is_kill_switch_on():
            return False, f"🚨 킬스위치 작동 중 ({self.kill_switch_path} 파일 존재) — 신규 진입 차단"
        if self.is_daily_loss_limit_hit():
            return False, (f"🚨 일일 손실 한도({self.daily_loss_limit_pct*100:.1f}%) 도달 "
                            f"(오늘 실현손익: {self.today_realized_pnl:+.2f}) — 신규 진입 차단")
        return True, ""
