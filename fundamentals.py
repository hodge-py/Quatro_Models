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

plt.style.use('dark_background')
sns.set_theme(style="darkgrid", palette="dark", context="notebook")

class Fundamentals:
    def __init__(self, ticker):
        self.ticker = ticker
        self.ticker_obj = yf.Ticker(self.ticker)
        
        # Pulling info once on init to avoid making multiple API calls later
        self.info = self.ticker_obj.info
        
        # Note: yfinance expresses growth and margins as decimals (0.15 = 15%)
        # and Debt/Equity usually as a percentage (100 = 1.0)
        self.thresholds = {
            "currentRatio": (1.1, 'min'),
            "earningsGrowth": (0.15, 'min'),   # 15% growth
            "profitMargins": (0.10, 'min'),    # 10% profit margin
            "debtToEquity": (100.0, 'max'),    # Debt/Equity ratio of 1.0
            "pegRatio": (1.5, 'max'),
            "priceToBook": (5.0, 'max')        # Standard small-cap ceiling
        }
        
        self.avg_price = None
        self.metric_df = None
        
        # Pull current price safely
        self.close_price = self.info.get('currentPrice') or self.info.get('regularMarketPrice')
        self.other_metrics = None
    
    def get_fundamentals(self):
        # Convert the info dictionary into a DataFrame similar to Finnhub's metric structure
        self.metric_df = pd.DataFrame(
            list(self.info.items()), 
            columns=["metric", "value"]
        )
        self.metric_df['metric'] = self.metric_df['metric'].str.strip()
        self.metric_df = self.metric_df.set_index('metric')

        # Run threshold checks
        new_fund_df = self.metric_df.reset_index()
        new_fund_df[['is_acceptable', 'status']] = new_fund_df.apply(lambda x: self._checkMetrics(x), axis=1)
        new_fund_df = new_fund_df.dropna(subset=['metric'], how='any')

        return new_fund_df

    def _checkMetrics(self, row):
        metric = row['metric']
        value = row['value']

        if metric not in self.thresholds:
            return pd.Series([False, "N/A"])
        
        limit, logic = self.thresholds[metric]

        if value is not None and not pd.isna(value):
            if logic == 'min':
                is_ok = value >= limit
            else:
                is_ok = value <= limit
        else:
            is_ok = None
            
        status = "Pass" if is_ok else "Fail"
        return pd.Series([is_ok, status])

    def plot_fundamentals(self):
        pass

    def calculateFairValues(self):
        fairValues = pd.DataFrame(
            index=[0], 
            columns=[f'{self.ticker} Price','Graham_Number', 'Graham_Number_Margin', 
                     'Industry_Avg', 'Industry_Avg_Margin', 'PEG_Fair_Value', 'PEG_Fair_Value_Margin']
        )
        fairValues.iat[0, 0] = self.close_price
        
        eps = self.info.get('trailingEps')
        bvps = self.info.get('bookValue')
        
        # Graham Number Calculation
        if eps and bvps and eps > 0 and bvps > 0:
            graham_num = np.sqrt(22.5 * eps * bvps)
            fairValues.iat[0, 1] = graham_num
            fairValues.iat[0, 2] = (graham_num - float(self.close_price)) / float(self.close_price)
        else:
            fairValues.iat[0, 1] = np.nan
            fairValues.iat[0, 2] = np.nan

        if self.avg_price:
            fairValues.iat[0, 3] = self.avg_price
            fairValues.iat[0, 4] = (self.avg_price - self.close_price) / self.close_price
        else:
            fairValues.iat[0, 3] = np.nan
            fairValues.iat[0, 4] = np.nan

        # PEG Fair Value
        growth = self.info.get('earningsGrowth')
        if eps and growth and eps > 0 and growth > 0:
            # yfinance returns growth as decimal (e.g. 0.15); converting to percent (15) for formula
            growth_pct = growth * 100
            peg_fair_value = eps * growth_pct
            fairValues.iat[0, 5] = peg_fair_value
            fairValues.iat[0, 6] = (peg_fair_value - self.close_price) / self.close_price
        else:
            fairValues.iat[0, 5] = np.nan
            fairValues.iat[0, 6] = np.nan
        
        return fairValues

    def get_peers(self, peer_list=None):
        """
        yfinance does not have an automated peer lookup like Finnhub.
        Pass a list of strings manually to use this functionality.
        """
        if not peer_list:
            print("yfinance does not provide a direct peers endpoint. Please pass a list of tickers manually.")
            return pd.DataFrame(), None
            
        peer_values = {self.ticker: self.close_price}
        for peer in peer_list:
            try:
                p_ticker = yf.Ticker(peer)
                peer_values[peer] = p_ticker.info.get('currentPrice') or p_ticker.info.get('regularMarketPrice')
            except:
                pass # Silently skip failed tickers
        
        df_peers = pd.DataFrame.from_dict(peer_values, orient='index', columns=['Price'])
        self.avg_price = df_peers['Price'].mean()
        return df_peers, self.avg_price

    def get_quote(self):
        # We can extract a mini quote directly from the info dictionary
        keys = ['currentPrice', 'open', 'dayLow', 'dayHigh', 'regularMarketVolume']
        quote_data = {k: self.info.get(k) for k in keys if k in self.info}
        return pd.DataFrame(list(quote_data.items()), columns=["key", "value"])
    
    def get_history(self, period='5y'):
        # Updated to use the established ticker object
        return self.ticker_obj.history(period=period)

    def get_other_metric(self):
        try:
            cf = self.ticker_obj.cashflow
            bs = self.ticker_obj.balance_sheet
            
            # Helper to safely retrieve values from pandas index
            def get_v(df, label):
                return df.loc[label].iloc[0] if label in df.index else 0

            net_inc = get_v(cf, 'Net Income')
            op_cash = get_v(cf, 'Operating Cash Flow')
            capex = get_v(cf, 'Capital Expenditure')
            sbc = get_v(cf, 'Stock Based Compensation')
            div_paid = get_v(cf, 'Dividends Paid')
            
            cash_bal = get_v(bs, 'Cash Cash Equivalents And Short Term Investments')
            assets = get_v(bs, 'Total Assets')
            
            # --- Advanced Calculations ---
            # CapEx is usually a negative number in yfinance, so we check and add it
            fcf = op_cash + capex if capex < 0 else op_cash - capex
            
            fcf_div_coverage = fcf / abs(div_paid) if div_paid != 0 else 0
            runway = (cash_bal / (abs(fcf) / 12)) if fcf < 0 else 99 # 99 = Self-Sustaining
            accrual_ratio = (net_inc - op_cash) / assets if assets != 0 else 0
            sbc_ratio = (sbc / op_cash) * 100 if op_cash != 0 else 0

            audit_results = [
                ["Calculated_FCF", fcf, "Acceptable" if fcf > 0 else "Not Acceptable"],
                ["FCF_Dividend_Coverage", fcf_div_coverage, "Acceptable" if fcf_div_coverage > 1.1 else "Not Acceptable"],
                ["Cash_Runway_Months", runway, "Acceptable" if runway > 12 else "Not Acceptable"],
                ["Accrual_Quality_Ratio", accrual_ratio, "Acceptable" if accrual_ratio < 0.1 else "Not Acceptable"],
                ["SBC_Percent_of_CashFlow", sbc_ratio, "Acceptable" if sbc_ratio < 10 else "Not Acceptable"],
            ]

            return pd.DataFrame(audit_results, columns=["fundamental", "value", "status"])
        
        except Exception as e:
            print(f"Drill-down failed: {e}")
            return pd.DataFrame()
