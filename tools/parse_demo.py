"""Generate a map evidence record from a CS2 demo for offline processing."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from demoparser2 import DemoParser


def parse(path):
    parser=DemoParser(str(path))
    def events(name,fields=()):
        frame=parser.parse_event(name,player=list(fields),other=['is_warmup_period'])
        return frame[frame.is_warmup_period==False].sort_values('tick').to_dict('records')
    freezes=events('round_freeze_end')
    ends=events('round_end')
    deaths=events('player_death',['team_num'])
    ticks=[r['tick'] for r in freezes]
    equipment=parser.parse_ticks(['team_num','current_equip_value'],ticks=ticks) if ticks else None
    rounds=[]
    for i,start in enumerate(ticks):
        stop=ticks[i+1] if i+1<len(ticks) else float('inf')
        finishes=[e for e in ends if start<e['tick']<stop and e['winner'] in (2,3)]
        if len(finishes)!=1:continue
        end=finishes[0];fraglog=[]
        for d in deaths:
            if not start<=d['tick']<=end['tick'] or {d['attacker_team_num'],d['user_team_num']}!={2,3}:continue
            fraglog.append({'tick':int(d['tick']),'killer':str(d['attacker_steamid']),'victim':str(d['user_steamid']),'side':int(d['attacker_team_num'])})
        trades=[]
        for j,k in enumerate(fraglog):
            # A revenge kill on the original attacker, within 320 simulation ticks.
            prior=next((x for x in reversed(fraglog[:j]) if x['killer']==k['victim'] and x['side']!=k['side'] and 0<k['tick']-x['tick']<=320),None)
            if prior:trades.append({'tick':k['tick'],'previous_tick':prior['tick'],'side':k['side']})
        at=equipment[equipment.tick==start]
        sides={}
        for side in (2,3):
            group=at[at.team_num==side].drop_duplicates('steamid')
            sides[str(side)]={'steamids':sorted(str(n) for n in group.steamid),'equipment':int(group.current_equip_value.sum()) if len(group)==5 else None}
        rounds.append({'start':start,'end':int(end['tick']),'winner':int(end['winner']),'opening':fraglog[0] if fraglog else None,'trades':trades,'sides':sides})
    with path.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'map':parser.parse_header()['map_name'],'sha256':digest,'parsed_at':datetime.now(timezone.utc).isoformat(),'rounds':rounds}


if __name__=='__main__':
    cli=argparse.ArgumentParser()
    cli.add_argument('demo',type=Path)
    cli.add_argument('output',type=Path)
    args=cli.parse_args()
    args.output.write_text(json.dumps(parse(args.demo),ensure_ascii=False))
