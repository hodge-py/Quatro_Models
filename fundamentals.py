import pandas as pd
import finnhub
import json
import seaborn as sns
import numpy as np
import yfinance as yf
import pprint


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
        self.avg_price = None
        self.metric_df = None
        self.close_price = float(self.finnhub_client.quote(self.ticker)['c'])
        self.other_metrics = None
    
    def get_fundamentals(self):
        metric = self.finnhub_client.company_basic_financials(self.ticker,'all')['metric']
        self.metric_df = df = pd.DataFrame(
                list(metric.items()), 
                columns=["metric", "value"]
        )

        self.metric_df['metric'] = self.metric_df['metric'].str.strip()

        self.metric_df = self.metric_df.set_index('metric')

        new_fund_df = df

        new_fund_df[['is_acceptable', 'status']] = new_fund_df.apply(lambda x: self._checkMetrics(x), axis=1)

        new_fund_df = new_fund_df.dropna(subset=['metric'], how='any')

        return new_fund_df


    def _checkMetrics(self, new_fund_df):
        metric = new_fund_df['metric']
        value = new_fund_df['value']

        if metric not in self.thresholds:
            return pd.Series([False, "N/A"])
        
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

    def caculateFairValues(self):
        fairValues = pd.DataFrame(index=[0],columns=[f'{self.ticker} Price','Graham_Number', 'Graham_Number_Margin', 'Industry_Avg', 'Industry_Avg_Margin', 'PEG_Fair_Value', 'PEG_Fair_Value_Margin'])
        fairValues.iat[0,0] = self.close_price
        if self.metric_df.loc['epsTTM','value'] > 0 and self.metric_df.loc['bookValuePerShareQuarterly','value'] > 0:
            fairValues.iat[0,1] = np.sqrt(22.5 * self.metric_df.loc['epsTTM','value'] * self.metric_df.loc['bookValuePerShareQuarterly','value'])
            fairValues.iat[0,2] = (fairValues.iat[0,1] - float(self.close_price)) / float(self.close_price)
        else:
            fairValues.iat[0,1] = np.nan
            fairValues.iat[0,2] = np.nan

        if self.avg_price:
            fairValues.iat[0,3] = self.avg_price
            fairValues.iat[0,4] = (self.avg_price - self.close_price) / self.close_price
        else:
            fairValues.iat[0,3] = np.nan
            fairValues.iat[0,4] = np.nan

        if self.metric_df.loc['epsTTM','value'] > 0 and self.metric_df.loc['epsGrowthTTMYoy','value'] > 0:
            fairValues.iat[0,5] = self.metric_df.loc['epsTTM','value'] * self.metric_df.loc['epsGrowthTTMYoy','value']
            fairValues.iat[0,6] = (self.metric_df.loc['epsTTM','value'] * self.metric_df.loc['epsGrowthTTMYoy','value'] - self.close_price) / self.close_price
        else:
            fairValues.iat[0,5] = np.nan
            fairValues.iat[0,6] = np.nan
        
        return fairValues


    def get_peers(self):
        peer_dict = self.finnhub_client.company_peers(self.ticker)
        peer_values = {self.ticker: self.finnhub_client.quote(self.ticker)['c']}
        for peer in peer_dict:
            if "." in peer:
                pass
            else:
                peer_values[peer] = self.finnhub_client.quote(peer)['c']
        
        df_peers = pd.DataFrame.from_dict(peer_values, orient='index', columns=['Price'])
        self.avg_price = df_peers['Price'].mean()
        return df_peers, self.avg_price

    def get_quote(self):
        data = self.finnhub_client.quote(self.ticker)
        quote_df = df = pd.DataFrame(
                list(data.items()), 
                columns=["key", "value"]
            ) 
        return quote_df
    
    def get_history(self):
        data = yf.download(self.ticker, auto_adjust=True, period='max')
        return data

    def get_other_metric(self):
        other_metrics = {}
        # FREE CASH FLOW
        finacials = self.finnhub_client.financials_reported(symbol=self.ticker,freq='annual')
        #pprint.pprint(finacials)
        cf = finacials['data'][0]['report']['cf']
        #pprint.pprint(cf)
        netOperatingCashFlow = 0
        capex = 0
        for item in cf:
            other_metrics[item['concept']] = item['value']
        
        self.other_metrics = pd.DataFrame.from_dict(other_metrics, orient='index', columns=['value'])

        # Helper to safely get values from the index
        def get_v(concept):
            return self.other_metrics.loc[concept, 'value'] if concept in self.other_metrics.index else 0

        # --- 1. Basic Extractions ---
        net_inc = get_v('us-gaap_NetIncomeLoss')
        op_cash = get_v('us-gaap_NetCashProvidedByUsedInOperatingActivities')
        capex = get_v('us-gaap_PaymentsToAcquirePropertyPlantAndEquipment')
        sbc = get_v('us-gaap_ShareBasedCompensation')
        div_paid = get_v('us-gaap_PaymentsOfDividends')
        
        # --- 2. Advanced Calculations ---
        
        # Free Cash Flow (FCF)
        fcf = op_cash - capex
        
        # FCF Dividend Coverage (Can they afford their dividend?)
        # Ratio > 1.0 means they pay dividends out of cash flow, not debt.
        fcf_div_coverage = fcf / abs(div_paid) if div_paid != 0 else 0
        
        # Cash Burn Check (Months of Runway)
        # Assumes you have 'cash_balance' from the Balance Sheet index
        cash_bal = get_v('us-gaap_CashAndCashEquivalentsAtCarryingValue')
        runway = (cash_bal / (abs(fcf) / 12)) if fcf < 0 else 99 # 99 = Self-Sustaining
        
        # Earnings Quality (Accrual Ratio)
        # (Net Income - Operating Cash) / Total Assets
        assets = get_v('us-gaap_Assets') 
        accrual_ratio = (net_inc - op_cash) / assets if assets != 0 else 0

        # SBC Reliance (Are they diluting shareholders to pay staff?)
        sbc_ratio = (sbc / op_cash) * 100 if op_cash != 0 else 0

        # --- 3. Build the Audit Results ---
        audit_results = [
            ["Calculated_FCF", fcf],
            ["FCF_Dividend_Coverage", fcf_div_coverage],
            ["Cash_Runway_Months", runway],
            ["Accrual_Quality_Ratio", accrual_ratio],
            ["SBC_Percent_of_CashFlow", sbc_ratio]
        ]

        return pd.DataFrame(audit_results, columns=["fundamental", "value"])




