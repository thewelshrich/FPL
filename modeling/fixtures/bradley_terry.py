import pandas as pd
import numpy as np
import json
from tqdm import tqdm

from scipy.optimize import minimize

from utils import get_next_gw, time_decay
from ranked_probability_score import ranked_probability_score, match_outcome


class Bradley_Terry:
    """ Model game outcomes using logistic distribution """

    def __init__(
            self,
            games,
            threshold=0.1,
            scale=1,
            parameters=None,
            decay=True):
        """
        Args:
            games (pd.DataFrame): Finished games to used for training.
            threshold (float): Threshold to differentiate team performances
            scale (float): Variance of strength ratings
            parameters (array): Initial parameters to use
            decay (boolean): Apply time decay
        """
        self.games = games.loc[:, [
            "score1", "score2", "team1", "team2", "date"]]
        self.games = self.games.dropna()

        self.games["date"] = pd.to_datetime(self.games["date"])
        self.games["days_since"] = (
            self.games["date"].max() - self.games["date"]).dt.days
        self.games["weight"] = (
            time_decay(0.0026, self.games["days_since"]) if decay else 1)
        self.decay = decay

        self.games["score1"] = self.games["score1"].astype(int)
        self.games["score2"] = self.games["score2"].astype(int)

        self.teams = np.sort(np.unique(self.games["team1"]))
        self.league_size = len(self.teams)
        self.threshold = threshold
        self.scale = scale

        # Initial parameters
        if parameters is None:
            self.parameters = np.concatenate((
                np.random.uniform(0, 1, (self.league_size)),  # Strength
                [.1],  # Home advantage
            ))
        else:
            self.parameters = parameters

    def likelihood(self, parameters, games):
        """ Perform sample prediction and compare with outcome

        Args:
            parameters (pd.DataFrame): Current estimate of the parameters
            games (pd.DataFrame): Fixtures

        Returns:
            (float): Likelihood of the estimated parameters
        """
        parameter_df = (
            pd.DataFrame()
            .assign(rating=parameters[:self.league_size])
            .assign(team=self.teams)
        )

        fixtures_df = (
            pd.merge(
                games,
                parameter_df,
                left_on='team1',
                right_on='team')
            .rename(columns={"rating": "rating1"})
            .merge(parameter_df, left_on='team2', right_on='team')
            .rename(columns={"rating": "rating2"})
            .drop("team_y", axis=1)
            .drop("team_x", axis=1)
        )

        outcome = match_outcome(fixtures_df)
        outcome_ma = np.ones((fixtures_df.shape[0], 3))
        outcome_ma[np.arange(0, fixtures_df.shape[0]), outcome] = 0

        odds = np.zeros((fixtures_df.shape[0], 3))
        odds[:, 0] = (
            1 / (1 + np.exp(
                -(
                    fixtures_df["rating1"] + parameters[-1] -
                    fixtures_df["rating2"] - self.threshold
                ) / self.scale)
            )
        )
        odds[:, 2] = (
            1 / (1 + np.exp(
                -(
                    fixtures_df["rating2"] - parameters[-1] -
                    fixtures_df["rating1"] - self.threshold
                ) / self.scale)
            )
        )
        odds[:, 1] = 1 - odds[:, 0] - odds[:, 2]

        return - np.power(
            np.ma.masked_array(odds, outcome_ma),
            np.repeat(
                np.array(fixtures_df["weight"].values).reshape(-1, 1),
                3,
                axis=1)
        ).sum()

    def maximum_likelihood_estimation(self):
        """
        Maximum likelihood estimation of the model parameters for team
        strengths and the home field advantage.
        """
        # Set strength ratings to have unique set of values for reproducibility
        constraints = [{
            "type": "eq",
            "fun": lambda x:
                sum(x[: self.league_size]) - self.league_size
            }]

        # Set the maximum and minimum values the parameters can take
        bounds = [(0, 3)] * self.league_size
        bounds += [(0, 1)]

        self.solution = minimize(
            self.likelihood,
            self.parameters,
            args=self.games,
            constraints=constraints,
            bounds=bounds,
            options={'disp': False, 'maxiter': 100})

        self.parameters = self.solution["x"]

    def predict(self, games):
        """ Predict score for several fixtures

        Args:
            games (pd.DataFrame): Fixtures

        Returns:
            pd.DataFrame: Fixtures with appended odds
        """
        parameter_df = (
            pd.DataFrame()
            .assign(rating=self.parameters[:self.league_size])
            .assign(team=self.teams)
        )

        fixtures_df = (
            pd.merge(games, parameter_df, left_on='team1', right_on='team')
            .rename(columns={"rating": "rating1"})
            .merge(parameter_df, left_on='team2', right_on='team')
            .rename(columns={"rating": "rating2"})
            .drop("team_y", axis=1)
            .drop("team_x", axis=1)
            .assign(home_adv=self.parameters[-1])
        )

        def synthesize_odds(row):
            """ Lambda function that parses row by row to compute score matrix

            Args:
                row (array): Fixture

            Returns:
                (tuple): Home and Away win and clean sheets odds
            """
            home_win_p = (
                1 / (
                    1 + np.exp(
                        -(
                            row["rating1"] + row["home_adv"] -
                            row["rating2"] - self.threshold) / self.scale
                    )
                )
            )
            away_win_p = (
                1 / (
                    1 + np.exp(
                        -(
                            row["rating2"] - row["home_adv"] -
                            row["rating1"] - self.threshold) / self.scale
                    )
                )
            )
            draw_p = 1 - home_win_p - away_win_p

            return home_win_p, draw_p, away_win_p

        (
            fixtures_df["home_win_p"],
            fixtures_df["draw_p"],
            fixtures_df["away_win_p"]
            ) = zip(*fixtures_df.apply(
                lambda row: synthesize_odds(row), axis=1))

        return fixtures_df

    def evaluate(self, games):
        """ Evaluate the model's prediction accuracy

        Args:
            games (pd.DataFrame): Fixtured to evaluate on

        Returns:
            pd.DataFrame: df with appended metrics
        """
        fixtures_df = self.predict(games)

        fixtures_df["winner"] = match_outcome(fixtures_df)

        fixtures_df["rps"] = fixtures_df.apply(
            lambda row: ranked_probability_score(
                [row["home_win_p"], row["draw_p"],
                 row["away_win_p"]], row["winner"]), axis=1)

        return fixtures_df

    def backtest(
            self,
            train_games,
            test_season,
            path='',
            cold_start=False,
            save=True):
        """ Test the model's accuracy on past/finished games by iteratively
        training and testing on parts of the data.

        Args:
            train_games (pd.DataFrame): All the training samples
            test_season (int): Season to use a test set
            path (string): Path extension to adjust to ipynb use
            cold_start (boolean): Resume training with random parameters
            save (boolean): Save predictions to disk

        Returns:
            (float): Evaluation metric
        """
        # Get training data
        self.train_games = train_games

        # Initialize model
        self.__init__(self.train_games[
            self.train_games['season'] != test_season],
            decay=self.decay)

        # Initial train on past seasons
        self.maximum_likelihood_estimation()

        # Get test data
        # Separate testing based on per GW intervals
        fixtures = (
            pd.read_csv(
                f"{path}data/fpl_official/vaastav/data/2021-22/fixtures.csv")
            .loc[:, ['event', 'kickoff_time']])
        fixtures["kickoff_time"] = (
            pd.to_datetime(fixtures["kickoff_time"]).dt.date)
        # Get only EPL games from the test season
        self.test_games = (
            self.train_games
            .loc[self.train_games['league_id'] == 2411]
            .loc[self.train_games['season'] == test_season]
            .dropna()
            )
        self.test_games["kickoff_time"] = (
            pd.to_datetime(self.test_games["date"]).dt.date)
        # Merge on date
        self.test_games = pd.merge(
            self.test_games,
            fixtures,
            left_on='kickoff_time',
            right_on='kickoff_time')
        # Add the home team and away team index for running inference
        idx = (
            pd.DataFrame()
            .assign(team=self.teams)
            .assign(team_index=np.arange(self.league_size)))
        self.test_games = (
            pd.merge(self.test_games, idx, left_on="team1", right_on="team")
            .rename(columns={"team_index": "hg"})
            .drop(["team"], axis=1)
            .drop_duplicates()
            .merge(idx, left_on="team2", right_on="team")
            .rename(columns={"team_index": "ag"})
            .drop(["team"], axis=1)
            .sort_values("date")
        )

        predictions = pd.DataFrame()

        for gw in tqdm(range(1, 39)):
            # For each GW of the season
            if gw in self.test_games['event'].values:
                # Handle case when the season is not finished

                # Run inference on the specific GW and save data.
                predictions = pd.concat([
                    predictions,
                    self.evaluate(
                        self.test_games[self.test_games['event'] == gw])
                    ])

                if cold_start:
                    previous_parameters = None
                else:
                    previous_parameters = self.parameters

                # Retrain model with the new GW added to the train set.
                self.__init__(
                    pd.concat([
                        self.train_games[
                            self.train_games['season'] != test_season],
                        self.test_games[self.test_games['event'] <= gw]
                        ])
                    .drop(columns=['ag', 'hg']),
                    parameters=previous_parameters,
                    decay=self.decay)
                self.maximum_likelihood_estimation()

        if save:
            (
                predictions
                .loc[:, [
                    'date', 'team1', 'team2', 'event', 'hg', 'ag',
                    'rating1', 'rating2', 'home_adv',
                    'home_win_p', 'draw_p', 'away_win_p']]
                .to_csv(
                    f"{path}data/predictions/fixtures/bradley_terry" +
                    f"{'' if self.decay else '_no_decay'}.csv",
                    index=False)
            )

        return predictions


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
    model = Bradley_Terry(
        pd.concat([
            df.loc[df['season'] != season],
            season_games[season_games['event'] < next_gw]
            ]),
        decay=False)
    model.maximum_likelihood_estimation()

    # Add the home team and away team index for running inference
    idx = (
        pd.DataFrame()
        .assign(team=model.teams)
        .assign(team_index=np.arange(model.league_size)))
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

    predictions = model.evaluate(
        season_games[season_games['event'] == next_gw])
    print(predictions.rps.mean())
