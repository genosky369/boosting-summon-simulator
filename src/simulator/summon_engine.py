"""
소환권 시뮬레이션 엔진
- 소환권을 사용했을 때 획득 아이템 기대값 계산
- 기대값 기반 (몬테카를로 아님)
"""

from typing import Dict, List, Optional, Tuple
import math
from dataclasses import dataclass, field
from copy import deepcopy

try:
    from data.constants import Grade, Category, GRADE_ORDER
    from data.loader import get_data_manager, SummonTicket
except ImportError:
    import sys
    sys.path.insert(0, str(__file__).rsplit('src', 1)[0] + 'src')
    from data.constants import Grade, Category, GRADE_ORDER
    from data.loader import get_data_manager, SummonTicket


@dataclass
class Inventory:
    """
    인벤토리 (보유 아이템)

    [도감 완성도 기반 합성 시스템]
    - 총 획득 개수 추적 (total_acquired)
    - 도감 완성에 필요한 개수 = 등급별 종류 수
    - 중복분 = 총 획득 - 도감 완성 필요량
    - 합성 재료는 중복분만 사용
    """
    # 등급별 총 획득 개수
    total_acquired: Dict[Grade, float] = field(default_factory=dict)

    # 등급별 도감에 등록된 개수 (= min(총획득, 종류수))
    owned_count: Dict[Grade, float] = field(default_factory=dict)

    # 등급별 중복 개수 (= 총획득 - 도감등록, 합성 재료)
    duplicate_count: Dict[Grade, float] = field(default_factory=dict)

    # 카테고리
    category: Category = None

    # 등급별 종류 수 (도감 완성 기준)
    _type_counts: Dict[Grade, int] = field(default_factory=dict)

    def __post_init__(self):
        # 모든 등급 초기화
        for grade in Grade:
            if grade not in self.total_acquired:
                self.total_acquired[grade] = 0
            if grade not in self.owned_count:
                self.owned_count[grade] = 0
            if grade not in self.duplicate_count:
                self.duplicate_count[grade] = 0

    def set_type_counts(self, type_counts: Dict[Grade, int]):
        """등급별 종류 수 설정"""
        self._type_counts = type_counts

    def add_items(self, grade: Grade, count: float, item_type_count: int = 0):
        """
        아이템 추가

        Args:
            grade: 등급
            count: 획득 개수 (기대값이므로 소수점 가능)
            item_type_count: 해당 등급의 총 아이템 종류 수 (도감 계산용)

        [도감 완성도 기반 로직]
        1. 총 획득 개수 증가
        2. 도감 등록: min(총획득, 종류수) - 종류 수만큼만 도감에 등록
        3. 중복분: 총획득 - 도감등록 = 합성 재료
        """
        # 종류 수 저장
        if item_type_count > 0:
            self._type_counts[grade] = item_type_count

        type_count = self._type_counts.get(grade, 0)

        # 총 획득 증가
        self.total_acquired[grade] = self.total_acquired.get(grade, 0) + count

        # 도감 완성도 계산 (종류 수만큼만 도감에 등록)
        total = self.total_acquired[grade]
        if type_count > 0:
            # 도감에 등록되는 개수 = 기대값으로 계산
            # 쿠폰 수집 문제의 기대값 근사 사용
            owned = self._calculate_expected_unique(total, type_count)
            self.owned_count[grade] = owned
            # 중복분 = 총 획득 - 도감 등록
            self.duplicate_count[grade] = max(0, total - owned)
        else:
            # 종류 수 정보가 없으면 전부 중복으로 처리
            self.owned_count[grade] = 0
            self.duplicate_count[grade] = total

    def _calculate_expected_unique(self, total_draws: float, total_types: int) -> float:
        """
        기대 고유 아이템 수 계산 (쿠폰 수집 문제)

        n개 종류 중 k번 뽑았을 때 기대 고유 개수:
        E[unique] = n * (1 - ((n-1)/n)^k)

        Args:
            total_draws: 총 뽑기 횟수
            total_types: 총 종류 수

        Returns:
            기대 고유 아이템 수
        """
        if total_types <= 0:
            return 0
        if total_draws <= 0:
            return 0

        n = total_types
        k = total_draws

        # E[unique] = n * (1 - ((n-1)/n)^k)
        prob_not_collected = ((n - 1) / n) ** k
        expected_unique = n * (1 - prob_not_collected)

        return min(expected_unique, total_types)

    def get_collection_status(self, grade: Grade) -> Tuple[float, int]:
        """
        도감 완성도 조회

        Returns:
            (획득한 종류 수, 총 종류 수)
        """
        owned = self.owned_count.get(grade, 0)
        total = self._type_counts.get(grade, 0)
        return (owned, total)

    def get_total(self, grade: Grade) -> float:
        """특정 등급의 총 획득 개수"""
        return self.total_acquired.get(grade, 0)

    def get_materials(self, grade: Grade) -> float:
        """합성 재료로 사용 가능한 개수 (중복분만)"""
        return self.duplicate_count.get(grade, 0)

    def use_materials(self, grade: Grade, count: float) -> float:
        """
        합성 재료 사용

        Returns:
            실제 사용한 개수
        """
        available = self.duplicate_count.get(grade, 0)
        used = min(available, count)
        self.duplicate_count[grade] = available - used
        # total_acquired도 차감하여 쿠폰 컬렉터 계산이 정확하도록 함
        self.total_acquired[grade] = max(0, self.total_acquired.get(grade, 0) - used)
        return used


