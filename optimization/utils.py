import requests
import pandas as pd
import numpy as np


def get_team(team_id, gw):
    res = requests.get(f'https://fantasy.premierleague.com/api/entry/{team_id}/event/{gw}/picks/').json()
    # Adjust the player id with fplreview indices
    return [i['element'] for i in res['picks']], res['entry_history']['bank']


def get_predictions():
    df = pd.read_csv("../data/fpl_review/2021-22/gameweek/7/fplreview_fp.csv")
    df["Pos"] = df["Pos"].map(
        {
            1: 'G',
            2: 'D',
            3: 'M',
            4: 'F'
        })
    # One hot encoded values for the constraints
    df = pd.concat([df, pd.get_dummies(df.Pos)], axis=1)
    df = pd.concat([df, pd.get_dummies(df.Team)], axis=1)
    return df.fillna(0)


def get_transfer_history(team_id, last_gw):
    transfers = []
    # Reversing GW history until a chip is played or 2+ transfers were made
    for gw in range(last_gw, 0, -1):
        res = requests.get(f'https://fantasy.premierleague.com/api/entry/{team_id}/event/{gw}/picks/').json()
        transfer = res['entry_history']['event_transfers']
        chip = res['active_chip']

        transfers.append(transfer)
        if transfer > 1 or (chip is not None and chip != '3xc' and chip != 'bboost'):
            break

    return transfers


def get_rolling(team_id, last_gw):
    transfers = get_transfer_history(team_id, last_gw)

    # Start from gw where last chip used or when hits were taken
    # Reset FT count
    rolling = 0
    for transfer in reversed(transfers):
        # Transfer logic
        rolling = min(max(rolling + 1 - transfer, 0), 1)

    return rolling, transfers[0]


def get_chips(team_id, last_gw):
    freehit, wildcard, bboost, threexc = 0, 0, 0, 0
    # Reversing GW history until a chip is played or 2+ transfers were made
    for gw in range(last_gw, 0, -1):
        res = requests.get(f'https://fantasy.premierleague.com/api/entry/{team_id}/event/{gw}/picks/').json()
        chip = res['active_chip']

        if chip == '3xc':
            threexc = gw
        if chip == 'bboost':
            bboost = gw
        if chip == 'wildcard' and wildcard == 0:
            wildcard = gw
        if chip == 'freehit':
            freehit = gw

    return freehit, wildcard, bboost, threexc


def get_next_gw():
    url = 'https://fantasy.premierleague.com/api/bootstrap-static/'
    res = requests.get(url).json()
        
    for idx, gw in enumerate(res['events']):
        if not gw['finished']:
            return idx + 1


def pretty_print(data, start, period, team, starter, captain, vicecaptain, buy, sell, free_transfers, hits, freehit=-1, wildcard=-1, bboost=-1, threexc=-1):
    df = pd.DataFrame([], columns=['GW', 'Name', 'Pos', 'Team', 'SV', 'xP', 'Start', 'Cap', 'Vice', 'Buy', 'Sell'])

    for w in np.arange(start, start+period):
        print(f"GW: {w} - FT: {int(free_transfers[w].get_value())}")
        for p in data.index.tolist():
            if team[p, w].get_value():
                df = df.append({'GW': w, 'Name': data.loc[p]['Name'], 'Pos': data.loc[p]['Pos'], 'Team': data.loc[p]['Team'],
                                'SV': data.loc[p]['SV'], 'xP': data.loc[p][str(w) + '_Pts'], 'Start': int(starter[p, w].get_value()),
                                'Cap': int(captain[p, w].get_value()), 'Vice': int(vicecaptain[p, w].get_value()),
                                'Sell': int(sell[p, w].get_value()), 'Buy': int(buy[p, w].get_value())},
                               ignore_index=True)

            if buy[p, w].get_value():
                print(f"Buy: {data.loc[p, 'Name']}")
            if sell[p, w].get_value():
                print(f"Sell: {data.loc[p, 'Name']}")
        
        chip = ""
        av = ""
        if freehit + 1:
            chip = " - Chip: Freehit"
        if wildcard + 1:
            chip = " - Chip: Wildcard"
        if bboost + 1:
            chip = "- Chip: Bench Boost"
            av = f" - Added value: {np.sum(df.loc[(df['Team'] == 1) & (df['GW'] == w), 'xP']) - np.sum(df.loc[(df['Start'] == 1) & (df['GW'] == w), 'xP'])}"
        if threexc == w-start:
            chip = " - Chip: Triple Captain"
            av = f" - Added value: {np.sum(df.loc[(df['Cap'] == 1) & (df['GW'] == w), 'xP'])}"

        print(f"xPts: {np.sum(df.loc[(df['Start'] == 1) & (df['GW'] == w), 'xP'])-hits[w].get_value()*4:.2f} - Hits: {int(hits[w].get_value())}" + chip + av)
        print(" ____ ")

    custom_order = {'G': 0, 'D': 1, 'M': 2, 'F': 3}
    print(df.sort_values(by=['Pos'], key=lambda x: x.map(custom_order)).sort_values(by=['GW', 'Start'], ascending=[True, False]))
