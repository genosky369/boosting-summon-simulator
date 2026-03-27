"""
합성 시뮬레이션 엔진
- 아이템 합성 시뮬레이션
- 천장 시스템 반영한 기대값 계산
- 클래스/펫: 최고 등급까지 자동 합성
- 투혼: 합성 포인트 기반 (레벨업 후 남는 재료로 합성)
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from copy import deepcopy

try:
    from data.constants import Grade, Category, GRADE_ORDER, CATEGORY_MAX_GRADE
    from data.loader import get_data_manager, SynthesisInfo
    from simulator.summon_engine import Inventory
except ImportError:
    import sys
    sys.path.insert(0, str(__file__).rsplit('src', 1)[0] + 'src')
    from data.constants import Grade, Category, GRADE_ORDER, CATEGORY_MAX_GRADE
    from data.loader import get_data_manager, SynthesisInfo
    from simulator.summon_engine import Inventory


@dataclass
class SynthesisResult:
    """합성 결과"""
    source_grade: Grade
    target_grade: Grade
    attempts: float  # 시도 횟수 (기대값)
    success_count: float  # 성공 횟수 (기대값)
    fail_count: float  # 실패 횟수 (기대값)
    materials_used: float  # 사용한 재료 개수


class SynthesisEngine:
    """합성 시뮬레이션 엔진"""

    def __init__(self):
        self.dm = get_data_manager()

    def calculate_expected_success_rate_with_pity(
        self,
        base_rate: float,
        pity_count: Optional[int]
    ) -> float:
        """
        천장을 반영한 기대 성공률 계산

        천장이 있을 경우, 평균 성공률은 순수 확률보다 높아짐.
        예: 10% 확률에 10회 천장이면, 최대 10번 안에 무조건 성공
        -> 평균 시도 횟수가 줄어들고, 기대 성공률이 올라감

        [계산 방식]
        천장 N회, 기본 성공률 p일 때:
        - k번째에 처음 성공할 확률: (1-p)^(k-1) * p (k < N)
        - N번째에 성공할 확률: (1-p)^(N-1) (천장)
        - 평균 시도 횟수 E = sum(k * P(k번째 성공)) for k=1 to N
        - 조정된 성공률 = 1 / E
        """
        if pity_count is None or pity_count <= 0:
            # 천장 없음: 순수 확률
            return base_rate

        p = base_rate
        q = 1 - p

        # 평균 시도 횟수 계산
        expected_attempts = 0

        for k in range(1, pity_count):
            # k번째에 처음 성공할 확률
            prob_first_success_at_k = (q ** (k - 1)) * p
            expected_attempts += k * prob_first_success_at_k

        # 천장에서 성공할 확률 (이전에 모두 실패)
        prob_pity = q ** (pity_count - 1)
        expected_attempts += pity_count * prob_pity

        # 조정된 성공률
        if expected_attempts > 0:
            adjusted_rate = 1 / expected_attempts
        else:
            adjusted_rate = base_rate

        return adjusted_rate

    def get_synthesis_info(self, category: Category, grade: Grade) -> Optional[SynthesisInfo]:
        """특정 등급의 합성 정보 가져오기"""
        return self.dm.get_synthesis_for_grade(category, grade)

    def calculate_synthesis_expected(
        self,
        category: Category,
        source_grade: Grade,
        material_count: float
    ) -> Tuple[float, float, float]:
        """
        합성 기대값 계산

        Args:
            category: 카테고리
            source_grade: 합성 대상 등급
            material_count: 사용 가능한 재료 개수

        Returns:
            (시도 횟수, 성공 개수, 실패 개수)
        """
        info = self.get_synthesis_info(category, source_grade)
        if info is None:
            return 0, 0, 0

        # 투혼은 별도 처리 (합성 포인트 기반)
        if category == Category.SPIRIT:
            return self._calculate_spirit_synthesis(source_grade, material_count)

        # 클래스/펫/카드: 재료 개수 기반
        materials_per_attempt = info.material_count
        if materials_per_attempt <= 0:
            return 0, 0, 0

        attempts = material_count / materials_per_attempt

        # 천장 반영 성공률
        adjusted_rate = self.calculate_expected_success_rate_with_pity(
            info.success_rate, info.pity_count
        )

        success_count = attempts * adjusted_rate
        fail_count = attempts * (1 - adjusted_rate)

        return attempts, success_count, fail_count

    def _calculate_spirit_synthesis(
        self,
        source_grade: Grade,
        material_count: float
    ) -> Tuple[float, float, float]:
        """
        투혼 합성 기대값 계산 (합성 포인트 기반)

        Args:
            source_grade: 합성 대상 등급 (영웅/고대/전설)
            material_count: 사용 가능한 재료 개수

        Returns:
            (시도 횟수, 성공 개수, 실패 개수)
        """
        info = self.dm.get_synthesis_for_grade(Category.SPIRIT, source_grade)
        if info is None:
            return 0, 0, 0

        required_points = info.material_points
        if required_points <= 0:
            return 0, 0, 0

        # 재료의 합성 포인트 계산
        # 여기서 material_count는 source_grade 등급의 중복 투혼 개수
        points_per_material = self.dm.spirit_synthesis_points.get(source_grade, 0)
        total_points = material_count * points_per_material

        # 합성 시도 횟수 (5% 이상 초과 시 합성 안 함 규칙은 UI에서 처리)
        attempts = total_points / required_points

        # 천장 반영 성공률
        adjusted_rate = self.calculate_expected_success_rate_with_pity(
            info.success_rate, info.pity_count
        )

        success_count = attempts * adjusted_rate
        fail_count = attempts * (1 - adjusted_rate)

        return attempts, success_count, fail_count

    def synthesize_all(
        self,
        inventory: Inventory,
        category: Category,
        max_grade: Optional[Grade] = None
    ) -> Tuple[Inventory, List[SynthesisResult]]:
        """
        모든 가능한 합성 수행 (최고 등급까지)

        클래스/펫용: 무조건 최고 등급까지 합성
        투혼: 낮은 등급 재료들을 모아 상위 등급 합성

        Args:
            inventory: 현재 인벤토리
            category: 카테고리
            max_grade: 최대 목표 등급 (None이면 카테고리 최대 등급)

        Returns:
            (업데이트된 인벤토리, 합성 결과 리스트)
        """
        if max_grade is None:
            max_grade = CATEGORY_MAX_GRADE.get(category, Grade.LEGENDARY)

        results = []
        inventory = deepcopy(inventory)

        if category == Category.SPIRIT:
            # 투혼: 합성 등급(목표 등급) 기준으로 처리
            # 낮은 목표 등급부터 처리 (영웅 → 고대 → 전설)
            for target_grade in [Grade.HERO, Grade.ANCIENT, Grade.LEGENDARY]:
                if GRADE_ORDER.index(target_grade) > GRADE_ORDER.index(max_grade):
                    break

                info = self.get_synthesis_info(category, target_grade)
                if info is None:
                    continue

                result = self._execute_spirit_synthesis(inventory, target_grade, info)
                if result:
                    results.append(result)
        else:
            # 클래스/펫/카드: 낮은 등급부터 순서대로 합성
            for grade in GRADE_ORDER:
                # 최대 등급에 도달하면 중단
                if grade == max_grade:
                    break

                # 현재 등급의 합성 정보 확인
                info = self.get_synthesis_info(category, grade)
                if info is None:
                    continue

                # 합성 가능한 재료 확인
                materials = inventory.get_materials(grade)
                if materials <= 0:
                    continue

                # 합성 실행
                result = self._execute_material_synthesis(inventory, grade, info)
                if result:
                    results.append(result)

        return inventory, results

    def _execute_material_synthesis(
        self,
        inventory: Inventory,
        grade: Grade,
        info: SynthesisInfo
    ) -> Optional[SynthesisResult]:
        """
        재료 개수 기반 합성 실행 (클래스/펫/카드)

        [중요] 실패 시 같은 등급 반환을 반영한 기대값 계산
        예: 고대 3개 → 성공 시 전설 1개, 실패 시 고대 1개
        - 성공 시 순 소모: 3개
        - 실패 시 순 소모: 3 - 1 = 2개

        재료 M개로 얻을 수 있는 성공 개수를 기대값으로 계산:
        - 1회 성공당 평균 시도 횟수: T = 1 / adjusted_rate
        - 1회 성공당 평균 순 소모량: (성공 시 소모) + (실패 횟수 × 실패 시 순 소모)
          = material_count + (T - 1) × (material_count - 1)
        - 총 성공 개수 = M / (1회 성공당 평균 순 소모량)
        """
        materials = inventory.get_materials(grade)
        materials_per_attempt = info.material_count

        if materials <= 0:
            return None

        # 천장 반영 성공률
        adjusted_rate = self.calculate_expected_success_rate_with_pity(
            info.success_rate, info.pity_count
        )

        # 실패 시 같은 등급이 반환되는 경우 (클래스/펫/카드의 일반적인 케이스)
        if info.fail_grade == grade:
            # 실패 시 반환되는 개수 (1개)
            fail_return = 1
            # 성공 시 순 소모량
            net_cost_success = materials_per_attempt
            # 실패 시 순 소모량
            net_cost_fail = materials_per_attempt - fail_return

            # 1회 성공당 평균 시도 횟수
            avg_attempts_per_success = 1 / adjusted_rate
            # 1회 성공당 평균 실패 횟수
            avg_fails_per_success = avg_attempts_per_success - 1

            # 1회 성공당 평균 순 소모량
            # = 성공 1회 소모 + 실패 횟수 × 실패 시 순 소모
            net_cost_per_success = net_cost_success + (avg_fails_per_success * net_cost_fail)

            # 총 성공 개수 (기대값)
            success_count = materials / net_cost_per_success

            # 총 시도 횟수 (기대값)
            attempts = success_count * avg_attempts_per_success
            fail_count = attempts - success_count

            # 실제 사용된 재료 = 전체 재료 (실패 반환분은 이미 계산에 포함)
            usable_materials = materials
        else:
            # 실패 시 다른 등급이 반환되는 경우 (기존 로직)
            usable_materials = materials
            attempts = usable_materials / materials_per_attempt
            success_count = attempts * adjusted_rate
            fail_count = attempts * (1 - adjusted_rate)

        # 재료 소모
        inventory.use_materials(grade, usable_materials)

        # 성공/실패 결과 적용 (add_items로 도감 완성도도 업데이트)
        if success_count > 0:
            # 성공 시 상위 등급 획득 -> add_items로 추가 (도감 + 중복분 계산)
            type_count = inventory._type_counts.get(info.success_grade, 0)
            inventory.add_items(info.success_grade, success_count, type_count)

        if fail_count > 0 and info.fail_grade != grade:
            # 실패 시 다른 등급 획득하는 경우만 추가
            # (같은 등급 반환은 위의 net_cost 계산에서 이미 반영됨)
            type_count = inventory._type_counts.get(info.fail_grade, 0)
            inventory.add_items(info.fail_grade, fail_count, type_count)

        return SynthesisResult(
            source_grade=grade,
            target_grade=info.success_grade,
            attempts=attempts,
            success_count=success_count,
            fail_count=fail_count,
            materials_used=usable_materials
        )

    def _execute_spirit_synthesis(
        self,
        inventory: Inventory,
        target_grade: Grade,
        info: SynthesisInfo
    ) -> Optional[SynthesisResult]:
        """
        투혼 합성 실행 (합성 포인트 기반)

        [투혼 합성 규칙]
        - 합성 등급(target_grade)은 성공 시 획득하는 등급
        - 재료는 합성 등급보다 낮은 모든 등급 사용 가능
          예: 영웅 합성 → 일반/고급/희귀 재료 사용
          예: 고대 합성 → 일반/고급/희귀/영웅 재료 사용
          예: 전설 합성 → 일반/고급/희귀/영웅/고대 재료 사용
        - 각 등급의 합성 재료 포인트를 합산하여 합성 시도
        """
        required_points = info.material_points
        if required_points <= 0:
            return None

        # 목표 등급보다 낮은 등급들의 재료를 모두 수집
        target_index = GRADE_ORDER.index(target_grade)
        total_points = 0
        materials_used_by_grade = {}

        for mat_grade in GRADE_ORDER[:target_index]:
            # 불멸 등급은 투혼에 없음
            if mat_grade == Grade.IMMORTAL:
                continue

            materials = inventory.get_materials(mat_grade)
            if materials <= 0:
                continue

            points_per_material = self.dm.spirit_synthesis_points.get(mat_grade, 0)
            if points_per_material <= 0:
                continue

            grade_points = materials * points_per_material
            total_points += grade_points
            materials_used_by_grade[mat_grade] = materials

        if total_points <= 0:
            return None

        # 합성 가능 횟수 (기대값 기반: 소수점 허용)
        attempts = total_points / required_points
        if attempts <= 0:
            return None

        # 기대값 계산
        adjusted_rate = self.calculate_expected_success_rate_with_pity(
            info.success_rate, info.pity_count
        )
        success_count = attempts * adjusted_rate
        fail_count = attempts * (1 - adjusted_rate)

        # 재료 소모 (모든 등급)
        total_materials_used = 0
        for mat_grade, mat_count in materials_used_by_grade.items():
            inventory.use_materials(mat_grade, mat_count)
            total_materials_used += mat_count

        # 성공 시 목표 등급 획득
        if success_count > 0:
            type_count = inventory._type_counts.get(info.success_grade, 0)
            inventory.add_items(info.success_grade, success_count, type_count)

        # 실패 시 하위 등급 획득
        if fail_count > 0 and info.fail_grade:
            type_count = inventory._type_counts.get(info.fail_grade, 0)
            inventory.add_items(info.fail_grade, fail_count, type_count)

        return SynthesisResult(
            source_grade=target_grade,  # 합성 등급 (목표 등급)
            target_grade=info.success_grade,
            attempts=attempts,
            success_count=success_count,
            fail_count=fail_count,
            materials_used=total_materials_used
        )


def synthesize_to_max(
    inventory: Inventory,
    category: Category
) -> Tuple[Inventory, List[SynthesisResult]]:
    """
    편의 함수: 최고 등급까지 모든 합성 수행

    Args:
        inventory: 현재 인벤토리
        category: 카테고리

    Returns:
        (최종 인벤토리, 합성 결과 리스트)

    [수정됨] 실패 보상이 재료로 재사용되는 무한 루프 방지
    - 투혼: 합성 1회만 실행 (실패 보상은 결과에만 반영, 재료로 재사용 안 함)
    - 클래스/펫/카드: 기존처럼 반복 (실패 시 같은 등급이므로 문제 없음)
    """
    engine = SynthesisEngine()

    # 투혼은 합성 1회만 실행 (실패 보상 재사용 방지)
    if category == Category.SPIRIT:
        inventory, results = engine.synthesize_all(inventory, category)
        return inventory, results

    # 클래스/펫/카드: 합성이 더 이상 진행되지 않을 때까지 반복
    all_results = []
    max_iterations = 100  # 무한 루프 방지

    for _ in range(max_iterations):
        inventory, results = engine.synthesize_all(inventory, category)
        all_results.extend(results)

        # 변화가 없으면 종료
        if not results:
            break

    return inventory, all_results
