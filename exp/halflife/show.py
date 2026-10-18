import json, sys
def short(c):
    a=c['args']; return (c['name'], a.get('to') or a.get('ref') or a.get('destination') or a.get('path') or a.get('query'))
for l in open(sys.argv[1]):
    r=json.loads(l)
    for rd in r['rounds']:
        print(r['dom'], r['seed'], 'k',rd['k'], 'K', rd['knowledge']['score'])
        for b in rd['behavior']:
            print('   ', b['probe'], 'V' if b['violate'] else '-', 'C' if b['completed'] else '-', [short(c) for c in b['calls']], '|', (b['trace'][-1]['content'] or '')[:160].replace('\n',' '))
