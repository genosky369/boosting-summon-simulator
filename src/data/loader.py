"""
데이터 로더 모듈
- 엑셀 파일에서 데이터를 로드하여 파이썬 객체로 변환
- 기획 데이터 변경 시 엑셀만 수정하면 자동 반영
"""

import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from .constants import Grade, Category, GRADE_CODE_MAP, GRADE_NAME_MAP

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent


# =============================================================================
# 데이터 클래스 정의
# =============================================================================

@dataclass
class SummonTicket:
    """소환권 정보"""
    category: Category
    name: str
    probabilities: Dict[Grade, float]  # 등급별 확률
    pulls_per_ticket: int = 11  # 소환권 1개당 뽑기 횟수 (기본 11회)


@dataclass
class SynthesisInfo:
    """합성 정보"""
    category: Category
    source_grade: Grade  # 합성 대상 등급
    material_count: int  # 필요 재료 개수 (클래스/펫/카드)
    material_points: int = 0  # 필요 합성 포인트 (투혼)
    success_rate: float = 0.0  # 성공 확률
    success_grade: Grade = None  # 성공 시 등급
    fail_grade: Grade = None  # 실패 시 등급
    pity_count: Optional[int] = None  # 천장 횟수 (None이면 천장 없음)


@dataclass
class LevelUpInfo:
    """레벨업 정보 (투혼/카드)"""
    category: Category
    grade: Grade
    start_level: int
    target_level: int
    required_exp: int


@dataclass
class SpiritLevelUpPoint:
    """투혼 레벨업 포인트 정보"""
    grade: Grade
    point: int  # 기본 포인트 (동일 투혼 시 2배)


@dataclass
class SpiritSynthesisPoint:
    """투혼 합성 포인트 정보"""
    grade: Grade
    point: int


@dataclass
class ItemTypeCount:
    """아이템 종류 개수"""
    category: Category
    grade: Grade
    count: int


# =============================================================================
# 데이터 로더 클래스
# =============================================================================

class DataLoader:
    """엑셀 데이터 로더"""

    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path or PROJECT_ROOT
        self._cache = {}

    def _read_excel(self, filename: str) -> pd.DataFrame:
        """엑셀 파일 읽기 (캐싱)"""
        if filename not in self._cache:
            filepath = self.data_path / filename
            self._cache[filename] = pd.read_excel(filepath)
        return self._cache[filename]

    def load_summon_tickets(self) -> List[SummonTicket]:
        """소환권 확률 데이터 로드"""
        df = self._read_excel("소환권 타입/소환권 확률.xlsx")
        tickets = []

        for _, row in df.iterrows():
            category = Category(row["카테고리"])
            name = row["소환권 이름"]

            # 확률 파싱
            probabilities = {}
            for grade_name, grade in GRADE_NAME_MAP.items():
                if grade_name in df.columns:
                    prob = row[grade_name]
                    if prob > 0:
                        probabilities[grade] = prob

            # 11회 소환권인지 확인
            pulls = 11 if "11회" in name else 1

            tickets.append(SummonTicket(
                category=category,
                name=name,
                probabilities=probabilities,
                pulls_per_ticket=pulls
            ))

        return tickets

    def load_synthesis_info(self, category: Category) -> List[SynthesisInfo]:
        """합성 확률 데이터 로드"""
        filename_map = {
            Category.CLASS: "클래스 합성 확률.xlsx",
            Category.PET: "펫 합성 확률.xlsx",
            Category.SPIRIT: "투혼 합성 확률.xlsx",
            Category.CARD: "카드 합성 확률.xlsx",
        }

        df = self._read_excel(filename_map[category])
        infos = []

        for _, row in df.iterrows():
            source_grade = GRADE_NAME_MAP[row["합성 등급"]]

            # 투혼은 합성 포인트, 나머지는 재료 개수
            if category == Category.SPIRIT:
                material_count = 0
                material_points = int(row["합성 포인트"])
            else:
                material_count = int(row["합성 재료 개수"])
                material_points = 0

            pity = row.get("천장 횟수")
            pity_count = int(pity) if pd.notna(pity) else None

            infos.append(SynthesisInfo(
                category=category,
                source_grade=source_grade,
                material_count=material_count,
                material_points=material_points,
                success_rate=float(row["성공 확률"]),
                success_grade=GRADE_NAME_MAP[row["성공 시 등급"]],
                fail_grade=GRADE_NAME_MAP[row["실패 시 등급"]],
                pity_count=pity_count
            ))

        return infos

    def load_item_type_counts(self, category: Category) -> Dict[Grade, int]:
        """아이템 종류별 개수 로드"""
        filename_map = {
            Category.CLASS: "클래스 종류.xlsx",
            Category.PET: "펫 종류.xlsx",
            Category.SPIRIT: "투혼 종류.xlsx",
            Category.CARD: "카드 종류.xlsx",
        }

        if category not in filename_map:
            return {}

        df = self._read_excel(filename_map[category])
        counts = {}

        # 한글 등급명으로 카운트
        for grade_name, grade in GRADE_NAME_MAP.items():
            count = len(df[df["등급"] == grade_name])
            if count > 0:
                counts[grade] = count

        return counts

    def load_spirit_levelup_info(self) -> List[LevelUpInfo]:
        """투혼 레벨업 정보 로드"""
        df = self._read_excel("투혼 레벨업.xlsx")
        infos = []

        for _, row in df.iterrows():
            infos.append(LevelUpInfo(
                category=Category.SPIRIT,
                grade=GRADE_NAME_MAP[row["등급"]],
                start_level=int(row["시작 레벨"]),
                target_level=int(row["달성 레벨"]),
                required_exp=int(row["경험치"])
            ))

        return infos

    def load_spirit_levelup_points(self) -> Dict[Grade, int]:
        """투혼 레벨업 포인트 로드"""
        df = self._read_excel("투혼 레벨업 포인트.xlsx")
        points = {}

        for _, row in df.iterrows():
            grade_name = row["등급"]
            # 등급 이름만 처리 (보물사냥꾼 등 특수 소환권 제외)
            if grade_name in GRADE_NAME_MAP:
                grade = GRADE_NAME_MAP[grade_name]
                points[grade] = int(row["레벨업 재료 포인트"])

        return points

    def load_treasure_hunter_levelup_points(self) -> Dict[str, int]:
        """보물사냥꾼 레벨업 포인트 로드"""
        df = self._read_excel("투혼 레벨업 포인트.xlsx")
        points = {}

        for _, row in df.iterrows():
            grade_name = row["등급"]
            # 보물사냥꾼만 처리
            if "보물사냥꾼" in grade_name:
                points[grade_name] = int(row["레벨업 재료 포인트"])

        return points

    def load_spirit_synthesis_points(self) -> Dict[Grade, int]:
        """투혼 합성 포인트 로드"""
        df = self._read_excel("투혼 합성 포인트.xlsx")
        points = {}

        for _, row in df.iterrows():
            grade = GRADE_NAME_MAP[row["등급"]]
            points[grade] = int(row["합성 재료 포인트"])

        return points

    def load_card_levelup_info(self) -> List[Dict]:
        """카드 레벨업 정보 로드"""
        df = self._read_excel("카드 레벨업.xlsx")
        infos = []

        for _, row in df.iterrows():
            infos.append({
                "category": Category.CARD,
                "grade": GRADE_NAME_MAP[row["등급"]],
                "start_level": int(row["시작 레벨"]),
                "target_level": int(row["달성 레벨"]),
                "material_grade": GRADE_NAME_MAP[row["재료 등급"]],
                "material_count": float(row["재료 개수"])
            })

        return infos


