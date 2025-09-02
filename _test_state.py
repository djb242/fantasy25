import pandas as pd
import draft_helper_step2_vorp as mod

df = pd.DataFrame({
    'player':['A','B','C','D'],
    'position':['RB','RB','WR','WR'],
    'proj_points':[10.0,20.0,15.0,25.0]
})
repl = mod.compute_replacement_points(df, teams=1, starters_by_pos={'RB':1,'WR':1,'QB':0,'TE':0,'K':0,'DST':0})
needs = {'RB':'need','WR':'need','QB':'blocked','TE':'blocked','K':'blocked','DST':'blocked'}
weights = {'need':1.0,'bench':0.4,'blocked':0.1}
scored = mod.candidate_scores(df, repl, needs, weights)
print(scored)
print()
print(mod.printable_table(scored, topn=10))
