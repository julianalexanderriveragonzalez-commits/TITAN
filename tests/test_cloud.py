import base64
import io
import json
import os
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from pathlib import Path
from cloud import app

class CloudTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'TITAN_PASSWORD':'test-only-secret','TITAN_DB':str(Path(self.tmp.name)/'titan.sqlite3')})
        self.env.start()
    def tearDown(self):
        self.env.stop();self.tmp.cleanup()
    def request(self,path,method='GET',data=None,authorized=True,origin=None):
        b=json.dumps(data).encode() if data is not None else b''
        headers=[]
        auth='Basic '+base64.b64encode(b'titan:test-only-secret').decode() if authorized else ''
        env={'PATH_INFO':path,'REQUEST_METHOD':method,'CONTENT_LENGTH':str(len(b)),'CONTENT_TYPE':'application/json','wsgi.input':io.BytesIO(b),'HTTP_AUTHORIZATION':auth,'HTTP_HOST':'localhost:8765','wsgi.url_scheme':'http'}
        if origin: env['HTTP_ORIGIN']=origin
        status=[]
        def start(s,h):status.append(s)
        raw=b''.join(app(env,start))
        return status[0],json.loads(raw) if path!='/' else raw
    def payload(self,days):
        cutoff=(datetime.now(timezone.utc)+timedelta(days=days)).isoformat()
        return {'match':{'id':'test','team_a':'A','team_b':'B','cutoff':cutoff},'teams':{'A':{'series':[],'mechanisms':[]},'B':{'series':[],'mechanisms':[]}}}
    def test_auth_required(self):
        s,_=self.request('/health',authorized=False);self.assertTrue(s.startswith('401'))
    def test_analyze_without_fabricating(self):
        s,r=self.request('/api/analyze','POST',self.payload(2));self.assertTrue(s.startswith('200'));self.assertEqual(r['selection_type'],'PROVISIONAL FORZADA');self.assertEqual(len(r['controls_R33_R34']),12)
    def test_freeze_and_history(self):
        s,r=self.request('/api/freeze','POST',self.payload(2));self.assertTrue(s.startswith('201'))
        s,h=self.request('/api/history');self.assertEqual(h['items'][0]['id'],r['id'])
    def test_no_retrospective_freeze(self):
        s,r=self.request('/api/freeze','POST',self.payload(-1));self.assertTrue(s.startswith('409'))
    def test_no_early_evaluation(self):
        _,r=self.request('/api/freeze','POST',self.payload(2))
        s,_=self.request('/api/evaluate/'+r['id'],'POST',{'winner':'A'});self.assertTrue(s.startswith('409'))
    def test_origin_rejection(self):
        s,_=self.request('/api/analyze','POST',self.payload(2),origin='https://hostile.example');self.assertTrue(s.startswith('403'))
    def test_same_team_rejected(self):
        p=self.payload(2);p['match']['team_b']='A'
        s,_=self.request('/api/analyze','POST',p);self.assertTrue(s.startswith('400'))

if __name__=='__main__':unittest.main()
