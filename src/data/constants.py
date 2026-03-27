"""
상수 정의 모듈
- 등급, 카테고리, 부스팅 일정 등 상수 정의
- 기획 변경 시 이 파일만 수정하면 됨
"""

from enum import Enum
from typing import Dict, List
from datetime import date

# =============================================================================
# 등급 정의
# =============================================================================

class Grade(Enum):
    """아이템 등급"""
    NORMAL = "일반"      # GRADE1
    ADVANCED = "고급"    # GRADE2
    RARE = "희귀"        # GRADE3
    HERO = "영웅"        # GRADE4
    ANCIENT = "고대"     # GRADE5
    LEGENDARY = "전설"   # GRADE6
    IMMORTAL = "불멸"    # GRADE7 (펫 전용)

# 등급 순서 (낮은 등급 → 높은 등급)
GRADE_ORDER = [
    Grade.NORMAL,
    Grade.ADVANCED,
    Grade.RARE,
    Grade.HERO,
    Grade.ANCIENT,
    Grade.LEGENDARY,
    Grade.IMMORTAL,
]

# 등급 코드 매핑 (엑셀 데이터용)
GRADE_CODE_MAP = {
    "GRADE1": Grade.NORMAL,
    "GRADE2": Grade.ADVANCED,
    "GRADE3": Grade.RARE,
    "GRADE4": Grade.HERO,
    "GRADE5": Grade.ANCIENT,
    "GRADE6": Grade.LEGENDARY,
    "GRADE7": Grade.IMMORTAL,
}

# 등급 한글명 매핑
GRADE_NAME_MAP = {
    "일반": Grade.NORMAL,
    "고급": Grade.ADVANCED,
    "희귀": Grade.RARE,
    "영웅": Grade.HERO,
    "고대": Grade.ANCIENT,
    "전설": Grade.LEGENDARY,
    "불멸": Grade.IMMORTAL,
}

# =============================================================================
# 카테고리 정의
# =============================================================================

class Category(Enum):
    """아이템 카테고리"""
    CLASS = "클래스"
    PET = "펫"
    SPIRIT = "투혼"
    CARD = "카드"

# 카테고리별 최대 등급
CATEGORY_MAX_GRADE = {
    Category.CLASS: Grade.LEGENDARY,
    Category.PET: Grade.IMMORTAL,
    Category.SPIRIT: Grade.LEGENDARY,
    Category.CARD: Grade.LEGENDARY,
}

# =============================================================================
# 부스팅 일정
# =============================================================================

BOOSTING_SCHEDULE = {
    1: date(2026, 5, 27),
    2: date(2026, 6, 3),
    3: date(2026, 6, 10),
    4: date(2026, 6, 17),
    5: date(2026, 6, 24),
    6: date(2026, 7, 1),
    7: date(2026, 7, 8),
    8: date(2026, 7, 15),
    9: date(2026, 7, 22),
    10: date(2026, 7, 29),
}

TOTAL_WEEKS = 10

# =============================================================================
# 기본 목표 스펙 (변경 가능)
# =============================================================================

DEFAULT_TARGET_SPEC = {
    Category.CLASS: {Grade.LEGENDARY: 10},
    Category.PET: {Grade.LEGENDARY: 8, Grade.IMMORTAL: 2},
    Category.SPIRIT: {Grade.LEGENDARY: 2},
    Category.CARD: {},  # 미정
}

# 목표 오차 허용 범위
TARGET_TOLERANCE = 0.1  # ±10%

# =============================================================================
# 소환권 타입
# =============================================================================

class SummonType(Enum):
    """소환권 타입"""
    BRILLIANT = "찬란한"      # 일반 위주
    MYSTERIOUS = "신비로운"   # 고급 위주
    DAZZLING = "눈부신"       # 희귀 위주
    RADIANT = "영롱한"        # 희귀~고대 혼합
    HERO_CHALLENGE = "영웅 도전"
    HERO_CONFIRM = "영웅 확정"
    HERO_SELECT = "영웅 선택"
    ANCIENT_CHALLENGE = "고대 도전"
    ANCIENT_CONFIRM = "고대 확정"
    ANCIENT_SELECT = "고대 선택"
    LEGENDARY_CHALLENGE = "전설 도전"
    LEGENDARY_CONFIRM = "전설 확정"
    LEGENDARY_SELECT = "전설 선택"  # 계시자의 전설 클래스 선택 소환권
    HERO_CLASS_PET_SELECT = "영웅 클래스/펫 선택"
    ANCIENT_CLASS_PET_SELECT = "고대 클래스/펫 선택"

# 특수 소환권 (투혼 전용 - 보물사냥꾼)
class SpecialSummonType(Enum):
    """특수 소환권 타입 (보물사냥꾼)"""
    TREASURE_HUNTER_BEGINNER = "미숙한 보물사냥꾼"
    TREASURE_HUNTER_SKILLED = "숙달된 보물사냥꾼"
    TREASURE_HUNTER_PROFICIENT = "능숙한 보물사냥꾼"
    TREASURE_HUNTER_VETERAN = "노련한 보물사냥꾼"
    TREASURE_HUNTER_GREAT = "대단한 보물사냥꾼"
    TREASURE_HUNTER_PERFECT = "완벽한 보물사냥꾼"
