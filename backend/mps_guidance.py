"""User-defined MPS stage labels and clinician-review care planning text.

The mapping defines names, not validated numerical diagnostic cutoffs.
"""
STAGES = {
    0: '급성장기 이전',
    1: '급성장 가속기 초반',
    2: '급성장 가속기 중반',
    3: '급성장 감속기 초반',
    4: '급성장기 이후',
}
PHASES = {0: 'pre_phv', 1: 'accelerating', 2: 'accelerating',
          3: 'decelerating', 4: 'post_phv'}
SYSTEM = 'MPS 성장단계 0–4 · 의료진 검토용 운영 분류'


def normalize_stage(stage):
    stage['system'] = SYSTEM
    number = stage.get('mps_stage')
    if stage['status'] != 'estimated':
        stage.update(mps_stage=None, label='MPS Stage 판단 보류')
        return
    if number is None:
        # The broad acceleration label cannot distinguish Stage 1 from Stage 2.
        number = {'pre_phv': 0, 'post_phv': 4}.get(stage.get('phase'))
    if number not in STAGES or stage.get('phase') != PHASES.get(number):
        stage.update(mps_stage=None, status='insufficient', label='MPS Stage 판단 보류')
        stage['limitation'] = (stage.get('limitation','') +
            ' MPS 세부 단계에 맞는 현재 관찰·성장추이 또는 단계 간 구분 근거가 부족합니다.').strip()
        return
    stage.update(mps_stage=number, label=f'Stage {number} · {STAGES[number]}')


def sports_plan(patient, report):
    """Three concise paragraphs; never invent normality or longitudinal changes."""
    stage = report['phv']
    number = stage.get('mps_stage') if stage['status']=='estimated' else None
    followup = '약 3개월 단위로 신장·성장속도·성장단계를 재평가하고, 통증이나 기능 저하가 있으면 일정을 앞당겨 확인하는 MPS 추적 계획을 제안합니다.'
    if number in (1,2):
        exercise = (f"현재 영상·기록은 {stage['label']}에 해당하는 것으로 추정됩니다. "
                    '최대중량 달성보다 지도하의 정확한 동작, 달리기·점프·민첩성·기초 근력과 충분한 회복을 균형 있게 구성하고, 무릎·발뒤꿈치·허리 통증에 따라 부하를 조절합니다.')
    elif number==0:
        exercise = ('급성장기 이전 단계로 추정되어 다양한 움직임과 달리기·점프·균형·기초 근력의 동작 습득을 중심으로 계획합니다. 지도하에 숙련도에 맞춰 부하를 높이고 통증과 회복 상태를 확인합니다.')
    elif number==3:
        exercise = ('급성장 감속기 초반으로 추정되어 움직임의 질과 기초 근력을 확인하면서 훈련 부하를 점진적으로 조절합니다. 성장속도 변화와 무릎·발뒤꿈치·허리 통증, 회복 상태를 함께 살핍니다.')
    elif number==4:
        exercise = ('급성장기 이후 단계로 추정되며 성장 종료를 의미하지는 않습니다. 현재 체력·동작 숙련도·통증 상태를 확인하여 근력과 종목별 훈련을 점진적으로 구성하고 회복을 확보합니다.')
    else:
        exercise = ('현재 자료만으로 성장단계를 확정하기 어려워 단계별 고강도 훈련 처방은 보류합니다. 지도하에 기본 동작과 기초 체력을 점검하고, 무릎·발뒤꿈치·허리 통증 및 회복 상태를 확인합니다.')
    body_fat = patient.body_fat
    composition = (f'입력된 체지방률은 {body_fat:g}%이며 단일 수치만으로 적정 여부나 근육량 증가를 판단하지 않습니다. '
                   if body_fat is not None else '체성분의 현재값과 이전 측정값을 비교해 변화 추이를 확인합니다. ')
    nutrition = composition + '성장·운동량에 맞는 에너지와 단백질, 규칙적인 식사·수면을 점검하고 체중 조절 필요성은 의료진이 개별 판단합니다.'
    return dict(paragraphs=[followup,exercise,nutrition],
                basis='MPS 관리 제안 · 입력자료 기반 · 의료진 확인 후 적용',
                followup_months=3)
