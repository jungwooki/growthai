import sys,json,asyncio
from pathlib import Path
from unittest.mock import AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest,httpx
from fastapi import HTTPException
from backend import server,vision_stages
from clinical_fixture import blank_report


def response(data):
    return httpx.Response(200,json={'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(data)}]}], 'usage':{'input_tokens':100,'output_tokens':50,'total_tokens':150}})


def test_missing_and_wrong_group_observations_block_synthesis():
    files=[{'id':'F01','group':'ulna','visual':True}]
    with pytest.raises(HTTPException):vision_stages.parse_observations(response({'image_readings':[]}).json(),files)
    row=dict(file_id='F01',group='radius',quality='unusable',observations=[],visible_measurements=[],limitation='test')
    with pytest.raises(HTTPException):vision_stages.parse_observations(response({'image_readings':[row]}).json(),files)


def test_stages_preserve_all_images_and_do_not_send_them_with_references(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-key')
    monkeypatch.setattr(server,'render_references',lambda *args:[{'type':'input_image','image_url':'reference','detail':'high'}])
    monkeypatch.setattr(server.asyncio,'sleep',AsyncMock())
    monkeypatch.setattr(server.budget,'completed',AsyncMock())
    files=[dict(id=f'F{i:02}',group='ulna',visual=True,name='synthetic.png') for i in range(1,13)]
    content=[]
    for f in files:content.extend([{'type':'input_text','text':f"PATIENT_FILE {f['id']} | group=ulna"},{'type':'input_image','image_url':f['id'],'detail':'high'}])
    rows=[dict(file_id=f['id'],group='ulna',quality='unusable',observations=['synthetic'],visible_measurements=[],limitation='not medical') for f in files]
    calls=[]
    async def post(client,**kwargs):
        calls.append(kwargs['payload'])
        return response({'image_readings':rows} if len(calls)==1 else blank_report())
    monkeypatch.setattr(server.budget,'post_ai',post)
    patient=server.Patient(sex=1,birth='2013-10-17',exam='2026-09-26',height=158.8,use_ai=True,consent=True)
    result=asyncio.run(server.ask_ai(patient,server.calculate(patient),[],content,files))
    assert len(calls)==2
    assert sum(p['type']=='input_image' for p in calls[0]['input'][0]['content'])==12
    assert [p['image_url'] for p in calls[1]['input'][0]['content'] if p['type']=='input_image']==['reference']
    assert len(result['clinical_report']['image_readings'])==12
    assert result['analysis_passes']==2
    assert result['usage']['input_tokens']==200
