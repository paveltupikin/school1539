"""Import the supplied PDF's exact question IDs from its matching saved print page.

Build-time dependencies only: lxml, pypdf. Runtime remains Python standard library.
Usage: python tools/import_russian.py saved-print.html supplied.pdf
The HTML must be the print-with-answers page of set 19223407.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

from lxml import html
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
TOPICS = {2: "Грамматическая основа", 3: "Синтаксический анализ", 4: "Пунктуационные правила",
          5: "Знаки препинания", 6: "Орфографические правила", 7: "Пропущенные буквы",
          8: "Грамматические нормы", 9: "Словосочетания", 10: "Содержание текста",
          11: "Средства выразительности", 12: "Лексика", 13: "Сочинение"}
HINTS = {
    2: "Найдите подлежащее и всё сказуемое. В составном сказуемом учитывайте связку или вспомогательный глагол. У односоставного предложения может быть только один главный член.",
    3: "Сначала выделите грамматические основы. Затем определите состав частей, тип связи и осложняющие конструкции. Не путайте вводную конструкцию с членом предложения.",
    4: "Для каждого правила найдите в предложении именно указанную конструкцию. Различайте тире между главными членами, знак при пропуске члена и знаки в сложном предложении.",
    5: "Выделите основы, границы частей и обособленные конструкции. Для каждой пронумерованной позиции проверьте, какой знак требуется по смыслу и строению предложения.",
    6: "Определите часть речи, морфему и условия выбора написания. Верным должен быть и результат, и объяснение: подходящее слово само по себе не делает правило правильным.",
    7: "Разберите каждое слово с пропуском: определите морфему и примените соответствующее правило. В ответ включайте только позиции с названной в условии буквой.",
    8: "Установите нужные падеж, число и род по контексту. Проверьте образование формы, особенно у числительных и существительных во множественном числе.",
    9: "Сохраните смысл и главное слово. При согласовании зависимое слово меняет форму вместе с главным; при управлении требуется падежная форма; при примыкании зависимое слово неизменяемое.",
    10: "Сверьте каждое утверждение с текстом. Не добавляйте предположения: подтверждаться должны все части высказывания, включая мотивы и причины поступков.",
    11: "Назовите признак указанного средства выразительности и проверьте его в каждом примере. Перенос значения, образное определение и устойчивое выражение различаются.",
    12: "Ищите слово или выражение только в указанном фрагменте. Сохраните нужный смысл, стилистическую окраску и требуемую форму ответа.",
    13: "Самопроверка: выбрана одна тема; дан тезис и ответ на вопрос; приведены два примера из исходного текста и пояснения к ним; есть вывод; не менее 70 слов. Проверьте связность, орфографию и пунктуацию. Автоматическая оценка сочинения не выставляется.",
}


def clean(s):
    return re.sub(r"[\t \u00a0\u202f]+", " ", s.replace("\xad", "").replace("\u2060", "")).strip()


def plain(el):
    el = deepcopy(el)
    # The PDF does not contain the expandable obsolete essay requirement.
    for bad in el.xpath('.//details|.//script|.//style'):
        bad.drop_tree()
    chunks = []
    def visit(node):
        if node.text: chunks.append(node.text)
        for child in node:
            if isinstance(child.tag, str): visit(child)
            if child.tail: chunks.append(child.tail)
        if node.tag in {'p', 'br', 'tr'} or node.get('class') == 'col_name': chunks.append('\n')
    visit(el)
    return '\n'.join(line for line in (clean(x) for x in ''.join(chunks).splitlines()) if line)


def run(saved_html, pdf):
    document = html.fromstring(Path(saved_html).read_text(encoding='utf-8'))
    pdf_ids = [(int(a), int(b), c) for a, b, c in re.findall(
        r'(\d+)\.\s*Тип\s*(\d+)\s*№\s*(\d+)',
        '\n'.join(p.extract_text() for p in PdfReader(pdf).pages))]
    assert len(pdf_ids) == 100 and {a for a, _, _ in pdf_ids} == set(range(1, 101))
    expected = {a: (b,c) for a,b,c in pdf_ids}
    contexts, tasks, cards, by_type = {}, [], [], defaultdict(list)
    for index, block in enumerate(document.xpath('//div[contains(concat(" ",@class," ")," prob_maindiv ")]'), 1):
        label = clean(block.xpath('.//span[@class="prob_nums"]')[0].text_content())
        kind, source_id = re.search(r'Тип\s*(\d+)\s*№\s*(\d+)', label).groups()
        kind = int(kind)
        assert expected[index] == (kind, source_id), (index, label, expected[index])
        body = plain(block.xpath('.//div[starts-with(@id,"body")]')[0])
        answer_el = block.xpath('.//div[@class="answer"]')
        variants = clean(answer_el[0].text_content()).split(':',1)[1].strip().split('|') if answer_el else []
        assert variants or kind == 13, source_id
        task = dict(id='rus-'+source_id, public_id='R-'+source_id, source='reshu-russ-19223407',
                    source_id=source_id, source_position=index, number=kind, topic=TOPICS[kind], prompt=body,
                    kind='written' if kind==13 else 'sequence' if kind==4 else 'text' if kind in {8,9,12} else 'set',
                    answer=variants[0] if variants else '', answers=variants,
                    solution=(('Эталонный ответ: '+ ' / '.join(variants)+'.\n') if variants else '')+HINTS[kind],
                    compact_answer=kind in {9,12})
        shared = block.xpath('.//div[starts-with(@id,"text") and @data-text_id]')
        if shared:
            c=shared[0]; cid='rus-text-'+c.get('data-text_id')
            context=dict(id=cid, source=task['source'], title='Текст к заданиям '+('2–3' if kind<4 else '10–13'), text=plain(c))
            assert cid not in contexts or contexts[cid]==context
            contexts[cid]=context; task['context']=cid
        tasks.append(task); by_type[kind].append(task)
        if kind in {2,3,6,10,11}:
            options=re.findall(r'(?ms)^\s*([1-5])\)\s*(.*?)(?=^\s*[1-5]\)|\Z)',body)
            assert len(options)==5,(source_id,options)
            for digit, option in options:
                good=digit in variants[0]
                questions={2:'Верно ли определена грамматическая основа?',3:'Верно ли это утверждение о строении текста?',
                           6:'Верно ли объяснено написание слова?',10:'Соответствует ли утверждение содержанию текста?',
                           11:'Есть ли в этом примере указанное средство выразительности?'}
                intro=body.split('1)')[0].strip() if kind==11 else ''
                cards.append(dict(id=f'rus-step-{source_id}-{digit}',task=task['id'], public_id=f'R-{source_id}-{digit}',
                                  kind='choice',prompt='\n'.join(x for x in [questions[kind],intro,option] if x),
                                  options=['Да','Нет'],answer='1' if good else '2',answers=[],
                                  solution=('Да.' if good else 'Нет.')+f' В полном задании верные варианты: {", ".join(variants[0])}.\n'+HINTS[kind]))
        elif kind==4:
            rules=re.findall(r'(?m)^([АБВ])\)\s*(.+)',body)
            examples=re.findall(r'(?m)^[1-5]\)\s*(.+)',body)
            assert len(rules)==3 and len(examples)==5,(source_id,rules,examples)
            for pos,(letter,rule) in enumerate(rules):
                cards.append(dict(id=f'rus-step-{source_id}-{letter}',task=task['id'],public_id=f'R-{source_id}-{"ABC"[pos]}',
                                  kind='choice',prompt='Подберите предложение к правилу.\n'+rule,
                                  options=examples,answer=variants[0][pos],answers=[],solution=HINTS[4]))
        else:
            cards.append(dict(id='rus-card-'+source_id,task=task['id']))
    assert len(tasks)==100
    tests=[]
    for i in range(10):
        items=[by_type[n][i]['id'] for n in range(2,10)]
        if i<5: items.extend(by_type[n][i]['id'] for n in range(10,14))
        tests.append(dict(id=f'russ-practice-{i+1:02}',title=f'Учебный пробник {i+1} · задания 2–13' if i<5 else f'Тренировка {i-4} · задания 2–9',tasks=items))
    assert Counter(x for t in tests for x in t['tasks']) == Counter(t['id'] for t in tasks)
    seed=dict(exam='oge',subject='russ',sources={'reshu-russ-19223407':'РЕШУ ОГЭ · русский язык'},
              provenance=dict(file=Path(pdf).name,sha256=hashlib.sha256(Path(pdf).read_bytes()).hexdigest(),
                              source_url='https://rus-oge.sdamgia.ru/test?id=19223407',actual_tasks=100,
                              note='В PDF нет изложения № 1 и аудиозаписи. Это учебные работы, не полный экзаменационный вариант.'),
              contexts=list(contexts.values()),tasks=tasks,cards=cards,tests=tests)
    (ROOT/'bank/oge-russ.json').write_text(json.dumps(seed,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'tasks':len(tasks),'cards':len(cards),'tests':len(tests),'contexts':len(contexts),'types':dict(Counter(t['number'] for t in tasks))},ensure_ascii=False))

if __name__=='__main__': run(*sys.argv[1:])