# Paste these inside your Fundamentals class

    def get_insider_sentiment(self):
        """
        yfinance doesn't pull individual 90-day transaction logs.
        Instead, this checks overall percentage ownership to gauge conviction.
        """
        insider_pct = self.info.get('heldPercentInsiders', 0)
        inst_pct = self.info.get('heldPercentInstitutions', 0)
        
        # Express as readable percentages
        insider_pct_str = f"{insider_pct * 100:.2f}%" if insider_pct else "N/A"
        inst_pct_str = f"{inst_pct * 100:.2f}%" if inst_pct else "N/A"
        
        # Logic flag
        if insider_pct and insider_pct > 0.10: # >10% owned by insiders is usually very strong
            signal = "Strong Insider Conviction"
        elif insider_pct and insider_pct > 0.01:
            signal = "Moderate Insider Conviction"
        else:
            signal = "Low Direct Insider Ownership"
            
        return ["insider_signal", f"{signal} (Insiders: {insider_pct_str}, Inst: {inst_pct_str})"]
    

    def get_news(self):
        """
        Pulls the latest news from Yahoo Finance based on the nested 'content' structure.
        """
        raw_news = self.ticker_obj.news
        formatted_news = []
        
        for item in raw_news:
            # Grab the nested content dictionary
            content = item.get('content', {})
            
            if not content:
                continue
                
            # 1. Parse the ISO date string (e.g., '2026-02-24T11:51:55Z')
            pub_date_str = content.get('pubDate')
            formatted_date = "N/A"
            
            if pub_date_str:
                try:
                    # Strip the 'Z' and parse the ISO format
                    dt = datetime.strptime(pub_date_str, '%Y-%m-%dT%H:%M:%SZ')
                    formatted_date = dt.strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    # Fallback just in case the format varies
                    formatted_date = pub_date_str

            # 2. Extract headline, publisher, and url
            headline = content.get('title')
            publisher = content.get('provider', {}).get('displayName')
            url = content.get('canonicalUrl', {}).get('url')

            formatted_news.append({
                'date': formatted_date,
                'headline': headline,
                'publisher': publisher,
                'url': url
            })

            pprint.pprint(formatted_news)
            
        return formatted_news

    def get_inflections(self):
        """
        Pulls reported quarterly EPS to spot trend inflections and standard deviations.
        """
        # Pulls reported and estimated EPS from the earnings dates DataFrame
        earnings_dates = self.ticker_obj.earnings_dates
        
        if earnings_dates.empty or 'Reported EPS' not in earnings_dates.columns:
            print("No historical EPS data found.")
            return

        # Drop NaNs (future earnings dates have NaN reported EPS)
        reported_eps = earnings_dates['Reported EPS'].dropna().head(8)
        
        # Reverse to put it in chronological order
        earningsPerShare = reported_eps.values[::-1]
        
        # Weighting more recent quarters heavier
        down = np.arange(len(earningsPerShare), 0, -1)
        average_weighted = round(np.average(earningsPerShare, weights=down), 4)
        standard = np.std(earningsPerShare)
        
        # Pulling debt/equity from info
        debtToEquity = self.info.get('debtToEquity', 0) / 100.0 # Standardize to a 1.0 base
        
        print(f"Average Weighted EPS: {average_weighted}")
        print(f"Lower Standard Deviation: {average_weighted - standard:.4f}")
        print(f"Upper Standard Deviation: {average_weighted + standard:.4f}")
        print(f"Total Debt/Total Equity Ratio: {debtToEquity:.2f}")

        up = np.arange(0, len(earningsPerShare), 1)

        plt.figure(figsize=(10, 5))
        ax = sns.lineplot(x=up, y=earningsPerShare)
        ax.axhline(y=average_weighted, color='r', linestyle='--', label='Wtd Avg')
        ax.axhline(y=average_weighted + standard, color='g', linestyle=':', label='+1 Std Dev')
        ax.axhline(y=average_weighted - standard, color='g', linestyle=':', label='-1 Std Dev')
        sns.scatterplot(x=up, y=earningsPerShare)
        
        plt.title(f"{self.ticker} EPS Inflection & Volatility Tracker")
        plt.xlabel("Quarters (Chronological)")
        plt.ylabel("Reported EPS")
        plt.legend()
        plt.show()


    def revenue_growth(self):
        """
        Infinitely cleaner in yfinance! No more complex GAAP contract checks.
        """
        financials = self.ticker_obj.financials
        
        if 'Total Revenue' not in financials.index:
            print("Revenue data not found in financials.")
            return
            
        revenueHold = financials.loc['Total Revenue'].dropna().values[::-1]
        
        upslope = np.arange(0, len(revenueHold), 1)
        print(f"Revenue Trend: {revenueHold}")
        
        plt.figure(figsize=(8, 5))
        sns.barplot(x=upslope, y=revenueHold, hue=upslope, legend=False)
        plt.title(f"{self.ticker} Annual Revenue Growth")
        plt.xlabel("Years (Chronological)")
        plt.ylabel("Revenue ($)")
        plt.show()


    def eps_surprise(self):
        """
        Utilizes yfinance's earnings_dates DataFrame for actuals vs estimates.
        """
        earnings_dates = self.ticker_obj.earnings_dates.dropna(subset=['Reported EPS', 'EPS Estimate']).head(8)
        
        if earnings_dates.empty:
            print("No earnings surprise data available.")
            return
            
        actual = earnings_dates['Reported EPS'].values[::-1]
        estimate = earnings_dates['EPS Estimate'].values[::-1]
        
        upslope = np.arange(0, len(actual), 1)
        
        plt.figure(figsize=(10, 5))
        sns.scatterplot(x=upslope, y=actual, s=100, label='Actual', color='blue')
        sns.scatterplot(x=upslope, y=estimate, s=100, label='Estimate', color='orange', marker='X')
        
        # Connect the dots with a line to see movement
        sns.lineplot(x=upslope, y=actual, color='blue', alpha=0.5)
        sns.lineplot(x=upslope, y=estimate, color='orange', alpha=0.5)

        plt.title(f"{self.ticker} EPS Surprise Tracker (Last 8 Quarters)")
        plt.xlabel("Quarters (Chronological)")
        plt.ylabel("EPS Value")
        plt.legend()
        plt.show()


    def calculate_dcf(self, growth_rate=0.07, discount_rate=0.10, terminal_growth=0.02):
        """
        Adapted to use the existing ticker object and clean up variable lookups.
        """
        df_cf = self.ticker_obj.cashflow
        if df_cf.empty:
            return "No cash flow data found."

        try:
            ocf = df_cf.loc['Operating Cash Flow'].iloc[0]
            capex = df_cf.loc['Capital Expenditure'].iloc[0]
        except KeyError:
            return "Required financial line items not found."

        # Free Cash Flow (CapEx is usually negative in yf, so we add it)
        current_fcf = ocf - abs(capex)
        print(f"Current FCF for {self.ticker}: ${current_fcf:,.2f}")

        # 2. Project Future Cash Flows (5 Years)
        projected_fcfs = [current_fcf * ((1 + growth_rate) ** i) for i in range(1, 6)]

        # 3. Calculate Terminal Value (TV)
        terminal_value = (projected_fcfs[-1] * (1 + terminal_growth)) / (discount_rate - terminal_growth)

        # 4. Discount Everything to Present Value (PV)
        pv_fcfs = sum([fcf / ((1 + discount_rate) ** (i + 1)) for i, fcf in enumerate(projected_fcfs)])
        pv_terminal_value = terminal_value / ((1 + discount_rate) ** 5)

        # 5. Enterprise Value
        enterprise_value = round(float(pv_fcfs + pv_terminal_value), 2)
        
        # 6. Get Equity Value (Add Cash, Sub Debt)
        cash = self.info.get('totalCash', 0)
        debt = self.info.get('totalDebt', 0)
        shares = self.info.get('sharesOutstanding', 1)
        
        equity_value = round(float(enterprise_value + cash - debt), 2)
        intrinsic_price = round(float(equity_value / shares), 2)

        pprint.pprint({
            "Ticker": self.ticker,
            "Intrinsic Price": intrinsic_price,
            "Current Price": self.info.get('currentPrice') or self.info.get('regularMarketPrice'),
            "Enterprise Value": enterprise_value
        })
        
        return intrinsic_price            


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

    def sharesBuyBackandFCFYield(self):
        ticker = yf.Ticker(self.ticker)
        info = ticker.info
        balance = ticker.balance_sheet
        shares_outstanding = info.get('sharesOutstanding', 1)
        # Compare this to the shares outstanding from 1 year ago in the balance sheet
        prev_shares = balance.loc['Ordinary Shares Number'].iloc[1] 

        buyback_pct = (prev_shares - shares_outstanding) / prev_shares
        print(f"Shares Retired (Buyback %): {buyback_pct:.2%}")

        df_cf = ticker.cashflow

        mkt_cap = info.get('marketCap', 1)

        if 'Free Cash Flow' in df_cf.index:
            fcf = df_cf.loc['Free Cash Flow'].iloc[0]
        elif 'Operating Cash Flow' in df_cf.index and 'Capital Expenditure' in df_cf.index:
            # Note: Capital Expenditure is usually negative in yfinance, so we add it
            fcf = df_cf.loc['Operating Cash Flow'].iloc[0] + df_cf.loc['Capital Expenditure'].iloc[0]
        
        if fcf and mkt_cap:
            yield_pct = (fcf / mkt_cap) * 100
            return yield_pct
        
        return None




