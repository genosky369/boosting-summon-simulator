"""
소환권 배분 계산기
- 목표 달성을 위한 소환권 배분 비율 기반 계산
- 각 소환권 타입별 필요 개수 산출
- 도감 완성 한계 고려
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

try:
    from data.constants import Grade, Category, GRADE_ORDER, CATEGORY_MAX_GRADE
    from data.loader import get_data_manager, SummonTicket
    from simulator.summon_engine import Inventory, SummonEngine
    from simulator.synthesis_engine import SynthesisEngine, synthesize_to_max
    from simulator.levelup_engine import (
        SpiritInventory, process_spirit_levelup_then_synthesis,
        process_card_levelup_then_synthesis
    )
except ImportError:
    import sys
    sys.path.insert(0, str(__file__).rsplit('src', 1)[0] + 'src')
    from data.constants import Grade, Category, GRADE_ORDER, CATEGORY_MAX_GRADE
    from data.loader import get_data_manager, SummonTicket
    from simulator.summon_engine import Inventory, SummonEngine
    from simulator.synthesis_engine import SynthesisEngine, synthesize_to_max
    from simulator.levelup_engine import (
        SpiritInventory, process_spirit_levelup_then_synthesis,
        process_card_levelup_then_synthesis
    )


@dataclass
class AllocationResult:
    """배분 계산 결과"""
    ticket_name: str
    ticket_count: int  # 필요한 소환권 개수
    contribution_ratio: float  # 기여 비율 (0~1)
    expected_target_items: float  # 해당 소환권으로 얻는 목표 등급 기대값
    warning: str = ""  # 경고 메시지 (도감 한계 초과 등)


@dataclass
class AllocationSummary:
    """배분 계산 전체 요약"""
    category: Category
    target_grade: Grade
    target_count: int
    allocations: List[AllocationResult]
    total_tickets: int
    total_expected: float  # 도감+중복분 합계 기대값
    collection_limit: int = 0  # 도감 종류 수 (한계)
    warning: str = ""  # 전체 경고 메시지


class AllocationCalculator:
    """소환권 배분 계산기"""

    def __init__(self, spirit_target_level: int = 5, card_target_level: int = 5):
        """
        Args:
            spirit_target_level: 투혼 레벨업 목표 (0~5, 기본값 5)
            card_target_level: 카드 레벨업 목표 (0~5, 기본값 5)
        """
        self.dm = get_data_manager()
        self.summon_engine = SummonEngine()
        self.synthesis_engine = SynthesisEngine()
        self.spirit_target_level = spirit_target_level
        self.card_target_level = card_target_level

    def _run_simulation(
        self,
        category: Category,
        target_grade: Grade,
        ticket_name: str,
        ticket_count: int,
        max_synthesis_grade: Optional[Grade] = None
    ) -> float:
        """
        단일 소환권으로 시뮬레이션하여 목표 등급 획득량 계산

        Args:
            max_synthesis_grade: 합성 상한 등급 (None이면 카테고리 최대)
                ANCIENT로 설정하면 고대→전설 합성 차단 (불멸 모드)

        Returns:
            목표 등급의 총 보유량 (도감 + 중복분)
        """
        if ticket_count <= 0:
            return 0.0

        # 빈 인벤토리 생성
        if category == Category.SPIRIT:
            inventory = SpiritInventory(category=category)
        else:
            inventory = Inventory(category=category)

        # 실제 종류 수를 설정하여 도감(장판) 효과를 반영
        type_counts = self.dm.item_counts.get(category, {})
        inventory.set_type_counts(type_counts)

        # 소환권 적용
        ticket = self.dm.get_ticket_by_name(ticket_name)
        if ticket:
            result = self.summon_engine.simulate_summon(ticket, ticket_count)
            self.summon_engine.apply_summon_result(inventory, result)

        # 합성/레벨업 처리
        if category == Category.SPIRIT:
            inventory, _ = process_spirit_levelup_then_synthesis(
                inventory, target_level=self.spirit_target_level
            )
        elif category == Category.CARD:
            inventory, _ = process_card_levelup_then_synthesis(
                inventory, target_level=self.card_target_level
            )
        else:
            if max_synthesis_grade:
                # 합성 상한 제한 (불멸 모드: 고대→전설 차단)
                inventory, _ = self.synthesis_engine.synthesize_all(
                    inventory, category, max_grade=max_synthesis_grade
                )
            else:
                inventory, _ = synthesize_to_max(inventory, category)

        # 목표 등급 총 보유량 (도감 + 중복분)
        owned = inventory.owned_count.get(target_grade, 0)
        duplicates = inventory.duplicate_count.get(target_grade, 0)
        return owned + duplicates

    def _find_required_tickets_binary_search(
        self,
        category: Category,
        target_grade: Grade,
        ticket_name: str,
        target_items: float,
        max_tickets: int = 10000000,
        max_synthesis_grade: Optional[Grade] = None
    ) -> Tuple[int, float, str]:
        """
        이진 탐색으로 목표 달성에 필요한 소환권 수 찾기

        Returns:
            (필요 소환권 수, 실제 기대 획득량, 경고 메시지)
        """
        if target_items <= 0:
            return 0, 0.0, ""

        # 먼저 상한선에서 달성 가능한지 확인
        max_achievable = self._run_simulation(category, target_grade, ticket_name, max_tickets, max_synthesis_grade)

        if max_achievable < target_items:
            return -1, max_achievable, f"목표 {target_items:.1f}개 달성 불가 (최대 {max_achievable:.1f}개)"

        low = 0
        high = max_tickets
        best_count = max_tickets
        best_achieved = max_achievable

        while low < high:
            mid = (low + high) // 2
            achieved = self._run_simulation(category, target_grade, ticket_name, mid, max_synthesis_grade)

            if achieved >= target_items:
                best_count = mid
                best_achieved = achieved
                high = mid
            else:
                low = mid + 1

        final_achieved = self._run_simulation(category, target_grade, ticket_name, best_count, max_synthesis_grade)

        return best_count, final_achieved, ""

    def calculate_allocation(
        self,
        category: Category,
        target_grade: Grade,
        target_count: int,
        ticket_ratios: Dict[str, float],
        max_synthesis_grade: Optional[Grade] = None
    ) -> AllocationSummary:
        """
        목표 달성을 위한 소환권 배분 계산

        이진 탐색 기반으로 각 소환권별 필요 개수를 정확히 계산

        Args:
            category: 카테고리
            target_grade: 목표 등급
            target_count: 목표 개수
            ticket_ratios: 소환권별 기여 비율 (소환권 전체 이름: 비율, 0~1)

        Returns:
            AllocationSummary
        """
        # 도감은 고려하지 않음 (순수 획득 개수만 계산)
        collection_limit = 0
        overall_warning = ""

        if not ticket_ratios or sum(ticket_ratios.values()) == 0:
            return AllocationSummary(
                category=category,
                target_grade=target_grade,
                target_count=target_count,
                allocations=[],
                total_tickets=0,
                total_expected=0,
                collection_limit=collection_limit,
                warning=overall_warning
            )

        # 비율을 그대로 사용 (정규화하지 않음)
        allocations = []
        total_tickets = 0
        total_expected = 0

        for ticket_name, ratio in ticket_ratios.items():
            if ratio <= 0:
                continue

            # 이 소환권이 기여해야 할 목표 개수
            target_contribution = target_count * ratio

            # 이진 탐색으로 필요한 소환권 수 찾기
            ticket_count, expected, warning = self._find_required_tickets_binary_search(
                category, target_grade, ticket_name, target_contribution,
                max_synthesis_grade=max_synthesis_grade
            )

            if ticket_count >= 0:
                total_tickets += ticket_count
                total_expected += expected

            allocations.append(AllocationResult(
                ticket_name=ticket_name,
                ticket_count=ticket_count,
                contribution_ratio=ratio,
                expected_target_items=expected,
                warning=warning
            ))

        return AllocationSummary(
            category=category,
            target_grade=target_grade,
            target_count=target_count,
            allocations=allocations,
            total_tickets=total_tickets,
            total_expected=total_expected,
            collection_limit=collection_limit,
            warning=overall_warning
        )

    def calculate_allocation_precise(
        self,
        category: Category,
        target_grade: Grade,
        target_count: int,
        ticket_ratios: Dict[str, float],
        tolerance: float = 0.05,
        max_synthesis_grade: Optional[Grade] = None
    ) -> AllocationSummary:
        """
        정밀한 배분 계산 (이진 탐색 기반)

        calculate_allocation과 동일하게 동작 (이미 이진 탐색으로 정밀함)
        """
        return self.calculate_allocation(
            category, target_grade, target_count, ticket_ratios,
            max_synthesis_grade=max_synthesis_grade
        )

    # 하위 호환성을 위한 메서드들
    def calculate_single_ticket_efficiency(
        self,
        ticket: SummonTicket,
        category: Category,
        target_grade: Grade,
        ticket_count: int = 1000,
        target_contribution: float = 0
    ) -> Tuple[float, float]:
        """
        단일 소환권의 목표 등급 효율 계산 (하위 호환성)
        """
        achieved = self._run_simulation(
            category, target_grade, ticket.name, ticket_count
        )
        efficiency = achieved / ticket_count if ticket_count > 0 else 0
        return efficiency, achieved

    def _simulate_single_allocation(
        self,
        category: Category,
        target_grade: Grade,
        ticket_name: str,
        ticket_count: int
    ) -> float:
        """단일 소환권 시뮬레이션 (하위 호환성)"""
        return self._run_simulation(category, target_grade, ticket_name, ticket_count)

    def _simulate_allocation(
        self,
        category: Category,
        target_grade: Grade,
        allocations: List[AllocationResult]
    ) -> float:
        """배분 결과로 전체 시뮬레이션 (하위 호환성)"""
        # 빈 인벤토리 생성
        if category == Category.SPIRIT:
            inventory = SpiritInventory(category=category)
        else:
            inventory = Inventory(category=category)

        type_counts = self.dm.item_counts.get(category, {})
        inventory.set_type_counts(type_counts)

        # 각 소환권 적용
        for alloc in allocations:
            ticket = self.dm.get_ticket_by_name(alloc.ticket_name)
            if ticket and alloc.ticket_count > 0:
                result = self.summon_engine.simulate_summon(ticket, alloc.ticket_count)
                self.summon_engine.apply_summon_result(inventory, result)

        # 합성/레벨업 처리
        if category == Category.SPIRIT:
            inventory, _ = process_spirit_levelup_then_synthesis(
                inventory, target_level=self.spirit_target_level
            )
        elif category == Category.CARD:
            inventory, _ = process_card_levelup_then_synthesis(
                inventory, target_level=self.card_target_level
            )
        else:
            inventory, _ = synthesize_to_max(inventory, category)

        # 목표 등급 총 보유량
        owned = inventory.owned_count.get(target_grade, 0)
        duplicates = inventory.duplicate_count.get(target_grade, 0)

        return owned + duplicates


def get_allocation_calculator() -> AllocationCalculator:
    """배분 계산기 인스턴스 가져오기"""
    return AllocationCalculator()
