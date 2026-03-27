"""
메인 시뮬레이션 엔진
- 전체 시뮬레이션 흐름 관리
- 주차별 소환권 → 획득 → 합성 → 결과
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from copy import deepcopy
from datetime import date

try:
    from data.constants import (
        Grade, Category, GRADE_ORDER, BOOSTING_SCHEDULE,
        TOTAL_WEEKS, DEFAULT_TARGET_SPEC, TARGET_TOLERANCE
    )
    from data.loader import get_data_manager
    from simulator.summon_engine import (
        SummonEngine, Inventory, SummonResult, create_empty_inventory
    )
    from simulator.synthesis_engine import SynthesisEngine, synthesize_to_max
    from simulator.levelup_engine import (
        SpiritInventory, process_spirit_levelup_then_synthesis,
        process_card_levelup_then_synthesis
    )
except ImportError:
    import sys
    sys.path.insert(0, str(__file__).rsplit('src', 1)[0] + 'src')
    from data.constants import (
        Grade, Category, GRADE_ORDER, BOOSTING_SCHEDULE,
        TOTAL_WEEKS, DEFAULT_TARGET_SPEC, TARGET_TOLERANCE
    )
    from data.loader import get_data_manager
    from simulator.summon_engine import (
        SummonEngine, Inventory, SummonResult, create_empty_inventory
    )
    from simulator.synthesis_engine import SynthesisEngine, synthesize_to_max
    from simulator.levelup_engine import (
        SpiritInventory, process_spirit_levelup_then_synthesis,
        process_card_levelup_then_synthesis
    )


@dataclass
class WeeklyInput:
    """주차별 입력 데이터"""
    week: int
    date: date
    tickets: Dict[Category, List[Tuple[str, int]]]  # 카테고리별 [(소환권명, 개수), ...]

    def __post_init__(self):
        if self.tickets is None:
            self.tickets = {cat: [] for cat in Category}


@dataclass
class WeeklyResult:
    """주차별 결과"""
    week: int
    date: date

    # 카테고리별 인벤토리 상태
    inventories: Dict[Category, Inventory]

    # 카테고리별 소환 결과
    summon_results: Dict[Category, List[SummonResult]]

    # 목표 대비 진행률
    progress: Dict[Category, Dict[Grade, float]]

    # 해당 주차에 추가된 양 (목표 대비 %)
    weekly_contribution: Dict[Category, float]


@dataclass
class SimulationState:
    """시뮬레이션 상태"""
    # 목표 스펙
    target_spec: Dict[Category, Dict[Grade, int]] = field(default_factory=dict)

    # 주차별 입력
    weekly_inputs: Dict[int, WeeklyInput] = field(default_factory=dict)

    # 주차별 결과
    weekly_results: Dict[int, WeeklyResult] = field(default_factory=dict)

    # 현재 인벤토리 (카테고리별)
    current_inventories: Dict[Category, Inventory] = field(default_factory=dict)

    # 총 소환권 사용량 (목표 달성에 필요한 총량 추적용)
    total_tickets_used: Dict[Category, Dict[str, int]] = field(default_factory=dict)

    # 레벨업 목표 레벨 (투혼, 카드만 해당)
    spirit_target_level: int = 5  # 투혼 레벨업 목표 (0~5)
    card_target_level: int = 5    # 카드 레벨업 목표 (0~5)

    # 불멸 클래스 목표
    class_immortal_target: int = 0

    def ensure_categories(self):
        """모든 카테고리가 초기화되었는지 확인"""
        for cat in Category:
            if cat not in self.total_tickets_used:
                self.total_tickets_used[cat] = {}


class MainSimulationEngine:
    """메인 시뮬레이션 엔진"""

    def __init__(self):
        self.dm = get_data_manager()
        self.summon_engine = SummonEngine()
        self.synthesis_engine = SynthesisEngine()

    def create_initial_state(
        self,
        target_spec: Optional[Dict[Category, Dict[Grade, int]]] = None
    ) -> SimulationState:
        """
        초기 시뮬레이션 상태 생성

        Args:
            target_spec: 목표 스펙 (None이면 기본값)

        Returns:
            SimulationState
        """
        if target_spec is None:
            target_spec = deepcopy(DEFAULT_TARGET_SPEC)

        # 빈 인벤토리 생성 (종류 수 정보 포함)
        inventories = {}
        for cat in Category:
            if cat == Category.SPIRIT:
                inv = SpiritInventory(category=cat)
            else:
                inv = Inventory(category=cat)
            # 종류 수 정보 설정
            type_counts = self.dm.item_counts.get(cat, {})
            inv.set_type_counts(type_counts)
            inventories[cat] = inv

        return SimulationState(
            target_spec=target_spec,
            weekly_inputs={},
            weekly_results={},
            current_inventories=inventories,
            total_tickets_used={cat: {} for cat in Category}
        )

    def add_weekly_input(
        self,
        state: SimulationState,
        week: int,
        tickets: Dict[Category, List[Tuple[str, int]]]
    ) -> SimulationState:
        """
        주차별 소환권 입력 추가

        Args:
            state: 현재 상태
            week: 주차 (1-10)
            tickets: 카테고리별 소환권 목록

        Returns:
            업데이트된 상태
        """
        if week < 1 or week > TOTAL_WEEKS:
            raise ValueError(f"주차는 1~{TOTAL_WEEKS} 사이여야 합니다.")

        state = deepcopy(state)
        state.ensure_categories()

        weekly_date = BOOSTING_SCHEDULE.get(week, date.today())
        state.weekly_inputs[week] = WeeklyInput(
            week=week,
            date=weekly_date,
            tickets=tickets
        )

        # 총 소환권 사용량 업데이트
        for cat, ticket_list in tickets.items():
            if cat not in state.total_tickets_used:
                state.total_tickets_used[cat] = {}
            for ticket_name, count in ticket_list:
                current = state.total_tickets_used[cat].get(ticket_name, 0)
                state.total_tickets_used[cat][ticket_name] = current + count

        return state

    def simulate_week(
        self,
        state: SimulationState,
        week: int
    ) -> SimulationState:
        """
        특정 주차 시뮬레이션 실행

        Args:
            state: 현재 상태
            week: 주차

        Returns:
            업데이트된 상태
        """
        if week not in state.weekly_inputs:
            return state

        state = deepcopy(state)
        weekly_input = state.weekly_inputs[week]

        summon_results = {cat: [] for cat in Category}
        weekly_contribution = {cat: 0.0 for cat in Category}

        # 이전 주차까지의 인벤토리 상태 복사
        prev_inventories = deepcopy(state.current_inventories)

        for cat in Category:
            ticket_list = weekly_input.tickets.get(cat, [])
            if not ticket_list:
                continue

            inventory = state.current_inventories[cat]

            # 1. 소환권 사용
            for ticket_name, count in ticket_list:
                ticket = self.dm.get_ticket_by_name(ticket_name)
                if ticket is None:
                    continue

                result = self.summon_engine.simulate_summon(ticket, count)
                self.summon_engine.apply_summon_result(inventory, result)
                summon_results[cat].append(result)

            # 2. 합성/레벨업 처리
            if cat == Category.SPIRIT:
                inventory, _ = process_spirit_levelup_then_synthesis(
                    inventory, target_level=state.spirit_target_level
                )
            elif cat == Category.CARD:
                inventory, _ = process_card_levelup_then_synthesis(
                    inventory, target_level=state.card_target_level
                )
            else:
                imm_target = getattr(state, 'class_immortal_target', 0)
                reserved_ancient = 0
                reserved_legendary = 0

                if cat == Category.CLASS and imm_target > 0:
                    # 불멸 클래스 로직:
                    # 1단계: 고대 도감 95% 달성 전 → 고대까지만 합성 (고대→전설 차단)
                    # 2단계: 고대 도감 95% 달성 후 → 고대 32개 예약 후 전설 합성 허용
                    # 3단계: 전설 목표 80% 달성 후 → 전설 8개 예약

                    ancient_owned, ancient_types = inventory.get_collection_status(Grade.ANCIENT)
                    ancient_filled = ancient_types > 0 and ancient_owned >= ancient_types * 0.95

                    if not ancient_filled:
                        pass  # 합성은 아래에서 max_grade 제한으로 처리
                    else:
                        # 고대 도감 달성: 고대 32개 예약
                        ancient_dups = inventory.duplicate_count.get(Grade.ANCIENT, 0)
                        reserved_ancient = min(32, ancient_dups)
                        if reserved_ancient > 0:
                            inventory.duplicate_count[Grade.ANCIENT] = max(0,
                                inventory.duplicate_count.get(Grade.ANCIENT, 0) - reserved_ancient)
                            inventory.total_acquired[Grade.ANCIENT] = max(0,
                                inventory.total_acquired.get(Grade.ANCIENT, 0) - reserved_ancient)

                    # 전설 잉여 예약 (전설 목표 80% 달성 시)
                    legend_target = state.target_spec.get(Category.CLASS, {}).get(Grade.LEGENDARY, 10)
                    legend_owned = inventory.owned_count.get(Grade.LEGENDARY, 0)
                    legend_dups = inventory.duplicate_count.get(Grade.LEGENDARY, 0)
                    legend_total = legend_owned + legend_dups

                    if legend_total >= legend_target * 0.8:
                        legend_surplus = max(0, legend_total - legend_target)
                        reserved_legendary = min(8, legend_surplus)
                        if reserved_legendary > 0:
                            inventory.duplicate_count[Grade.LEGENDARY] = max(0,
                                inventory.duplicate_count.get(Grade.LEGENDARY, 0) - reserved_legendary)
                            inventory.total_acquired[Grade.LEGENDARY] = max(0,
                                inventory.total_acquired.get(Grade.LEGENDARY, 0) - reserved_legendary)

                    if not ancient_filled:
                        # 고대 도감 미달: 고대까지만 합성 (일반→고급→희귀→영웅→고대)
                        inventory, _ = self.synthesis_engine.synthesize_all(
                            inventory, cat, max_grade=Grade.LEGENDARY
                        )
                        # max_grade=LEGENDARY면 고대까지만 합성 (LEGENDARY에서 break)
                    else:
                        # 고대 도감 달성: 전설까지 합성
                        inventory, _ = synthesize_to_max(inventory, cat)

                    # 예약분 복원
                    if reserved_ancient > 0:
                        inventory.total_acquired[Grade.ANCIENT] = inventory.total_acquired.get(Grade.ANCIENT, 0) + reserved_ancient
                        inventory.duplicate_count[Grade.ANCIENT] = inventory.duplicate_count.get(Grade.ANCIENT, 0) + reserved_ancient
                    if reserved_legendary > 0:
                        inventory.total_acquired[Grade.LEGENDARY] = inventory.total_acquired.get(Grade.LEGENDARY, 0) + reserved_legendary
                        inventory.duplicate_count[Grade.LEGENDARY] = inventory.duplicate_count.get(Grade.LEGENDARY, 0) + reserved_legendary
                else:
                    # 불멸 목표 없음 또는 펫: 기존대로
                    inventory, _ = synthesize_to_max(inventory, cat)

            state.current_inventories[cat] = inventory

        # 3. 진행률 계산
        progress = self._calculate_progress(state)

        # 4. 주차별 기여도 계산
        for cat in Category:
            prev_progress = self._calculate_category_progress(
                prev_inventories[cat],
                state.target_spec.get(cat, {})
            )
            curr_progress = self._calculate_category_progress(
                state.current_inventories[cat],
                state.target_spec.get(cat, {})
            )
            weekly_contribution[cat] = curr_progress - prev_progress

        # 5. 결과 저장
        state.weekly_results[week] = WeeklyResult(
            week=week,
            date=weekly_input.date,
            inventories=deepcopy(state.current_inventories),
            summon_results=summon_results,
            progress=progress,
            weekly_contribution=weekly_contribution
        )

        return state

    def simulate_all(self, state: SimulationState) -> SimulationState:
        """
        모든 주차 시뮬레이션 실행

        Args:
            state: 현재 상태

        Returns:
            최종 상태
        """
        state = deepcopy(state)

        # 인벤토리 초기화 (처음부터 다시 시뮬레이션, 종류 수 정보 포함)
        for cat in Category:
            if cat == Category.SPIRIT:
                inv = SpiritInventory(category=cat)
            else:
                inv = Inventory(category=cat)
            # 종류 수 정보 설정
            type_counts = self.dm.item_counts.get(cat, {})
            inv.set_type_counts(type_counts)
            state.current_inventories[cat] = inv

        # 기존 결과 초기화
        state.weekly_results = {}

        # 입력된 주차만 순서대로 시뮬레이션
        weeks = sorted(state.weekly_inputs.keys())
        for week in weeks:
            state = self.simulate_week(state, week)

        return state

    def _calculate_progress(
        self,
        state: SimulationState
    ) -> Dict[Category, Dict[Grade, float]]:
        """
        목표 대비 진행률 계산

        총 보유량 = 도감 완성도(owned_count) + 합성 후 남은 중복분(duplicate_count)

        Returns:
            카테고리별, 등급별 진행률 (0~1, 1 이상이면 초과 달성)
        """
        progress = {}

        for cat, targets in state.target_spec.items():
            progress[cat] = {}
            inventory = state.current_inventories.get(cat)

            if inventory is None:
                continue

            for grade, target_count in targets.items():
                if target_count <= 0:
                    progress[cat][grade] = 1.0
                    continue

                # 총 보유량 = 도감 + 중복분
                owned = inventory.owned_count.get(grade, 0)
                duplicates = inventory.duplicate_count.get(grade, 0)
                total_owned = owned + duplicates
                progress[cat][grade] = total_owned / target_count

        return progress

    def _calculate_category_progress(
        self,
        inventory: Inventory,
        targets: Dict[Grade, int]
    ) -> float:
        """
        카테고리 전체 진행률 계산 (가중 평균)

        총 보유량 = 도감 완성도(owned_count) + 합성 후 남은 중복분(duplicate_count)

        Returns:
            0~1 사이 값 (1이면 목표 달성)
        """
        if not targets:
            return 0.0

        total_target = sum(targets.values())
        if total_target <= 0:
            return 0.0

        total_current = sum(
            min(inventory.owned_count.get(grade, 0) + inventory.duplicate_count.get(grade, 0), count)
            for grade, count in targets.items()
        )

        return total_current / total_target

    def get_summary(self, state: SimulationState) -> Dict[str, Any]:
        """
        시뮬레이션 요약 정보

        Returns:
            요약 딕셔너리
        """
        summary = {
            "target_spec": {},
            "current_status": {},
            "progress": {},
            "weekly_contributions": {},
        }

        # 목표 스펙
        for cat, targets in state.target_spec.items():
            summary["target_spec"][cat.value] = {
                grade.value: count for grade, count in targets.items()
            }

        # 현재 상태
        for cat, inventory in state.current_inventories.items():
            summary["current_status"][cat.value] = {
                grade.value: {
                    "owned": inventory.owned_count.get(grade, 0),
                    "duplicates": inventory.duplicate_count.get(grade, 0)
                }
                for grade in Grade
                if inventory.owned_count.get(grade, 0) > 0 or
                   inventory.duplicate_count.get(grade, 0) > 0
            }

        # 진행률
        progress = self._calculate_progress(state)
        for cat, grades in progress.items():
            summary["progress"][cat.value] = {
                grade.value: f"{rate * 100:.1f}%"
                for grade, rate in grades.items()
            }

        # 주차별 기여도
        for week, result in sorted(state.weekly_results.items()):
            summary["weekly_contributions"][f"{week}주차"] = {
                cat.value: f"{contrib * 100:.1f}%"
                for cat, contrib in result.weekly_contribution.items()
                if contrib > 0
            }

        return summary


# =============================================================================
# 편의 함수
# =============================================================================

def quick_simulate(
    tickets_by_week: Dict[int, Dict[Category, List[Tuple[str, int]]]],
    target_spec: Optional[Dict[Category, Dict[Grade, int]]] = None
) -> SimulationState:
    """
    빠른 시뮬레이션 실행

    Args:
        tickets_by_week: {주차: {카테고리: [(소환권명, 개수), ...]}}
        target_spec: 목표 스펙

    Returns:
        최종 시뮬레이션 상태
    """
    engine = MainSimulationEngine()
    state = engine.create_initial_state(target_spec)

    for week, tickets in tickets_by_week.items():
        state = engine.add_weekly_input(state, week, tickets)

    state = engine.simulate_all(state)
    return state