@dataclass
class SummonResult:
    """소환 결과"""
    category: Category
    ticket_name: str
    ticket_count: int
    total_pulls: int
    expected_items: Dict[Grade, float]  # 등급별 기대 획득 개수


class SummonEngine:
    """소환권 시뮬레이션 엔진"""

    def __init__(self):
        self.dm = get_data_manager()

    def simulate_summon(
        self,
        ticket: SummonTicket,
        count: int = 1
    ) -> SummonResult:
        """
        소환권 사용 시뮬레이션 (기대값 계산)

        Args:
            ticket: 소환권 정보
            count: 소환권 사용 개수

        Returns:
            SummonResult: 소환 결과 (기대값)
        """
        total_pulls = ticket.pulls_per_ticket * count
        expected_items = {}

        for grade, prob in ticket.probabilities.items():
            expected_count = total_pulls * prob
            if expected_count > 0:
                expected_items[grade] = expected_count

        return SummonResult(
            category=ticket.category,
            ticket_name=ticket.name,
            ticket_count=count,
            total_pulls=total_pulls,
            expected_items=expected_items
        )

    def apply_summon_result(
        self,
        inventory: Inventory,
        result: SummonResult
    ) -> Inventory:
        """
        소환 결과를 인벤토리에 적용

        Args:
            inventory: 현재 인벤토리
            result: 소환 결과

        Returns:
            업데이트된 인벤토리
        """
        for grade, count in result.expected_items.items():
            item_type_count = self.dm.get_item_count(result.category, grade)
            inventory.add_items(grade, count, item_type_count)

        return inventory

    def simulate_multiple_summons(
        self,
        tickets_with_counts: List[Tuple[str, int]],
        category: Category,
        initial_inventory: Optional[Inventory] = None
    ) -> Tuple[Inventory, List[SummonResult]]:
        """
        여러 소환권 사용 시뮬레이션

        Args:
            tickets_with_counts: [(소환권 이름, 개수), ...]
            category: 카테고리
            initial_inventory: 초기 인벤토리 (None이면 빈 인벤토리)

        Returns:
            (최종 인벤토리, 소환 결과 리스트)
        """
        inventory = initial_inventory or Inventory(category=category)
        results = []

        for ticket_name, count in tickets_with_counts:
            ticket = self.dm.get_ticket_by_name(ticket_name)
            if ticket is None:
                continue

            result = self.simulate_summon(ticket, count)
            self.apply_summon_result(inventory, result)
            results.append(result)

        return inventory, results


# =============================================================================
# 유틸리티 함수
# =============================================================================

def create_empty_inventory(category: Category) -> Inventory:
    """빈 인벤토리 생성"""
    return Inventory(category=category)


def calculate_total_expected(results: List[SummonResult]) -> Dict[Grade, float]:
    """여러 소환 결과의 총 기대값 계산"""
    total = {}
    for result in results:
        for grade, count in result.expected_items.items():
            total[grade] = total.get(grade, 0) + count
    return total
