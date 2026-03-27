"""
부스팅 소환권 시뮬레이터 - Streamlit 앱
"""

import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
import sys

# 프로젝트 경로 설정
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data.constants import (
    Category, Grade, GRADE_ORDER, BOOSTING_SCHEDULE,
    TOTAL_WEEKS, DEFAULT_TARGET_SPEC
)
from data.loader import get_data_manager, reload_data_manager
from simulator.main_engine import MainSimulationEngine, SimulationState
from simulator.allocation_calculator import AllocationCalculator

# =============================================================================
# 페이지 설정
# =============================================================================

st.set_page_config(
    page_title="부스팅 소환권 시뮬레이터",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# 세션 상태 초기화
# =============================================================================

def init_session_state():
    """세션 상태 초기화"""
    if "engine" not in st.session_state:
        st.session_state.engine = MainSimulationEngine()

    if "state" not in st.session_state:
        st.session_state.state = st.session_state.engine.create_initial_state()

    if "dm" not in st.session_state:
        st.session_state.dm = get_data_manager()

    if "alloc_calc" not in st.session_state:
        st.session_state.alloc_calc = AllocationCalculator()

init_session_state()

# =============================================================================
# 사이드바 - 목표 스펙 설정
# =============================================================================

st.sidebar.title("목표 스펙 설정")

st.sidebar.markdown("---")

# 클래스 목표
st.sidebar.subheader("클래스")
class_legendary = st.sidebar.number_input(
    "전설 클래스 목표",
    min_value=0, max_value=50, value=10,
    key="class_legendary"
)

st.sidebar.markdown("---")

# 펫 목표
st.sidebar.subheader("펫")
pet_legendary = st.sidebar.number_input(
    "전설 펫 목표",
    min_value=0, max_value=50, value=8,
    key="pet_legendary"
)
pet_immortal = st.sidebar.number_input(
    "불멸 펫 목표",
    min_value=0, max_value=10, value=2,
    key="pet_immortal"
)

st.sidebar.markdown("---")

# 투혼 목표
st.sidebar.subheader("투혼")
spirit_legendary = st.sidebar.number_input(
    "전설 투혼 목표",
    min_value=0, max_value=20, value=2,
    key="spirit_legendary"
)
spirit_target_level = st.sidebar.selectbox(
    "투혼 레벨업 목표",
    options=[0, 1, 2, 3, 4, 5],
    index=5,
    format_func=lambda x: f"{x}레벨" if x > 0 else "레벨업 안 함",
    key="spirit_target_level",
    help="투혼을 몇 레벨까지 올릴지 선택합니다. 레벨업에 사용되지 않은 재료는 합성에 사용됩니다."
)

st.sidebar.markdown("---")

# 카드 목표
st.sidebar.subheader("카드")
card_legendary = st.sidebar.number_input(
    "전설 카드 목표",
    min_value=0, max_value=50, value=0,
    key="card_legendary"
)
card_target_level = st.sidebar.selectbox(
    "카드 레벨업 목표",
    options=[0, 1, 2, 3, 4, 5],
    index=5,
    format_func=lambda x: f"{x}레벨" if x > 0 else "레벨업 안 함",
    key="card_target_level",
    help="카드를 몇 레벨까지 올릴지 선택합니다. 레벨업에 사용되지 않은 재료는 합성에 사용됩니다."
)

# 목표 스펙 업데이트 버튼
if st.sidebar.button("목표 스펙 적용", type="primary"):
    new_target = {
        Category.CLASS: {Grade.LEGENDARY: class_legendary},
        Category.PET: {Grade.LEGENDARY: pet_legendary, Grade.IMMORTAL: pet_immortal},
        Category.SPIRIT: {Grade.LEGENDARY: spirit_legendary},
        Category.CARD: {Grade.LEGENDARY: card_legendary} if card_legendary > 0 else {},
    }
    st.session_state.state.target_spec = new_target
    # 레벨업 목표 적용
    st.session_state.state.spirit_target_level = spirit_target_level
    st.session_state.state.card_target_level = card_target_level
    # 배분 계산기 업데이트
    st.session_state.alloc_calc = AllocationCalculator(
        spirit_target_level=spirit_target_level,
        card_target_level=card_target_level
    )
    st.sidebar.success("목표 스펙이 적용되었습니다!")

# =============================================================================
# 메인 영역
# =============================================================================

st.title("부스팅 소환권 시뮬레이터")

st.markdown("""
이 시뮬레이터는 부스팅 서버에서 소환권 배분 계획을 세우는 데 도움을 줍니다.
- 주차별로 소환권을 입력하면 예상 결과를 확인할 수 있습니다.
- 목표 스펙 대비 진행률을 추적합니다.
""")

# 탭 구성
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 소환권 입력", "📊 시뮬레이션 결과", "📈 진행률 추이", "🧮 배분 계산기", "💾 저장/불러오기"])

# =============================================================================
# 탭 1: 소환권 입력
# =============================================================================

with tab1:
    st.header("주차별 소환권 입력")

    # 주차 선택
    col1, col2 = st.columns([1, 3])
    with col1:
        selected_week = st.selectbox(
            "주차 선택",
            options=list(range(1, TOTAL_WEEKS + 1)),
            format_func=lambda x: f"{x}주차 ({BOOSTING_SCHEDULE[x].strftime('%Y-%m-%d')})"
        )

    st.markdown("---")

    # 카테고리별 소환권 입력
    st.subheader(f"{selected_week}주차 소환권 배분")

    # 현재 주차의 입력값 가져오기
    current_input = st.session_state.state.weekly_inputs.get(selected_week)
    current_tickets = current_input.tickets if current_input else {cat: [] for cat in Category}

    # 카테고리 선택
    category_names = {
        Category.CLASS: "클래스",
        Category.PET: "펫",
        Category.SPIRIT: "투혼",
        Category.CARD: "카드"
    }

    selected_category = st.selectbox(
        "카테고리 선택",
        options=list(Category),
        format_func=lambda x: category_names[x]
    )

    # 해당 카테고리의 소환권 목록
    available_tickets = st.session_state.dm.get_tickets_for_category(selected_category)
    ticket_names = [t.name for t in available_tickets]

    # 소환권 선택 및 수량 입력
    col1, col2 = st.columns([3, 1])
    with col1:
        selected_ticket = st.selectbox(
            "소환권 선택",
            options=ticket_names if ticket_names else ["(소환권 없음)"],
            key=f"ticket_select_{selected_week}_{selected_category.value}"
        )
    with col2:
        ticket_count = st.number_input(
            "수량",
            min_value=0, max_value=1000, value=0,
            key=f"ticket_count_{selected_week}_{selected_category.value}"
        )

    # 소환권 추가 버튼
    if st.button("소환권 추가", key=f"add_ticket_{selected_week}"):
        if ticket_count > 0 and selected_ticket and selected_ticket != "(소환권 없음)":
            # 기존 입력에 추가
            if selected_week not in st.session_state.state.weekly_inputs:
                from simulator.main_engine import WeeklyInput
                st.session_state.state.weekly_inputs[selected_week] = WeeklyInput(
                    week=selected_week,
                    date=BOOSTING_SCHEDULE[selected_week],
                    tickets={cat: [] for cat in Category}
                )

            week_input = st.session_state.state.weekly_inputs[selected_week]

            # 같은 소환권이 있으면 수량 추가
            found = False
            for i, (name, count) in enumerate(week_input.tickets[selected_category]):
                if name == selected_ticket:
                    week_input.tickets[selected_category][i] = (name, count + ticket_count)
                    found = True
                    break

            if not found:
                week_input.tickets[selected_category].append((selected_ticket, ticket_count))

            st.success(f"{selected_ticket} x {ticket_count}개 추가됨!")
            st.rerun()

    # 현재 주차 입력 현황
    st.markdown("---")
    st.subheader(f"{selected_week}주차 입력 현황")

    if selected_week in st.session_state.state.weekly_inputs:
        week_input = st.session_state.state.weekly_inputs[selected_week]
        has_input = False

        for cat in Category:
            tickets = week_input.tickets.get(cat, [])
            if tickets:
                has_input = True
                st.markdown(f"**{category_names[cat]}**")
                for name, count in tickets:
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.write(f"- {name}: {count}개")
                    with col2:
                        if st.button("삭제", key=f"del_{selected_week}_{cat.value}_{name}"):
                            week_input.tickets[cat] = [(n, c) for n, c in week_input.tickets[cat] if n != name]
                            st.rerun()

        if not has_input:
            st.info("입력된 소환권이 없습니다.")
    else:
        st.info("입력된 소환권이 없습니다.")

    # 시뮬레이션 실행 버튼
    st.markdown("---")
    if st.button("시뮬레이션 실행", type="primary", key="run_sim"):
        with st.spinner("시뮬레이션 실행 중..."):
            st.session_state.state = st.session_state.engine.simulate_all(st.session_state.state)
        st.session_state.sim_completed = True
        st.rerun()

    # 시뮬레이션 완료 메시지
    if st.session_state.get("sim_completed"):
        st.success("시뮬레이션 완료!")
        st.session_state.sim_completed = False

# =============================================================================
# 탭 2: 시뮬레이션 결과
# =============================================================================

with tab2:
    st.header("시뮬레이션 결과")

    # 현재 상태 요약
    summary = st.session_state.engine.get_summary(st.session_state.state)

    # 목표 스펙
    st.subheader("목표 스펙")
    target_cols = st.columns(4)
    for i, (cat, targets) in enumerate(summary["target_spec"].items()):
        with target_cols[i]:
            st.markdown(f"**{cat}**")
            if targets:
                for grade, count in targets.items():
                    st.write(f"- {grade}: {count}개")
            else:
                st.write("(미설정)")

    st.markdown("---")

    # 도감 완성도
    st.subheader("도감 완성도")
    collection_cols = st.columns(4)

    for i, cat in enumerate(Category):
        with collection_cols[i]:
            st.markdown(f"**{category_names[cat]}**")
            inv = st.session_state.state.current_inventories.get(cat)
            if inv and hasattr(inv, 'get_collection_status'):
                has_data = False
                for grade in GRADE_ORDER:
                    owned, total = inv.get_collection_status(grade)
                    if total > 0:
                        has_data = True
                        pct = (owned / total * 100) if total > 0 else 0
                        st.write(f"- {grade.value}: {owned:.1f}/{total} ({pct:.1f}%)")
                if not has_data:
                    st.write("(데이터 없음)")
            else:
                st.write("(없음)")

    st.markdown("---")

    # 현재 보유 현황 (합성 후 중복분)
    st.subheader("합성 후 남은 중복분")
    status_cols = st.columns(4)

    for i, cat in enumerate(Category):
        with status_cols[i]:
            st.markdown(f"**{category_names[cat]}**")
            inv = st.session_state.state.current_inventories.get(cat)
            if inv:
                has_items = False
                for grade in GRADE_ORDER:
                    count = inv.duplicate_count.get(grade, 0)
                    if count > 0.01:
                        has_items = True
                        st.write(f"- {grade.value}: {count:.2f}개")
                if not has_items:
                    st.write("(없음)")
            else:
                st.write("(없음)")

    st.markdown("---")

    # 진행률
    st.subheader("목표 대비 진행률")
    progress_cols = st.columns(4)

    for i, (cat, progress) in enumerate(summary["progress"].items()):
        with progress_cols[i]:
            st.markdown(f"**{cat}**")
            if progress:
                for grade, rate in progress.items():
                    rate_val = float(rate.replace("%", ""))
                    st.progress(min(rate_val / 100, 1.0), text=f"{grade}: {rate}")
            else:
                st.write("(목표 미설정)")

# =============================================================================
# 탭 3: 진행률 추이
# =============================================================================

with tab3:
    st.header("주차별 진행률 추이")

    # 주차별 기여도
    st.subheader("주차별 목표 대비 기여도")

    if st.session_state.state.weekly_results:
        # 데이터 준비
        weeks = []
        class_contrib = []
        pet_contrib = []
        spirit_contrib = []
        card_contrib = []

        for week in sorted(st.session_state.state.weekly_results.keys()):
            result = st.session_state.state.weekly_results[week]
            weeks.append(f"{week}주차")
            class_contrib.append(result.weekly_contribution.get(Category.CLASS, 0) * 100)
            pet_contrib.append(result.weekly_contribution.get(Category.PET, 0) * 100)
            spirit_contrib.append(result.weekly_contribution.get(Category.SPIRIT, 0) * 100)
            card_contrib.append(result.weekly_contribution.get(Category.CARD, 0) * 100)

        # 차트 데이터
        chart_data = pd.DataFrame({
            "주차": weeks,
            "클래스": class_contrib,
            "펫": pet_contrib,
            "투혼": spirit_contrib,
            "카드": card_contrib
        })
        chart_data = chart_data.set_index("주차")

        st.bar_chart(chart_data)

        # 누적 진행률
        st.subheader("누적 진행률")
        cumulative_class = []
        cumulative_pet = []
        cumulative_spirit = []
        cumulative_card = []

        total = {cat: 0 for cat in Category}
        for week in sorted(st.session_state.state.weekly_results.keys()):
            result = st.session_state.state.weekly_results[week]
            for cat in Category:
                total[cat] += result.weekly_contribution.get(cat, 0) * 100

            cumulative_class.append(total[Category.CLASS])
            cumulative_pet.append(total[Category.PET])
            cumulative_spirit.append(total[Category.SPIRIT])
            cumulative_card.append(total[Category.CARD])

        cum_data = pd.DataFrame({
            "주차": weeks,
            "클래스": cumulative_class,
            "펫": cumulative_pet,
            "투혼": cumulative_spirit,
            "카드": cumulative_card
        })
        cum_data = cum_data.set_index("주차")

        st.line_chart(cum_data)

    else:
        st.info("시뮬레이션을 실행해주세요.")

# =============================================================================
# 탭 4: 배분 계산기
# =============================================================================

with tab4:
    st.header("소환권 배분 계산기")

    # 데이터 새로고침 버튼
    col_refresh, col_info = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 데이터 새로고침", key="refresh_data"):
            st.session_state.dm = reload_data_manager()
            st.session_state.alloc_calc = AllocationCalculator(
                spirit_target_level=st.session_state.get("spirit_target_level", 5),
                card_target_level=st.session_state.get("card_target_level", 5)
            )
            st.success("엑셀 데이터가 새로고침되었습니다!")
            st.rerun()
    with col_info:
        st.caption("엑셀 파일(소환권 확률 등) 수정 후 이 버튼을 눌러주세요.")

    st.markdown("""
    목표 달성을 위해 각 소환권을 몇 개씩 사용해야 하는지 계산합니다.
    - **기여도 비율**을 입력하면 필요한 소환권 개수를 계산합니다.
    - 예: 고대 10개 목표, 찬란한 50%, 영롱한 50% → 찬란한으로 5개, 영롱한으로 5개 얻는데 필요한 소환권 수
    """)

    st.markdown("---")

    # 카테고리 선택
    alloc_category = st.selectbox(
        "카테고리 선택",
        options=list(Category),
        format_func=lambda x: category_names[x],
        key="alloc_category"
    )

    # 목표 등급 선택 (카테고리별 달성 가능한 등급)
    grade_options = {
        Category.CLASS: [Grade.ANCIENT, Grade.LEGENDARY],
        Category.PET: [Grade.ANCIENT, Grade.LEGENDARY, Grade.IMMORTAL],
        Category.SPIRIT: [Grade.ANCIENT, Grade.LEGENDARY],
        Category.CARD: [Grade.HERO, Grade.ANCIENT, Grade.LEGENDARY],
    }
    available_grades = grade_options.get(alloc_category, [Grade.LEGENDARY])

    alloc_target_grade = st.selectbox(
        "목표 등급",
        options=available_grades,
        format_func=lambda x: x.value,
        key="alloc_target_grade"
    )

    st.info("**참고**: 전설 등급은 도감 완성도 때문에 많은 소환권이 필요합니다. 고대 등급부터 시작하는 것을 권장합니다.")

    # 투혼/카드일 경우 레벨업 수준 선택
    alloc_levelup_target = 5  # 기본값
    if alloc_category in [Category.SPIRIT, Category.CARD]:
        levelup_name = "투혼" if alloc_category == Category.SPIRIT else "카드"
        alloc_levelup_target = st.selectbox(
            f"{levelup_name} 레벨업 목표",
            options=[0, 1, 2, 3, 4, 5],
            index=5,
            format_func=lambda x: f"{x}레벨" if x > 0 else "레벨업 안 함",
            key="alloc_levelup_target",
            help=f"{levelup_name}을 몇 레벨까지 올릴지 선택합니다. 레벨업에 사용되지 않은 재료는 합성에 사용됩니다."
        )

    # 목표 개수
    alloc_target_count = st.number_input(
        "목표 개수",
        min_value=1, max_value=100, value=10,
        key="alloc_target_count"
    )

    st.markdown("---")
    st.subheader("소환권별 기여도 비율 (%)")

    # 해당 카테고리의 모든 소환권 목록
    available_tickets = st.session_state.dm.get_tickets_for_category(alloc_category)

    # 비율 입력 - 모든 소환권을 표시
    ratios = {}

    # 소환권이 많으면 2열로 표시
    if len(available_tickets) > 4:
        col1, col2 = st.columns(2)
        for i, ticket in enumerate(available_tickets):
            # 소환권 이름 간략화 (캐릭터 귀속 제거)
            short_name = ticket.name.replace(" (캐릭터 귀속)", "").replace(" (계정 귀속)", "")
            with col1 if i % 2 == 0 else col2:
                ratio = st.number_input(
                    f"{short_name}",
                    min_value=0, max_value=100, value=0,
                    key=f"alloc_ratio_{ticket.name}"
                )
                if ratio > 0:
                    ratios[ticket.name] = ratio / 100
    else:
        for ticket in available_tickets:
            short_name = ticket.name.replace(" (캐릭터 귀속)", "").replace(" (계정 귀속)", "")
            ratio = st.number_input(
                f"{short_name} (%)",
                min_value=0, max_value=100, value=0,
                key=f"alloc_ratio_{ticket.name}"
            )
            if ratio > 0:
                ratios[ticket.name] = ratio / 100

    # 비율 합계 표시
    total_ratio = sum(ratios.values()) * 100 if ratios else 0
    if total_ratio > 0:
        if abs(total_ratio - 100) < 0.1:
            st.success(f"배분 비율 합계: {total_ratio:.0f}%")
        else:
            st.warning(f"배분 비율 합계: {total_ratio:.0f}% (100%가 아니어도 자동 정규화됩니다)")

    st.markdown("---")

    # 계산 버튼
    if st.button("배분 계산", type="primary", key="calc_allocation"):
        if not ratios:
            st.error("최소 하나 이상의 소환권에 비율을 입력해주세요.")
        else:
            with st.spinner("계산 중..."):
                # 레벨업 수준을 반영한 배분 계산기 생성
                if alloc_category == Category.SPIRIT:
                    calc = AllocationCalculator(
                        spirit_target_level=alloc_levelup_target,
                        card_target_level=5
                    )
                elif alloc_category == Category.CARD:
                    calc = AllocationCalculator(
                        spirit_target_level=5,
                        card_target_level=alloc_levelup_target
                    )
                else:
                    calc = st.session_state.alloc_calc

                result = calc.calculate_allocation_precise(
                    category=alloc_category,
                    target_grade=alloc_target_grade,
                    target_count=alloc_target_count,
                    ticket_ratios=ratios
                )

            st.session_state.alloc_result = result

    # 결과 표시
    if "alloc_result" in st.session_state and st.session_state.alloc_result:
        result = st.session_state.alloc_result

        st.subheader("계산 결과")

        # 요약
        st.markdown(f"""
        **목표**: {category_names[result.category]} {result.target_grade.value} {result.target_count}개
        """)

        # 도감 한계 정보 표시
        if hasattr(result, 'collection_limit') and result.collection_limit > 0:
            st.info(f"도감 종류 수: {result.collection_limit}종 (이 수를 초과하면 중복분이 필요합니다)")

        # 전체 경고 표시
        if hasattr(result, 'warning') and result.warning:
            st.warning(result.warning)

        # 소환권별 필요 개수
        if result.allocations:
            # 계산 불가 소환권 체크
            has_impossible = any(alloc.ticket_count < 0 for alloc in result.allocations)

            if has_impossible:
                st.error("""
                **일부 소환권으로는 목표 달성이 불가능합니다.**

                도감 종류 수를 초과하는 중복분이 필요한데, 해당 소환권의 확률이 너무 낮아 중복분이 충분히 생기지 않습니다.
                - 더 낮은 등급(예: 고대 대신 영웅)을 목표로 설정하거나
                - 해당 등급 확률이 높은 소환권을 선택하세요.
                """)

            st.markdown("### 필요 소환권")

            for alloc in result.allocations:
                short_name = alloc.ticket_name.replace(" (캐릭터 귀속)", "").replace(" (계정 귀속)", "")
                col1, col2, col3 = st.columns([3, 1, 2])
                with col1:
                    st.write(f"**{short_name}**")
                with col2:
                    if alloc.ticket_count >= 0:
                        st.write(f"**{alloc.ticket_count:,}개**")
                    else:
                        st.write("**달성 불가**")
                with col3:
                    if alloc.ticket_count >= 0:
                        st.write(f"(기여: {alloc.expected_target_items:.2f}개)")
                    else:
                        st.write(f"(최대: {alloc.expected_target_items:.1f}개)")

                # 개별 경고 메시지 표시
                if hasattr(alloc, 'warning') and alloc.warning:
                    st.caption(f"⚠️ {alloc.warning}")

            st.markdown("---")

            # 총계 (계산 가능한 것만)
            valid_allocations = [a for a in result.allocations if a.ticket_count >= 0]
            if valid_allocations:
                st.markdown(f"""
                **총 소환권 개수**: {result.total_tickets}개

                **예상 획득량**: {result.total_expected:.2f}개 (목표: {result.target_count}개)
                """)

            # 결과를 주차별 입력에 추가하는 버튼
            st.markdown("---")
            if st.button("이 배분을 1주차에 추가", key="add_alloc_to_week"):
                from simulator.main_engine import WeeklyInput

                week = 1
                if week not in st.session_state.state.weekly_inputs:
                    st.session_state.state.weekly_inputs[week] = WeeklyInput(
                        week=week,
                        date=BOOSTING_SCHEDULE[week],
                        tickets={cat: [] for cat in Category}
                    )

                week_input = st.session_state.state.weekly_inputs[week]

                for alloc in result.allocations:
                    if alloc.ticket_count > 0:
                        # 기존에 같은 소환권이 있으면 수량 추가
                        found = False
                        for i, (name, count) in enumerate(week_input.tickets[result.category]):
                            if name == alloc.ticket_name:
                                week_input.tickets[result.category][i] = (name, count + alloc.ticket_count)
                                found = True
                                break

                        if not found:
                            week_input.tickets[result.category].append(
                                (alloc.ticket_name, alloc.ticket_count)
                            )

                st.success("1주차에 추가되었습니다! '소환권 입력' 탭에서 확인하세요.")

            # =================================================================
            # 10주 배분 기능
            # =================================================================
            st.markdown("---")
            st.subheader("10주 배분")
            st.markdown("배분 계산기 결과를 10주에 걸쳐 비율대로 자동 분배합니다.")

            # 주차별 비율 입력
            if "weekly_pcts" not in st.session_state:
                st.session_state.weekly_pcts = {w: 10.0 for w in range(1, 11)}

            pct_cols = st.columns(5)
            for i in range(10):
                w = i + 1
                with pct_cols[i % 5]:
                    st.session_state.weekly_pcts[w] = st.number_input(
                        f"{w}주차 ({BOOSTING_SCHEDULE[w].strftime('%m.%d')})",
                        min_value=0.0, max_value=100.0,
                        value=st.session_state.weekly_pcts[w],
                        step=0.1,
                        key=f"weekly_pct_{w}"
                    )

            pct_total = sum(st.session_state.weekly_pcts.values())
            if abs(pct_total - 100) < 0.1:
                st.success(f"비율 합계: {pct_total:.1f}%")
            else:
                st.warning(f"비율 합계: {pct_total:.1f}% (100%가 권장됩니다)")

            # 미리보기 테이블
            if valid_allocations:
                import pandas as pd
                preview_data = []
                for w in range(1, 11):
                    pct = st.session_state.weekly_pcts[w] / 100.0
                    row = {"주차": f"{w}주차 ({BOOSTING_SCHEDULE[w].strftime('%m.%d')})"}
                    for alloc in valid_allocations:
                        short_name = alloc.ticket_name.replace(" (캐릭터 귀속)", "").replace(" (계정 귀속)", "")
                        weekly_count = round(alloc.ticket_count * pct)
                        row[short_name] = weekly_count
                    preview_data.append(row)

                # 합계 행
                total_row = {"주차": "합계"}
                for alloc in valid_allocations:
                    short_name = alloc.ticket_name.replace(" (캐릭터 귀속)", "").replace(" (계정 귀속)", "")
                    total_row[short_name] = sum(r[short_name] for r in preview_data)
                preview_data.append(total_row)

                df = pd.DataFrame(preview_data)
                st.dataframe(df, use_container_width=True, hide_index=True)

            # 적용 버튼
            if st.button("10주 전체에 배분 적용", type="primary", key="apply_weekly_alloc"):
                from simulator.main_engine import WeeklyInput

                for w in range(1, 11):
                    pct = st.session_state.weekly_pcts[w] / 100.0

                    if w not in st.session_state.state.weekly_inputs:
                        st.session_state.state.weekly_inputs[w] = WeeklyInput(
                            week=w,
                            date=BOOSTING_SCHEDULE[w],
                            tickets={cat: [] for cat in Category}
                        )

                    week_input = st.session_state.state.weekly_inputs[w]
                    # 해당 카테고리의 기존 소환권 초기화
                    week_input.tickets[result.category] = []

                    for alloc in valid_allocations:
                        weekly_count = round(alloc.ticket_count * pct)
                        if weekly_count > 0:
                            week_input.tickets[result.category].append(
                                (alloc.ticket_name, weekly_count)
                            )

                st.success(f"10주 전체에 {category_names[result.category]} 소환권이 배분되었습니다! '소환권 입력' 탭에서 확인하세요.")

        else:
            st.warning("계산 결과가 없습니다. 소환권 데이터를 확인해주세요.")

# =============================================================================
# 탭 5: 저장/불러오기
# =============================================================================

with tab5:
    st.header("저장 / 불러오기")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("현재 상태 저장")

        save_name = st.text_input("저장 파일명", value="simulation_save")

        if st.button("저장", key="save_btn"):
            # 저장 데이터 준비
            save_data = {
                "target_spec": {
                    cat.value: {grade.value: count for grade, count in targets.items()}
                    for cat, targets in st.session_state.state.target_spec.items()
                },
                "weekly_inputs": {}
            }

            for week, week_input in st.session_state.state.weekly_inputs.items():
                save_data["weekly_inputs"][str(week)] = {
                    cat.value: [(name, count) for name, count in tickets]
                    for cat, tickets in week_input.tickets.items()
                }

            # 저장
            save_path = PROJECT_ROOT / "saves" / f"{save_name}.json"
            save_path.parent.mkdir(exist_ok=True)

            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)

            st.success(f"저장 완료: {save_path}")

    with col2:
        st.subheader("저장된 상태 불러오기")

        # 저장 파일 목록
        save_dir = PROJECT_ROOT / "saves"
        if save_dir.exists():
            save_files = list(save_dir.glob("*.json"))
            if save_files:
                selected_file = st.selectbox(
                    "불러올 파일 선택",
                    options=save_files,
                    format_func=lambda x: x.stem
                )

                col_load, col_delete = st.columns(2)

                with col_load:
                    if st.button("불러오기", key="load_btn"):
                        with open(selected_file, "r", encoding="utf-8") as f:
                            load_data = json.load(f)

                        # 상태 복원
                        from simulator.main_engine import WeeklyInput

                        # 새 상태 생성
                        new_state = st.session_state.engine.create_initial_state()

                        # 목표 스펙 복원
                        grade_map = {g.value: g for g in Grade}
                        cat_map = {c.value: c for c in Category}

                        for cat_name, targets in load_data["target_spec"].items():
                            cat = cat_map[cat_name]
                            new_state.target_spec[cat] = {
                                grade_map[g]: c for g, c in targets.items()
                            }

                        # 주차별 입력 복원
                        for week_str, inputs in load_data["weekly_inputs"].items():
                            week = int(week_str)
                            tickets = {}
                            for cat_name, ticket_list in inputs.items():
                                cat = cat_map[cat_name]
                                tickets[cat] = [(name, count) for name, count in ticket_list]

                            new_state.weekly_inputs[week] = WeeklyInput(
                                week=week,
                                date=BOOSTING_SCHEDULE[week],
                                tickets=tickets
                            )

                        st.session_state.state = new_state
                        st.success("불러오기 완료!")
                        st.rerun()

                with col_delete:
                    if st.button("삭제", key="delete_btn", type="secondary"):
                        import os
                        os.remove(selected_file)
                        st.success(f"삭제 완료: {selected_file.stem}")
                        st.rerun()
            else:
                st.info("저장된 파일이 없습니다.")
        else:
            st.info("저장 폴더가 없습니다.")

# =============================================================================
# 푸터
# =============================================================================

st.markdown("---")
st.markdown("*부스팅 소환권 시뮬레이터 v1.0*")
