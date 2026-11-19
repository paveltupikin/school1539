import io
import json
from pathlib import Path
import sqlite3
import sys
import time
import unittest
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import question_bank as bank
import server


class RussianBankTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        server.initialize(self.db)
        self.student = server.user_create(self.db, dict(login='demo.student',name='Ученик Демо',grade='9',password='demo-password-123'), 'student')
        self.teacher = server.user_create(self.db, dict(login='demo.teacher',name='Учитель Демо',password='demo-password-123'), 'teacher')
        for uid, token in [(self.student,'student-token'),(self.teacher,'teacher-token')]:
            self.db.execute('INSERT INTO session VALUES(?,?,?)',(server.token_hash(token),uid,int(time.time())+3600))
        self.db.commit()

    def tearDown(self): self.db.close()

    def api(self,path,data=None,teacher=False):
        try:
            result=server.api(self.db,'POST' if data is not None else 'GET',path,data or {},'teacher-token' if teacher else 'student-token')
            self.db.commit()
            return result[0]
        except Exception:
            self.db.rollback()
            raise

    def start(self, **kwargs):
        return self.api('/start',dict(exam='oge',subject='russ',mode='test',**kwargs))

    def finish_correct(self,attempt):
        tasks=json.loads(self.db.execute('SELECT questions FROM attempt WHERE id=?',(attempt['id'],)).fetchone()[0])
        return self.api('/finish',dict(id=attempt['id'],answers=[t['answer'] if t['kind']!='written' else 'Мой тезис и два примера из текста.' for t in tasks]))

    def test_complete_import_and_database_views(self):
        seed=bank.load_seed('russ')
        self.assertEqual((len(seed['tasks']),len(seed['cards']),len(seed['contexts'])),(100,280,15))
        self.assertEqual(Counter(x for t in seed['tests'] for x in t['tasks']),Counter(t['id'] for t in seed['tasks']))
        self.assertEqual(len({t['public_id'] for t in seed['tasks']}|{t['public_id'] for t in seed['cards'] if 'public_id' in t}),330)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM database_tests WHERE subject='russ'").fetchone()[0],100)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM database_cards WHERE subject='russ'").fetchone()[0],280)
        self.assertEqual(len(bank.questions(self.db,'oge','math','test')),25)
        self.assertEqual(len(bank.questions(self.db,'oge','math','quiz')),13)
        bank.install_all(self.db)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM user').fetchone()[0],2)

    def test_answer_variants_and_ordered_matching(self):
        for task in bank.questions(self.db,'oge','russ','feed')+bank.questions(self.db,'oge','russ','quiz'):
            if task['kind']=='written': continue
            for answer in task.get('answers') or [task['answer']]: self.assertTrue(server.matches(task,answer),(task['id'],answer))
        self.assertTrue(server.matches({'kind':'text','answer':'бревенчатыйдом','answers':['бревенчатыйдом','домбревенчатый'],'compact_answer':True},'ДОМ БРЕВЁНЧАТЫЙ'))
        self.assertTrue(server.matches({'kind':'set','answer':'345'},'5, 3, 4'))
        self.assertFalse(server.matches({'kind':'set','answer':'345'},'3345'))
        self.assertFalse(server.matches({'kind':'sequence','answer':'215'},'512'))

    def test_resume_scopes_and_sources_after_submission(self):
        first=self.start(test='russ-practice-01')
        second=self.start(test='russ-practice-02')
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(self.start(test='russ-practice-01')['id'],first['id'])
        self.assertEqual([t['number'] for t in first['questions']],list(range(2,14)))
        for task in first['questions']:
            self.assertNotIn('answer',task); self.assertNotIn('source_label',task)
            if task.get('context'): self.assertNotIn('source',task['context'])
        result=self.finish_correct(first)
        self.assertEqual((result['correct'],result['total']),(11,11))
        self.assertIsNone(result['details'][-1][2])
        self.assertEqual(len(result['questions']),12)
        self.assertEqual(result['source'],'РЕШУ ОГЭ · русский язык')
        self.assertEqual(result,self.api('/finish',dict(id=first['id'],answers=[])))

    def test_card_topics_skip_and_review(self):
        def start(**k): return self.api('/start',dict(exam='oge',subject='russ',mode='quiz',**k))
        card=start(topic='Грамматическая основа')
        self.assertEqual(card['questions'][0]['topic'],'Грамматическая основа')
        self.assertEqual(start(topic='Грамматическая основа')['id'],card['id'])
        self.api('/finish',dict(id=card['id'],answers=['неверный ответ']))
        review=start(review=True)
        self.assertEqual(review['questions'][0]['public_id'],card['questions'][0]['public_id'])
        self.finish_correct(review)
        with self.assertRaises(server.Error): start(review=True)
        another=start(topic='Лексика')
        self.api('/skip',{'id':another['id']})
        self.assertNotEqual(start(topic='Лексика')['id'],another['id'])
        with self.assertRaises(server.Error): start(id='M-001')

    def test_teacher_assignment_timer_roles_and_xlsx(self):
        group=self.api('/groups',{'name':'Группа Демо'},teacher=True)
        gid=group['id']
        self.db.execute('INSERT INTO member VALUES(?,?)',(gid,self.student));self.db.commit()
        self.api(f'/groups/{gid}/assign',dict(exam='oge',subject='russ',mode='test',title='Входная работа',minutes=1),teacher=True)
        assignment=self.api('/progress')['assignments'][0]
        attempt=self.start(assignment=assignment['id'])
        self.assertIsNotNone(attempt['deadline'])
        self.db.execute('UPDATE attempt SET deadline=? WHERE id=?',(int(time.time())-1,attempt['id']));self.db.commit()
        result=self.finish_correct(attempt)
        self.assertTrue(result['expired']);self.assertEqual(result['correct'],0)
        other=server.user_create(self.db,dict(login='other.demo',name='Другой Демо',grade='9',password='demo-password-123'),'student')
        self.db.execute('INSERT INTO session VALUES(?,?,?)',(server.token_hash('other-token'),other,int(time.time())+3600));self.db.commit()
        with self.assertRaises(server.Error): server.api(self.db,'POST','/finish',dict(id=attempt['id'],answers=[]),'other-token')
        self.db.rollback()
        with self.assertRaises(server.Error): self.api(f'/groups/{gid}')
        exported=self.api(f'/groups/{gid}/export',teacher=True)
        from openpyxl import load_workbook
        sheet=load_workbook(io.BytesIO(exported),data_only=True).active
        self.assertEqual(sheet.cell(1,1).value,'Ученик')

    def test_catalog_feed_and_legacy_migration(self):
        self.assertEqual(len(self.api('/oge/russ/catalog')['tests']),10)
        feed=self.api('/oge/russ/tasks')['tasks']
        self.assertEqual(len(feed),330)
        self.assertFalse(any('answer' in t or 'solution' in t for t in feed))
        self.assertEqual(len(self.api('/oge/math/tasks')['tasks']),28)
        old=sqlite3.connect(':memory:');old.row_factory=sqlite3.Row;old.executescript(server.SCHEMA)
        server.initialize(old)
        self.assertIn('scope',{r[1] for r in old.execute('PRAGMA table_info(attempt)')});old.close()

    def test_registration_login_and_logout(self):
        data=dict(login='new.demo',name='Новый Демо',grade='9',password='demo-password-123')
        account,headers=server.api(self.db,'POST','/register',data,'')
        self.db.commit()
        token=headers['Set-Cookie'].split('portal=',1)[1].split(';',1)[0]
        self.assertEqual(server.api(self.db,'GET','/me',{},token)[0]['user']['role'],'student')
        server.api(self.db,'POST','/logout',{},token);self.db.commit()
        self.assertIsNone(server.api(self.db,'GET','/me',{},token)[0]['user'])
        logged_in,headers=server.api(self.db,'POST','/login',data,'')
        self.db.commit()
        self.assertEqual(logged_in['user']['name'],'Новый Демо')

if __name__=='__main__': unittest.main()
