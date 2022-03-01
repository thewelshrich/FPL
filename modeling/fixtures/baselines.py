import pandas as pd
import numpy as np
import json

from utils import get_next_gw
from ranked_probability_score import ranked_probability_score, match_outcome


class Baselines:
    """ Baselines and dummy models """

    def __init__(self, games):
        self.games = games.loc[:, ["score1", "score2", "team1", "team2"]]
        self.games = self.games.dropna()
        self.games["score1"] = self.games["score1"].astype(int)
        self.games["score2"] = self.games["score2"].astype(int)

        self.teams = np.sort(np.unique(self.games["team1"]))
        self.league_size = len(self.teams)

    def uniform(self, games):
        parameter_df = (
            pd.DataFrame()
            .assign(team=self.teams)
        )

        aggregate_df = (
            pd.merge(games, parameter_df, left_on='team1', right_on='team')
            .merge(parameter_df, left_on='team2', right_on='team')
        )

        aggregate_df["home_win_p"] = 0.333
        aggregate_df["draw_p"] = 0.333
        aggregate_df["away_win_p"] = 0.333

        return aggregate_df

    def home_bias(self, games):
        parameter_df = (
            pd.DataFrame()
            .assign(team=self.teams)
        )

        aggregate_df = (
            pd.merge(games, parameter_df, left_on='team1', right_on='team')
            .merge(parameter_df, left_on='team2', right_on='team')
        )

        aggregate_df["home_win_p"] = 1
        aggregate_df["draw_p"] = 0
        aggregate_df["away_win_p"] = 0

        return aggregate_df

    def draw_bias(self, games):
        parameter_df = (
            pd.DataFrame()
            .assign(team=self.teams)
        )

        aggregate_df = (
            pd.merge(games, parameter_df, left_on='team1', right_on='team')
            .merge(parameter_df, left_on='team2', right_on='team')
        )

        aggregate_df["home_win_p"] = 0
        aggregate_df["draw_p"] = 1
        aggregate_df["away_win_p"] = 0

        return aggregate_df

    def away_bias(self, games):
        parameter_df = (
            pd.DataFrame()
            .assign(team=self.teams)
        )

        aggregate_df = (
            pd.merge(games, parameter_df, left_on='team1', right_on='team')
            .merge(parameter_df, left_on='team2', right_on='team')
        )

        aggregate_df["home_win_p"] = 0
        aggregate_df["draw_p"] = 0
        aggregate_df["away_win_p"] = 1

        return aggregate_df

    def random_odds(self, games):
        parameter_df = (
            pd.DataFrame()
            .assign(team=self.teams)
        )

        aggregate_df = (
            pd.merge(games, parameter_df, left_on='team1', right_on='team')
            .merge(parameter_df, left_on='team2', right_on='team')
        )
        
        odds = np.random.rand(3, aggregate_df.shape[0])
        aggregate_df["home_win_p"] = odds[0] / np.sum(odds, 0)
        aggregate_df["draw_p"] = odds[1] / np.sum(odds, 0)
        aggregate_df["away_win_p"] = odds[2] / np.sum(odds, 0)

        return aggregate_df

    def bookies_odds(self, games, path):
        parameter_df = (
            pd.DataFrame()
            .assign(team=self.teams)
        )

        aggregate_df = (
            pd.merge(games, parameter_df, left_on='team1', right_on='team')
            .merge(parameter_df, left_on='team2', right_on='team')
        )

        predictions_market = (
            pd.read_csv(f'{path}data/betting/2021-22.csv')
            .loc[:, ["HomeTeam", "AwayTeam", "B365H", "B365D", "B365A"]]
            .rename(columns={
                "HomeTeam": "team1",
                "AwayTeam": "team2",
                "B365H": "home_win_p",
                "B365D": "draw_p",
                "B365A": "away_win_p"})
        )

        predictions_market = predictions_market.replace({
            'Brighton': 'Brighton and Hove Albion',
            'Leicester': 'Leicester City',
            'Leeds': 'Leeds United',
            'Man City': 'Manchester City',
            'Man United': 'Manchester United',
            'Norwich': 'Norwich City',
            'Tottenham': 'Tottenham Hotspur',
            'West Ham': 'West Ham United',
            'Wolves': 'Wolverhampton'
        })

        aggregate_df = pd.merge(
            aggregate_df,
            predictions_market,
            left_on=['team1', 'team2'],
            right_on=['team1', 'team2'])

        aggregate_df['total'] = (100 / aggregate_df['home_win_p'] + 100 /
                    aggregate_df['draw_p'] + 100 / aggregate_df['away_win_p'])
        aggregate_df['home_win_p'] = 100 / aggregate_df['home_win_p'] / aggregate_df['total']
        aggregate_df['away_win_p'] = 100 / aggregate_df['away_win_p'] / aggregate_df['total']
        aggregate_df['draw_p'] = 100 / aggregate_df['draw_p'] / aggregate_df['total']

        return aggregate_df

    def bookies_favorite(self, games, path):
        parameter_df = (
            pd.DataFrame()
            .assign(team=self.teams)
        )

        aggregate_df = (
            pd.merge(games, parameter_df, left_on='team1', right_on='team')
            .merge(parameter_df, left_on='team2', right_on='team')
        )

        predictions_market = (
            pd.read_csv(f'{path}data/betting/2021-22.csv')
            .loc[:, ["HomeTeam", "AwayTeam", "B365H", "B365D", "B365A"]]
            .rename(columns={
                "HomeTeam": "team1",
                "AwayTeam": "team2",
                "B365H": "home_win_p",
                "B365D": "draw_p",
                "B365A": "away_win_p"})
        )

        predictions_market = predictions_market.replace({
            'Brighton': 'Brighton and Hove Albion',
            'Leicester': 'Leicester City',
            'Leeds': 'Leeds United',
            'Man City': 'Manchester City',
            'Man United': 'Manchester United',
            'Norwich': 'Norwich City',
            'Tottenham': 'Tottenham Hotspur',
            'West Ham': 'West Ham United',
            'Wolves': 'Wolverhampton'
        })

        aggregate_df = pd.merge(
            aggregate_df,
            predictions_market,
            left_on=['team1', 'team2'],
            right_on=['team1', 'team2'])

        max_odds = np.argmax(aggregate_df[['home_win_p', 'draw_p', 'away_win_p']].values, 1)

        favorites = np.zeros(aggregate_df[['home_win_p', 'draw_p', 'away_win_p']].values.shape)
        favorites[np.arange(0, max_odds.shape[0]), max_odds] = 1

        aggregate_df['home_win_p'] = favorites[:, 0]
        aggregate_df['away_win_p'] = favorites[:, 2]
        aggregate_df['draw_p'] = favorites[:, 1]

        return aggregate_df

    def evaluate(self, games, function_name, path=''):
        if function_name == "uniform":
            aggregate_df = self.uniform(games)
        if function_name == "home":
            aggregate_df = self.home_bias(games)
        if function_name == "draw":
            aggregate_df = self.draw_bias(games)
        if function_name == "away":
            aggregate_df = self.away_bias(games)
        if function_name == "random":
            aggregate_df = self.random_odds(games)
        if function_name == "bookies":
            aggregate_df = self.bookies_odds(games, path)
        if function_name == "favorite":
            aggregate_df = self.bookies_favorite(games, path)

        aggregate_df["winner"] = match_outcome(aggregate_df)

        aggregate_df["rps"] = aggregate_df.apply(
            lambda row: ranked_probability_score(
                [row["home_win_p"], row["draw_p"],
                 row["away_win_p"]], row["winner"]), axis=1)

        return aggregate_df


