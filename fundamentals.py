import pandas as pd
import finnhub
import json
import seaborn as sns
import numpy as np
import yfinance as yf
import pprint
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from dotenv import load_dotenv
import os

class Fundamentals:
    def __init__(self, ticker, start_date, end_date):
        load_dotenv()
        api_key = os.getenv("FINNHUB") 
        self.ticker = ticker
        self.start_date = start_date
        self.end_date = end_date
        self.finnhub_client = finnhub.Client(api_key=api_key)
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
        self.company_financials = self.finnhub_client.company_basic_financials(self.ticker,'all')
    
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
        if value is not None:
            if logic == 'min':
                is_ok = value >= limit
            else:
                is_ok = value <= limit
        else:
            is_ok = None
            
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

        
        try:

            if self.metric_df.loc['epsTTM','value'] > 0 and self.metric_df.loc['epsGrowthTTMYoy','value'] > 0:
                fairValues.iat[0,5] = self.metric_df.loc['epsTTM','value'] * self.metric_df.loc['epsGrowthTTMYoy','value']
                fairValues.iat[0,6] = (self.metric_df.loc['epsTTM','value'] * self.metric_df.loc['epsGrowthTTMYoy','value'] - self.close_price) / self.close_price
            else:
                fairValues.iat[0,5] = np.nan
                fairValues.iat[0,6] = np.nan

        except:
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
        data = yf.download(self.ticker, auto_adjust=True, period='5y')
        return data

    def get_other_metric(self):
        try:
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
                ["Calculated_FCF", fcf, "Acceptable" if fcf > 0 else "Not Acceptable"],
                ["FCF_Dividend_Coverage", fcf_div_coverage ,"Acceptable" if fcf_div_coverage > 1.1 else "Not Acceptable"],
                ["Cash_Runway_Months", runway, "Acceptable" if runway > 12 else "Not Acceptable"],
                ["Accrual_Quality_Ratio", accrual_ratio, "Acceptable" if accrual_ratio < 0.1 else "Not Acceptable"],
                ["SBC_Percent_of_CashFlow", sbc_ratio, "Acceptable" if sbc_ratio < 10 else "Not Acceptable"],
            ]

            return pd.DataFrame(audit_results, columns=["fundamental", "value", "status"])
        
        except:
            def get_v_robust(keywords):
                """
                keywords: A list of strings to look for (e.g., ['NetIncome', 'ProfitLoss'])
                """
                for key in self.metric_df.index:
                    # Check if any of our keywords exist in the GAAP concept name
                    if any(word.lower() in key.lower() for word in keywords):
                        return self.metric_df.loc[key, 'value']
                return 0

            # --- Updated Extractions using the Robust Finder ---
            # Net Income aliases
            net_inc = get_v_robust(['NetIncomeLoss', 'ProfitLoss'])

            # Operating Cash Flow aliases
            op_cash = get_v_robust(['NetCashProvidedByUsedInOperatingActivities', 'CashGeneratedFromOperations'])

            # CapEx aliases
            capex = get_v_robust(['PaymentsToAcquirePropertyPlantAndEquipment', 'CapitalExpenditures'])

            # Cash Balance aliases
            cash_bal = get_v_robust(['CashAndCashEquivalentsAtCarryingValue', 'CashAndEquivalents'])

            # --- Updated Extractions using the Robust Finder ---
            # Net Income aliases
            net_inc = get_v_robust(['NetIncomeLoss', 'ProfitLoss'])

            # Operating Cash Flow aliases
            op_cash = get_v_robust(['NetCashProvidedByUsedInOperatingActivities', 'CashGeneratedFromOperations'])

            # CapEx aliases
            capex = get_v_robust(['PaymentsToAcquirePropertyPlantAndEquipment', 'CapitalExpenditures'])

            # Cash Balance aliases
            cash_bal = get_v_robust(['CashAndCashEquivalentsAtCarryingValue', 'CashAndEquivalents'])

            return pd.DataFrame([net_inc, op_cash, capex, cash_bal], columns=["value"], index=["Net Income", "Operating Cash Flow", "Capital Expenditures", "Cash Balance"])

    def get_insider_sentiment(self):
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
        print(start_date, end_date)
        # Fetch data
        trades = self.finnhub_client.stock_insider_transactions(self.ticker, start_date, end_date)
        data = trades.get('data', [])
        
        if not data:
            return ["insider_signal", "No Recent Activity"]

        # Calculate Net Buying
        # change > 0 is a buy, change < 0 is a sale
        net_shares = sum(item['change'] for item in data)
        
        if net_shares > 0:
            signal = "Bullish (Net Buy)"
        elif net_shares < 0:
            signal = "Bearish (Net Sell)"
        else:
            signal = "Neutral"
            
        return ["insider_signal", f"{signal}: {net_shares:,.0f} shares"]
    

    def get_news(self):
        news_df = pd.DataFrame(columns=['date', 'headline', 'summary' ,'url'])
        news = self.finnhub_client.company_news(self.ticker, _from=self.start_date, to=self.end_date)
        for x in news:
            del x['id']
            del x['image']
            del x['related']
            x['datetime'] = datetime.fromtimestamp(x['datetime']).strftime('%Y-%m-%d %H:%M:%S')
        return news

    def get_inflections(self):
        company_data = self.company_financials['series']['quarterly']['eps']
        earningsPerShare = np.array([])
        revueneShares = np.array([])
        totalDebtToCapital = self.metric_df.loc['totalDebt/totalEquityQuarterly','value']
        for x in company_data:
            earningsPerShare = np.append(earningsPerShare, x['v'])

        down = np.arange(len(earningsPerShare), 0, -1)

        average_weighted = round(np.average(earningsPerShare, weights=down),4)

        standard = np.std(earningsPerShare)
        
        print(f"Average Weighted EPS: {average_weighted}")
        print(f"Lower Standard Deviation: {average_weighted - standard}")
        print(f"Upper Standard Deviation: {average_weighted + standard}")
        print(f"Total Debt/Total Equity: {totalDebtToCapital}")

        up = np.arange(0, len(earningsPerShare), 1)

        reverseEarningsPerShare = earningsPerShare[::-1]

        ax = sns.lineplot(x=up, y=reverseEarningsPerShare)
        ax.axhline(y=average_weighted, color='r')
        ax.axhline(y=average_weighted + standard, color='g')
        ax.axhline(y=average_weighted - standard, color='g')
        sns.scatterplot(x=up, y=reverseEarningsPerShare)
        plt.show()


    def revenue_growth(self):
        revenue = self.finnhub_client.financials_reported(symbol=self.ticker, freq='annual')['data']
        revenueHold = np.array([])
        for x in revenue:
            for y in x['report']['ic']:
                if y['concept'] == 'us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax' and y['value'] > 0:
                    revenueHold = np.append(revenueHold, y['value'])
                elif y['concept'] == 'us-gaap_RevenueFromContractWithCustomerIncludingAssessedTax' and y['value'] > 0:
                    revenueHold = np.append(revenueHold, y['value'])
                elif y['concept'] == 'us-gaap_RevenueFromContractWithCustomer' and y['value'] > 0:
                    revenueHold = np.append(revenueHold, y['value'])
        
        revenueHold = revenueHold[::-1]
        ticker = yf.Ticker(self.ticker)
        print(ticker.financials.loc['Total Revenue'][::-1])
        if len(revenueHold) == 0:
            reverseRevenue = ticker.financials.loc['Total Revenue'][::-1]
            revenueHold = np.append(revenueHold, reverseRevenue)
        upslope = np.arange(0, len(revenueHold), 1)
        print(f"Revenue: {revenueHold}")
        sns.barplot(x=upslope, y=revenueHold)
        plt.show()


    def eps_surprise(self):
        surprise = self.finnhub_client.company_earnings(self.ticker, limit=8)
        actual = np.array([])
        estimate = np.array([])
        for x in surprise:
            actual = np.append(actual, x['actual'])
            estimate = np.append(estimate, x['estimate'])

        surpriseValue = actual - estimate

        reverseActual = actual[::-1]
        reverseEstimate = estimate[::-1]

        upslope = np.arange(0, len(surpriseValue), 1)
        sns.scatterplot(x=upslope, y=reverseActual)
        sns.scatterplot(x=upslope, y=reverseEstimate)
        #sns.scatterplot(x=upslope, y=surpriseValue)

        plt.legend(['Actual', 'Estimate'])
        plt.show()



    def calculate_dcf(self,growth_rate=0.07, discount_rate=0.10, terminal_growth=0.02):
        ticker = yf.Ticker(self.ticker)
        
        # 1. Pull Historical Cash Flow
        df_cf = ticker.cashflow
        if df_cf.empty:
            return "No cash flow data found."

        # Extract Operating Cash Flow and CapEx
        # Note: yfinance labels can vary slightly; these are the standard ones

        try:
            ocf = df_cf.loc['Operating Cash Flow']
    
            # Using 'Capital Expenditure' as found in your index list
            capex = df_cf.loc['Capital Expenditure']
            
        except KeyError:
            return "Required financial line items not found."

        # Free Cash Flow (CapEx is usually negative in yf, so we add it)
        fcf_history = ocf + capex
        current_fcf = fcf_history.iloc[0] # Most recent year
        
        print(f"Current FCF for {self.ticker}: ${current_fcf:,.2f}")

        # 2. Project Future Cash Flows (5 Years)
        projected_fcfs = []
        for i in range(1, 6):
            fcf_next = current_fcf * ((1 + growth_rate) ** i)
            projected_fcfs.append(fcf_next)

        # 3. Calculate Terminal Value (TV)
        # Formula: (FCF_Year5 * (1 + terminal_growth)) / (discount_rate - terminal_growth)
        terminal_value = (projected_fcfs[-1] * (1 + terminal_growth)) / (discount_rate - terminal_growth)

        # 4. Discount Everything to Present Value (PV)
        pv_fcfs = sum([fcf / ((1 + discount_rate) ** (i + 1)) for i, fcf in enumerate(projected_fcfs)])
        pv_terminal_value = terminal_value / ((1 + discount_rate) ** 5)

        # 5. Enterprise Value
        enterprise_value = round(float(pv_fcfs + pv_terminal_value),2)
        
        # 6. Get Equity Value (Add Cash, Sub Debt)
        info = ticker.info
        cash = info.get('totalCash', 0)
        debt = info.get('totalDebt', 0)
        shares = info.get('sharesOutstanding', 1)
        
        equity_value = round(float(enterprise_value + cash - debt),2)
        intrinsic_price = round(float(equity_value / shares),2)

        pprint.pprint({"Ticker": self.ticker,"Intrinsic Price": intrinsic_price,"Current Price": info.get('currentPrice'),"Enterprise Value": enterprise_value})
            


    def check_profitability(self):
        ticker = yf.Ticker(self.ticker)
        
        # 1. Pull Annual Income Statement
        annual_income = ticker.financials
        
        # 2. Pull Quarterly Income Statement (Better for turnarounds)
        quarterly_income = ticker.quarterly_financials
        
        if 'Net Income' not in annual_income.index:
            return "Net Income data not available."

        # Extract Net Income rows
        annual_ni = annual_income.loc['Net Income']
        quarterly_ni = quarterly_income.loc['Net Income']

        # 3. Calculate Trends
        # Sort by date (oldest to newest) to see the direction
        annual_ni = annual_ni.sort_index(ascending=True)
        quarterly_ni = quarterly_ni.sort_index(ascending=True)

        print(f"--- Profitability Analysis: {self.ticker} ---")
        print("\nAnnual Net Income History:")
        print(annual_ni)
        
        print("\nLast 4 Quarters Net Income:")
        print(quarterly_ni.tail(4))

        fig, ax = plt.subplots(1, 2, figsize=(15, 5))

        fig.suptitle(f"Profitability Analysis: {self.ticker}")
        sns.barplot (x=annual_ni.index, y=annual_ni, ax=ax[0])
        sns.barplot (x=quarterly_ni.index, y=quarterly_ni, ax=ax[1])

        plt.show()

        return annual_ni, quarterly_ni

    def analyze_turnaround(self):
        ticker = yf.Ticker(self.ticker)
        
        # Fetch Data
        info = ticker.info
        income = ticker.financials
        balance = ticker.balance_sheet
        
        # 1. Net Income Trend
        ni = income.loc['Net Income']
        ni_growth = ni.iloc[0] > ni.iloc[1] # Compare most recent to previous year
        
        # 2. Net Debt to EBITDA (Leverage)
        # Formula: (Total Debt - Cash) / EBITDA
        total_debt = info.get('totalDebt', 0)
        total_cash = info.get('totalCash', 0)
        ebitda = info.get('ebitda', 1) # Avoid division by zero
        
        net_debt_leverage = (total_debt - total_cash) / ebitda
        
        # 3. Gross Margin Trend
        # Formula: (Revenue - COGS) / Revenue
        rev = income.loc['Total Revenue']
        cogs = income.loc['Cost Of Revenue']
        current_margin = (rev.iloc[0] - cogs.iloc[0]) / rev.iloc[0]
        prev_margin = (rev.iloc[1] - cogs.iloc[1]) / rev.iloc[1]
        
        print(f"--- Advanced Analysis: {self.ticker} ---")
        print(f"Current Net Income: ${ni.iloc[0]:,.0f} (Growing: {ni_growth})")
        print(f"Net Debt / EBITDA: {net_debt_leverage:.2f}x (Lower is better)")
        print(f"Gross Margin: {current_margin:.2%} (Previous: {prev_margin:.2%})")
        
        if current_margin > prev_margin and ni_growth:
            print("\nSUMMARY: Efficiency is improving despite revenue trends.")

    def check_fcf_trend(self):
        ticker = yf.Ticker(self.ticker)
        
        # 1. Pull Annual and Quarterly Cash Flow Data
        annual_cf = ticker.cashflow
        quarterly_cf = ticker.quarterly_cashflow
        
        if annual_cf.empty or quarterly_cf.empty:
            return f"Could not find cash flow data for {self.ticker}."

        def get_fcf_series(df):
            # Prefer pre-calculated 'Free Cash Flow' if available
            if 'Free Cash Flow' in df.index:
                return df.loc['Free Cash Flow']
            # Fallback to manual calculation
            elif 'Operating Cash Flow' in df.index and 'Capital Expenditure' in df.index:
                return df.loc['Operating Cash Flow'] + df.loc['Capital Expenditure']
            return None

        annual_fcf = get_fcf_series(annual_cf)
        quarterly_fcf = get_fcf_series(quarterly_cf)

        # 2. Print Trends
        print(f"--- FCF Analysis for {self.ticker} ---")
        if annual_fcf is not None:
            # Sort oldest to newest
            annual_fcf = annual_fcf.sort_index(ascending=True)
            print("\nAnnual FCF Trend:")
            print(annual_fcf)

            sns.barplot(x=annual_fcf.index, y=annual_fcf)
            plt.show()
            
            # Calculate Year-over-Year (YoY) Change
            yoy_change = annual_fcf.iloc[-1] - annual_fcf.iloc[-2]
            status = "INCREASING" if yoy_change > 0 else "DECREASING"
            print(f"Annual Direction: {status} ({yoy_change:,.0f})")

        if quarterly_fcf is not None:
            quarterly_fcf = quarterly_fcf.sort_index(ascending=True)
            print("\nQuarterly FCF Trend (Last 4 Quarters):")
            print(quarterly_fcf.tail(4))

            sns.barplot(x=quarterly_fcf.index, y=quarterly_fcf)
            plt.show()
            
            # Calculate Quarter-over-Quarter (QoQ) Change
            qoq_change = quarterly_fcf.iloc[-1] - quarterly_fcf.iloc[-2]
            status = "INCREASING" if qoq_change > 0 else "DECREASING"
            print(f"Recent Quarterly Direction: {status} ({qoq_change:,.0f})")




