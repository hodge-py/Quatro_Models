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
            "currentRatioQuarterly": (1.1, float('inf'), True),
            "longTermDebt/equityQuarterly": (0, 1.0, False),
            "epsGrowthTTMYoy": (15.0, float('inf'), True),
            "netProfitMarginTTM": (10.0, float('inf'), True),
            "pegTTM": (0.0, 1.5, False),
            "cashPerSharePerShareQuarterly": (2.0, float('inf'), True)
            }
    
    def get_fundamentals(self):
        metric = self.finnhub_client.company_basic_financials(self.ticker,'all')['metric']
        df = pd.DataFrame(
                list(metric.items()), 
                columns=["key", "value"]
        )
        ratios_df = self.finnhub_client.company_basic_financials(self.ticker,'all')['series']['annual']
        ratios_df = pd.DataFrame(list(ratios_df.items()), columns=["key", "value"])

        new_fund_df = pd.concat([df, ratios_df])

        print(new_fund_df['key'])

        new_fund_df['is_acceptable'] = (
        (new_fund_df['currentRatioQuarterly'] >= self.thresholds['currentRatioQuarterly']) &
        (new_fund_df['epsGrowthTTMYoy'] >= self.thresholds['epsGrowthTTMYoy']) &
        (new_fund_df['netProfitMarginTTM'] >= self.thresholds['netProfitMarginTTM'])
        )

        conditions = [
        (new_fund_df['epsGrowthTTMYoy'] > 25) & (new_fund_df['netProfitMarginTTM'] > 20), # High Performers
        (new_fund_df['currentRatioQuarterly'] < 1.0),                            # Liquidity issues
        (new_fund_df['pegTTM'] < 1.0) & (df['epsGrowthTTMYoy'] > 0),             # Undervalued Growth
        (new_fund_df['longTermDebt/equityQuarterly'] > 1.5)                      # Debt Heavy
        ]
        
        choices = ['High-Efficiency Growth', 'Liquidity Risk', 'Value Play', 'Over-Leveraged']
        
        df['status_flag'] = np.select(conditions, choices, default='Neutral')

        return new_fund_df

    def plot_fundamentals(self):
        pass

    def get_quote(self):
        data = self.finnhub_client.quote(self.ticker)
        quote_df = df = pd.DataFrame(
                list(data.items()), 
                columns=["key", "value"]
            ) 
        return quote_df