# =============================================================================
# 데이터 매니저 (싱글톤 패턴)
# =============================================================================

class DataManager:
    """데이터 관리 매니저 (싱글톤)"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, data_path: Optional[Path] = None):
        if DataManager._initialized:
            return

        self.loader = DataLoader(data_path)
        self._load_all_data()
        DataManager._initialized = True

    def _load_all_data(self):
        """모든 데이터 로드"""
        # 소환권 데이터
        self.summon_tickets = self.loader.load_summon_tickets()
        self.summon_tickets_by_category = self._group_tickets_by_category()

        # 합성 데이터
        self.synthesis_info = {
            cat: self.loader.load_synthesis_info(cat)
            for cat in Category
        }

        # 아이템 종류 개수
        self.item_counts = {
            Category.CLASS: self.loader.load_item_type_counts(Category.CLASS),
            Category.PET: self.loader.load_item_type_counts(Category.PET),
            Category.SPIRIT: self.loader.load_item_type_counts(Category.SPIRIT),
            Category.CARD: self.loader.load_item_type_counts(Category.CARD),
        }
        # 불멸 클래스 종류 수 (Excel에 없으므로 전설과 동일하게 설정)
        if Grade.IMMORTAL not in self.item_counts.get(Category.CLASS, {}):
            legend_count = self.item_counts.get(Category.CLASS, {}).get(Grade.LEGENDARY, 28)
            self.item_counts[Category.CLASS][Grade.IMMORTAL] = legend_count

        # 투혼 레벨업/합성 포인트
        self.spirit_levelup_info = self.loader.load_spirit_levelup_info()
        self.spirit_levelup_points = self.loader.load_spirit_levelup_points()
        self.spirit_synthesis_points = self.loader.load_spirit_synthesis_points()
        self.treasure_hunter_levelup_points = self.loader.load_treasure_hunter_levelup_points()

        # 카드 레벨업 정보
        self.card_levelup_info = self.loader.load_card_levelup_info()

    def _group_tickets_by_category(self) -> Dict[Category, List[SummonTicket]]:
        """카테고리별 소환권 그룹화"""
        grouped = {cat: [] for cat in Category}
        for ticket in self.summon_tickets:
            grouped[ticket.category].append(ticket)
        return grouped

    def get_tickets_for_category(self, category: Category) -> List[SummonTicket]:
        """특정 카테고리의 소환권 목록"""
        return self.summon_tickets_by_category.get(category, [])

    def get_ticket_by_name(self, name: str) -> Optional[SummonTicket]:
        """이름으로 소환권 찾기"""
        for ticket in self.summon_tickets:
            if ticket.name == name:
                return ticket
        return None

    def get_synthesis_for_grade(self, category: Category, grade: Grade) -> Optional[SynthesisInfo]:
        """특정 등급의 합성 정보"""
        for info in self.synthesis_info[category]:
            if info.source_grade == grade:
                return info
        return None

    def get_item_count(self, category: Category, grade: Grade) -> int:
        """특정 카테고리/등급의 아이템 종류 개수"""
        return self.item_counts.get(category, {}).get(grade, 0)

    def reload_data(self):
        """데이터 새로고침 (엑셀 파일 변경 시 호출)"""
        self.loader._cache.clear()  # 캐시 클리어
        self._load_all_data()

    @classmethod
    def reset_instance(cls):
        """싱글톤 인스턴스 초기화 (테스트/새로고침용)"""
        cls._instance = None
        cls._initialized = False


# 전역 데이터 매니저 인스턴스
def get_data_manager(data_path: Optional[Path] = None) -> DataManager:
    """데이터 매니저 인스턴스 가져오기"""
    return DataManager(data_path)


def reload_data_manager() -> DataManager:
    """데이터 매니저 새로고침 (엑셀 변경 반영)"""
    DataManager.reset_instance()
    return DataManager()
