def empty_estimate():
 return dict(status='insufficient',center=None,low=None,high=None,method='',reasoning='판독 가능한 현재 영상이 없어 추정하지 않습니다.',evidence=[],limitation='영상과 계측 필요')
def blank_report():
 return dict(data_review=[dict(text='가상 연결 검증 자료입니다.',evidence=[],file_ids=[])],image_readings=[],regions=[],bone_age=empty_estimate(),phv=dict(status='insufficient',label='판단 보류',system='PHV',reasoning='성장기록과 영상 부족',evidence=[],limitation='추가 자료 필요'),adult_height=empty_estimate(),rationale=[],limitations=['실제 환자 판독 결과가 아닌 테스트 응답입니다.'],follow_up=[],sports_integrated=[])
