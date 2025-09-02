from draft_helper_step2_vorp import write_state, read_state
from collections import defaultdict
p = '_state_test.json'
write_state(p, 'players.csv', 10, {'RB':2}, {'RB':3}, {'need':1.0,'bench':0.4,'blocked':0.1}, 15, [('drafted','John Doe','RB'), ('mine','My Guy','WR')], defaultdict(int, {'RB':1,'WR':1,'FLEX':0}))
print('wrote')
st = read_state(p)
print(st['csv'], st['teams'], len(st['drafted']), st['my_counts']['RB'])
