import pandas as pd
import finnhub
import json
import seaborn as sns
import numpy as np


class Fundamentals:
    def __init__(self, ticker, start_date, end_date):
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.finnhub_client = finnhub.Client(api_key="d6t22lhr01qoqoiruqlgd6t22lhr01qoqoiruqm0")
        self.thresholds = {
            "currentRatioQuarterly": (1.1, 'min'),
            "epsGrowthTTMYoy": (15.0, 'min'),
            "netProfitMarginTTM": (10.0, 'min'),
            "longTermDebt/equityQuarterly": (1.0, 'max'),
            "pegTTM": (1.5, 'max'),
            "pb": (5.0, 'max') # Standard small-cap ceiling
        }
    
    def get_fundamentals(self):
        metric = self.finnhub_client.company_basic_financials(self.ticker,'all')['metric']
        df = pd.DataFrame(
                list(metric.items()), 
                columns=["metric", "value"]
        )
        ratios_df = self.finnhub_client.company_basic_financials(self.ticker,'all')['series']['annual']
        ratios_df = pd.DataFrame(list(ratios_df.items()), columns=["key", "value"])

        new_fund_df = pd.concat([df, ratios_df])

        
        new_fund_df[['is_acceptable', 'status']] = new_fund_df.apply(lambda x: self._checkMetrics(x), axis=1)

        return new_fund_df


    def _checkMetrics(self, new_fund_df):
        metric = new_fund_df['metric']
        value = new_fund_df['value']

        if metric not in self.thresholds:
            return new_fund_df
        
        limit, logic = self.thresholds[metric]
    
        # Logic Check
        if logic == 'min':
            is_ok = value >= limit
        else:
            is_ok = value <= limit
            
        # Status Labeling
        status = "Pass" if is_ok else "Fail"
        
        return pd.Series([is_ok, status])


    def plot_fundamentals(self):
        pass

    def get_quote(self):
        data = self.finnhub_client.quote(self.ticker)
        quote_df = df = pd.DataFrame(
                list(data.items()), 
                columns=["key", "value"]
            ) 
        return quote_df