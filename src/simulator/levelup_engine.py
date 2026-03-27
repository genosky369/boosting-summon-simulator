"""
레벨업 시뮬레이션 엔진
- 투혼/카드 레벨업 시뮬레이션
- 레벨업 우선, 남는 재료로 합성

[투혼 레벨업 규칙]
- 일반~고대 등급: 동일 투혼만 레벨업 재료로 사용 (경험치 2배)
- 보물사냥꾼: 레벨업 전용 재료 (합성 불가)
- 전설 등급: 레벨업만, 합성에 사용 안 함

[카드 레벨업 규칙]
- 레벨업 우선 → 남는 재료로 합성
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from copy import deepcopy

try:
    from data.constants import Grade, Category, GRADE_ORDER
    from data.loader import get_data_manager
    from simulator.summon_engine import Inventory
except ImportError:
    import sys
    sys.path.insert(0, str(__file__).rsplit('src', 1)[0] + 'src')
    from data.constants import Grade, Category, GRADE_ORDER
    from data.loader import get_data_manager
    from simulator.summon_engine import Inventory


@dataclass
class LevelUpResult:
    """레벨업 결과"""
    category: Category
    grade: Grade
    items_leveled: float  # 레벨업한 아이템 수
    total_exp_used: float  # 사용한 총 경험치
    materials_used: Dict[Grade, float]  # 등급별 사용한 재료


@dataclass
class SpiritInventory(Inventory):
    """
    투혼 전용 인벤토리

    [기획 변경 가능 영역]
    투혼은 동일 투혼 레벨업 규칙이 있어서 별도 처리 필요
    현재는 등급별로만 추적하므로, "동일 투혼" 여부를 확률적으로 계산
    """
    # 보물사냥꾼 보유 개수
    treasure_hunters: Dict[str, float] = None

    def __post_init__(self):
        super().__post_init__()
        if self.treasure_hunters is None:
            self.treasure_hunters = {}


class SpiritLevelUpEngine:
    """
    투혼 레벨업 엔진

    [레벨업 규칙]
    1. 동일 투혼 재료 시 경험치 2배
    2. 일반~고대: 동일 투혼 + 보물사냥꾼만 레벨업 재료로 사용
    3. 전설: 레벨업만, 합성에 사용 안 함
    """

    def __init__(self, target_level: int = 5):
        """
        Args:
            target_level: 목표 레벨 (0~5, 기본값 5)
        """
        self.dm = get_data_manager()
        self.target_level = max(0, min(5, target_level))

    def calculate_levelup_for_grade(
        self,
        grade: Grade,
        owned_count: float,
        duplicate_count: float,
        treasure_hunter_points: float = 0
    ) -> Tuple[float, float, float]:
        """
        특정 등급 투혼의 레벨업 계산

        Args:
            grade: 등급
            owned_count: 보유 개수 (도감)
            duplicate_count: 중복 개수 (재료용)
            treasure_hunter_points: 보물사냥꾼 레벨업 포인트 총합

        Returns:
            (레벨업된 개수, 사용된 중복 개수, 남은 중복 개수)

        [기획 가정]
        - 동일 투혼이 중복될 확률: duplicate / (등급 내 종류 수)
        - 동일 투혼이면 경험치 2배
        """
        if owned_count <= 0:
            return 0, 0, duplicate_count

        # 목표 레벨이 0이면 레벨업 안 함
        if self.target_level <= 0:
            return 0, 0, duplicate_count

        # 레벨업 정보 가져오기 (목표 레벨까지만)
        levelup_infos = [
            info for info in self.dm.spirit_levelup_info
            if info.grade == grade and info.target_level <= self.target_level
        ]
        if not levelup_infos:
            return 0, 0, duplicate_count

        # 0→목표레벨까지 필요한 총 경험치
        total_exp_needed = sum(info.required_exp for info in levelup_infos)

        # 동일 투혼 재료로 얻는 경험치 (2배)
        point_per_same = self.dm.spirit_levelup_points.get(grade, 0) * 2

        # 투혼 종류 수
        type_count = self.dm.get_item_count(Category.SPIRIT, grade)
        if type_count <= 0:
            type_count = 1

        # 동일 투혼 확률 (종류 수 기반)
        same_spirit_rate = 1 / type_count

        # 중복 투혼 중 동일 투혼으로 사용할 수 있는 기대 개수
        # (보유한 종류 수) / (전체 종류 수) * 중복 개수
        # 간단화: 보유 개수만큼의 종류를 가졌다고 가정
        effective_owned = min(owned_count, type_count)
        same_spirit_prob = effective_owned / type_count

        # 동일 투혼으로 레벨업 가능한 재료
        same_materials = duplicate_count * same_spirit_prob
        exp_from_same = same_materials * point_per_same

        # 보물사냥꾼 경험치
        total_exp_available = exp_from_same + treasure_hunter_points

        # 레벨업 가능한 개수
        if total_exp_needed > 0:
            items_can_levelup = total_exp_available / total_exp_needed
            items_leveled = min(items_can_levelup, owned_count)
        else:
            items_leveled = 0

        # 사용한 재료 계산
        if items_leveled > 0:
            exp_used = items_leveled * total_exp_needed
            # 보물사냥꾼 경험치 우선 사용
            exp_from_hunters = min(treasure_hunter_points, exp_used)
            exp_from_materials = exp_used - exp_from_hunters

            if point_per_same > 0:
                materials_used = exp_from_materials / point_per_same
            else:
                materials_used = 0
        else:
            materials_used = 0

        remaining_duplicates = duplicate_count - materials_used
        return items_leveled, materials_used, max(0, remaining_duplicates)

    def process_levelup(
        self,
        inventory: SpiritInventory
    ) -> Tuple[SpiritInventory, List[LevelUpResult]]:
        """
        투혼 레벨업 처리

        [처리 순서]
        1. 보물사냥꾼 포인트 계산
        2. 등급별 레벨업 (일반 → 전설)
        3. 남은 재료는 합성용으로 유지

        Args:
            inventory: 투혼 인벤토리

        Returns:
            (업데이트된 인벤토리, 레벨업 결과 리스트)
        """
        inventory = deepcopy(inventory)
        results = []

        # 보물사냥꾼 총 포인트
        total_hunter_points = sum(
            count * self.dm.treasure_hunter_levelup_points.get(name, 0)
            for name, count in inventory.treasure_hunters.items()
        )

        # 등급별 레벨업 (일반 → 전설)
        remaining_hunter_points = total_hunter_points

        for grade in GRADE_ORDER:
            if grade == Grade.IMMORTAL:
                continue  # 투혼은 불멸 없음

            owned = inventory.owned_count.get(grade, 0)
            duplicates = inventory.duplicate_count.get(grade, 0)

            if owned <= 0:
                continue

            # 전설은 합성에 사용 안 함, 레벨업만
            if grade == Grade.LEGENDARY:
                # 전설은 보물사냥꾼으로만 레벨업
                items_leveled, _, _ = self.calculate_levelup_for_grade(
                    grade, owned, 0, remaining_hunter_points
                )
                if items_leveled > 0:
                    # 사용한 보물사냥꾼 포인트
                    total_exp_needed = sum(
                        info.required_exp for info in self.dm.spirit_levelup_info
                        if info.grade == grade
                    )
                    exp_used = items_leveled * total_exp_needed
                    remaining_hunter_points -= exp_used

                    results.append(LevelUpResult(
                        category=Category.SPIRIT,
                        grade=grade,
                        items_leveled=items_leveled,
                        total_exp_used=exp_used,
                        materials_used={}
                    ))
            else:
                # 일반~고대: 동일 투혼 + 보물사냥꾼
                items_leveled, materials_used, remaining = self.calculate_levelup_for_grade(
                    grade, owned, duplicates, remaining_hunter_points
                )

                if items_leveled > 0:
                    inventory.duplicate_count[grade] = remaining
                    results.append(LevelUpResult(
                        category=Category.SPIRIT,
                        grade=grade,
                        items_leveled=items_leveled,
                        total_exp_used=0,  # 상세 계산 생략
                        materials_used={grade: materials_used}
                    ))

        return inventory, results


class CardLevelUpEngine:
    """
    카드 레벨업 엔진

    [레벨업 규칙]
    - 레벨업 우선 → 남는 재료로 합성
    - 재료 등급과 개수가 정해져 있음
    """

    def __init__(self, target_level: int = 5):
        """
        Args:
            target_level: 목표 레벨 (0~5, 기본값 5)
        """
        self.dm = get_data_manager()
        self.target_level = max(0, min(5, target_level))

    def process_levelup(
        self,
        inventory: Inventory
    ) -> Tuple[Inventory, List[LevelUpResult]]:
        """
        카드 레벨업 처리

        Args:
            inventory: 카드 인벤토리

        Returns:
            (업데이트된 인벤토리, 레벨업 결과 리스트)
        """
        inventory = deepcopy(inventory)
        results = []

        # 목표 레벨이 0이면 레벨업 안 함
        if self.target_level <= 0:
            return inventory, results

        # 카드 레벨업 정보 (등급별, 목표 레벨까지만)
        levelup_by_grade = {}
        for info in self.dm.card_levelup_info:
            grade = info["grade"]
            target_lv = info.get("target_level", info.get("결과 레벨", 5))
            # 목표 레벨까지만 포함
            if target_lv <= self.target_level:
                if grade not in levelup_by_grade:
                    levelup_by_grade[grade] = []
                levelup_by_grade[grade].append(info)

        # 등급별 레벨업
        for grade in GRADE_ORDER:
            if grade not in levelup_by_grade:
                continue

            owned = inventory.owned_count.get(grade, 0)
            if owned <= 0:
                continue

            # 0→목표레벨까지 필요한 총 재료
            total_materials_needed = {}
            for info in levelup_by_grade[grade]:
                mat_grade = info["material_grade"]
                mat_count = info["material_count"]
                total_materials_needed[mat_grade] = total_materials_needed.get(mat_grade, 0) + mat_count

            # 레벨업 가능 개수 계산
            items_can_levelup = owned
            for mat_grade, mat_needed in total_materials_needed.items():
                available = inventory.duplicate_count.get(mat_grade, 0)
                if mat_needed > 0:
                    possible = available / mat_needed
                    items_can_levelup = min(items_can_levelup, possible)

            if items_can_levelup > 0:
                # 재료 소모
                materials_used = {}
                for mat_grade, mat_needed in total_materials_needed.items():
                    used = items_can_levelup * mat_needed
                    inventory.use_materials(mat_grade, used)
                    materials_used[mat_grade] = used

                results.append(LevelUpResult(
                    category=Category.CARD,
                    grade=grade,
                    items_leveled=items_can_levelup,
                    total_exp_used=0,
                    materials_used=materials_used
                ))

        return inventory, results


def process_spirit_levelup_then_synthesis(
    inventory: SpiritInventory,
    target_level: int = 5
) -> Tuple[SpiritInventory, List]:
    """
    투혼: 레벨업 후 합성 처리

    Args:
        inventory: 투혼 인벤토리
        target_level: 목표 레벨 (0~5, 기본값 5)

    Returns:
        (최종 인벤토리, 결과 리스트)
    """
    try:
        from simulator.synthesis_engine import synthesize_to_max
    except ImportError:
        from src.simulator.synthesis_engine import synthesize_to_max

    # 1. 레벨업 처리
    levelup_engine = SpiritLevelUpEngine(target_level=target_level)
    inventory, levelup_results = levelup_engine.process_levelup(inventory)

    # 2. 남은 재료로 합성
    inventory, synthesis_results = synthesize_to_max(inventory, Category.SPIRIT)

    return inventory, levelup_results + synthesis_results


def process_card_levelup_then_synthesis(
    inventory: Inventory,
    target_level: int = 5
) -> Tuple[Inventory, List]:
    """
    카드: 레벨업 후 합성 처리

    Args:
        inventory: 카드 인벤토리
        target_level: 목표 레벨 (0~5, 기본값 5)

    Returns:
        (최종 인벤토리, 결과 리스트)
    """
    try:
        from simulator.synthesis_engine import synthesize_to_max
    except ImportError:
        from src.simulator.synthesis_engine import synthesize_to_max

    # 1. 레벨업 처리
    levelup_engine = CardLevelUpEngine(target_level=target_level)
    inventory, levelup_results = levelup_engine.process_levelup(inventory)

    # 2. 남은 재료로 합성
    inventory, synthesis_results = synthesize_to_max(inventory, Category.CARD)

    return inventory, levelup_results + synthesis_results
