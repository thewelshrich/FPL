import pandas as pd
import numpy as np

from scipy.stats import poisson
from scipy.optimize import minimize

from utils import odds, clean_sheet
from ranked_probability_score import ranked_probability_score, match_outcome


class SPI:

    def __init__(self, games):
        self.games = games.loc[:, ["proj_score1", "proj_score2", "team1", "team2", "prob1", "prob2", "probtie"]]
        self.games = self.games.apply(self.reverse_engineer_odds, axis=1)


    def reverse_engineer_odds(self, row):
        home_goals_pmf = poisson(row["proj_score1"]).pmf(np.arange(0, 8))
        away_goals_pmf = poisson(row["proj_score2"]).pmf(np.arange(0, 8))

        m = np.outer(home_goals_pmf, away_goals_pmf)

        row["home_win_p"], row["draw_p"], row["away_win_p"] = odds(m)

        return row


if __name__ == "__main__":

    df = pd.read_csv("data/fivethirtyeight/spi_matches.csv")
    df = (df
        .loc[(df['league_id'] == 2411) | (df['league_id'] == 2412)]
        )
    df = df[df['season'] == 2021]
    df = df[df['score1'].notna()]

    spi = SPI(df)

    print(spi.games)