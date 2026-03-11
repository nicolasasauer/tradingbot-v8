# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401

from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import (
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IStrategy,
    IntParameter,
    merge_informative_pair,
)


class SmartAlphaStrategy(IStrategy):
    """
    SmartAlphaStrategy – RSI + EMA Trend + Bollinger Bands

    Entry logic:
      - RSI is oversold (below buy_rsi threshold)
      - Price is above the EMA-200 (long-term uptrend filter)
      - EMA-20 is above EMA-50 (medium-term uptrend confirmation)
      - Price touches or crosses the lower Bollinger Band (mean-reversion entry)

    Exit logic:
      - RSI is overbought (above sell_rsi threshold)
      - Price crosses above the upper Bollinger Band
      - Trailing stop-loss as a safety net

    Protective mechanisms:
      - Hard stop-loss at 5 % below entry
      - Trailing stop-loss that kicks in after 2 % of profit
    """

    # ------------------------------------------------------------------
    # Strategy metadata
    # ------------------------------------------------------------------
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # ------------------------------------------------------------------
    # ROI – fallback exits (time-based)
    # ------------------------------------------------------------------
    minimal_roi = {
        "0": 0.03,    # 3 % at any time
        "15": 0.015,  # 1.5 % after 15 minutes
        "30": 0.01,   # 1 % after 30 minutes
        "60": 0.005,  # 0.5 % after 60 minutes
    }

    # ------------------------------------------------------------------
    # Stop-loss & trailing
    # ------------------------------------------------------------------
    stoploss = -0.05          # Hard stop: -5 %
    trailing_stop = True
    trailing_stop_positive = 0.02   # Trailing activates after +2 %
    trailing_stop_positive_offset = 0.03  # Trailing trails from +3 %
    trailing_only_offset_is_reached = True

    # ------------------------------------------------------------------
    # Hyperopt-tunable parameters
    # ------------------------------------------------------------------
    # Buy parameters
    buy_rsi = IntParameter(20, 50, default=30, space="buy", optimize=True)
    buy_rsi_enabled = BooleanParameter(default=True, space="buy", optimize=True)
    buy_ema_short = IntParameter(10, 30, default=20, space="buy", optimize=True)
    buy_ema_long = IntParameter(40, 70, default=50, space="buy", optimize=True)
    buy_bb_enabled = BooleanParameter(default=True, space="buy", optimize=True)

    # Sell parameters
    sell_rsi = IntParameter(60, 90, default=70, space="sell", optimize=True)
    sell_rsi_enabled = BooleanParameter(default=True, space="sell", optimize=True)
    sell_bb_enabled = BooleanParameter(default=True, space="sell", optimize=True)

    # ------------------------------------------------------------------
    # Startup candle count (needed so indicators are warmed up)
    # ------------------------------------------------------------------
    startup_candle_count: int = 200

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all technical indicators."""

        # ---- RSI --------------------------------------------------------
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # ---- EMA family -------------------------------------------------
        for period in (20, 50, 200):
            dataframe[f"ema_{period}"] = ta.EMA(dataframe, timeperiod=period)

        # ---- Dynamic EMA windows (hyperopt) ------------------------------
        for val in self.buy_ema_short.range:
            dataframe[f"ema_short_{val}"] = ta.EMA(dataframe, timeperiod=val)
        for val in self.buy_ema_long.range:
            dataframe[f"ema_long_{val}"] = ta.EMA(dataframe, timeperiod=val)

        # ---- Bollinger Bands (20, 2σ) ------------------------------------
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_upperband"] = bollinger["upperband"]
        dataframe["bb_middleband"] = bollinger["middleband"]
        dataframe["bb_lowerband"] = bollinger["lowerband"]
        dataframe["bb_width"] = (
            (dataframe["bb_upperband"] - dataframe["bb_lowerband"])
            / dataframe["bb_middleband"]
        )

        # ---- MACD (auxiliary confirmation) -------------------------------
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["hist"]

        # ---- Volume indicator --------------------------------------------
        dataframe["volume_mean"] = dataframe["volume"].rolling(window=20).mean()

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Define entry (buy) conditions."""

        conditions = []

        # RSI oversold
        if self.buy_rsi_enabled.value:
            conditions.append(dataframe["rsi"] < self.buy_rsi.value)

        # Dynamic EMA: short EMA above long EMA (uptrend)
        conditions.append(
            dataframe[f"ema_short_{self.buy_ema_short.value}"]
            > dataframe[f"ema_long_{self.buy_ema_long.value}"]
        )

        # Price above EMA-200 (macro uptrend filter)
        conditions.append(dataframe["close"] > dataframe["ema_200"])

        # Price touches or is below lower Bollinger Band (mean-reversion)
        if self.buy_bb_enabled.value:
            conditions.append(dataframe["close"] <= dataframe["bb_lowerband"])

        # Minimum volume filter (avoid thin markets)
        conditions.append(dataframe["volume"] > dataframe["volume_mean"] * 0.5)

        # Candle must be valid
        conditions.append(dataframe["volume"] > 0)

        if conditions:
            dataframe.loc[
                np.logical_and.reduce(conditions),
                "enter_long",
            ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Define exit (sell) conditions."""

        conditions = []

        # RSI overbought
        if self.sell_rsi_enabled.value:
            conditions.append(dataframe["rsi"] > self.sell_rsi.value)

        # Price crosses above upper Bollinger Band
        if self.sell_bb_enabled.value:
            conditions.append(dataframe["close"] >= dataframe["bb_upperband"])

        # Candle must be valid
        conditions.append(dataframe["volume"] > 0)

        if conditions:
            # Use OR logic for exits: trigger on any exit condition
            dataframe.loc[
                np.logical_or.reduce(conditions) & (dataframe["volume"] > 0),
                "exit_long",
            ] = 1

        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        """
        Dynamic protective stop-loss:
        - If profit > 5 %, lock in at least 2 % profit.
        - If profit > 10 %, lock in at least 5 % profit.
        - Otherwise fall back to the static stoploss.
        """
        if current_profit > 0.10:
            return max(self.stoploss, -0.05 + current_profit - 0.05)
        if current_profit > 0.05:
            return max(self.stoploss, -0.02)
        return self.stoploss