if __name__ == "__main__":
    with open('info.json') as f:
        season = json.load(f)['season']

    next_gw = get_next_gw()

    df = pd.read_csv("data/fivethirtyeight/spi_matches.csv")
    df = (
        df
        .loc[(df['league_id'] == 2411) | (df['league_id'] == 2412)]
        )

    # Get GW dates
    fixtures = (
        pd.read_csv("data/fpl_official/vaastav/data/2021-22/fixtures.csv")
        .loc[:, ['event', 'kickoff_time']])
    fixtures["kickoff_time"] = pd.to_datetime(fixtures["kickoff_time"]).dt.date

    # Get only EPL games from the current season
    season_games = (
        df
        .loc[df['league_id'] == 2411]
        .loc[df['season'] == season]
        )
    season_games["kickoff_time"] = pd.to_datetime(season_games["date"]).dt.date

    # Merge on date
    season_games = (
        pd.merge(
            season_games,
            fixtures,
            left_on='kickoff_time',
            right_on='kickoff_time')
        .drop_duplicates()
        )

    # Train model on all games up to the previous GW
    baselines = Baselines(
        pd.concat([
            df.loc[df['season'] != season],
            season_games[season_games['event'] < next_gw]
            ]))

    # Add the home team and away team index for running inference
    idx = (
        pd.DataFrame()
        .assign(team=baselines.teams)
        .assign(team_index=np.arange(baselines.league_size)))
    season_games = (
        pd.merge(season_games, idx, left_on="team1", right_on="team")
        .rename(columns={"team_index": "hg"})
        .drop(["team"], axis=1)
        .drop_duplicates()
        .merge(idx, left_on="team2", right_on="team")
        .rename(columns={"team_index": "ag"})
        .drop(["team"], axis=1)
        .sort_values("date")
    )

    predictions = baselines.evaluate(season_games[season_games['event'] == next_gw], 'favorite')
    print(f"{(np.mean(predictions.rps)*100):.2f}")