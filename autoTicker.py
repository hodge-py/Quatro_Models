import papermill as pm
import time
import pandas as pd

# 50 Canadian Small Cap Tickers (TSX and TSXV)
canadian_small_caps = [
    # Top S&P/TSX SmallCap Index Constituents
    "MX.TO", "TVE.TO", "ATH.TO", "FVI.TO", "DML.TO", 
    "SII.TO", "AAUC.TO", "ERO.TO", "KXS.TO", "EDR.TO",
    "BTE.TO", "SES.TO", "GMIN.TO", "OLA.TO", "TXG.TO", 
    "KNT.TO", "EIF.TO", "ARIS.TO", "PEY.TO", "CG.TO",
    
    # 2026 TSX Venture 50 & High-Growth Tickers
    "SCZ.V", "UCU.V", "MLP.V", "AUMB.V", "TDG.V", 
    "OMG.V", "PPP.V", "AGX.V", "NCX.V", "GGA.V",
    "GSVR.V", "SLVR.V", "APGO.V", "ITR.V", "AGMR.V", 
    "FLT.V", "BYN.V", "HSTR.V", "FMT.V", "ONYX.V",
    
    # Additional Representative Small Caps
    "QNC.V", "GSI.V", "SLI.V", "CKG.V", "THX.V",
    "WCP.TO", "PEY.TO", "TOU.TO", "EFN.TO", "EQB.TO"
]

tickers = pd.read_csv('all_tickers.txt',sep='\0', header=[0]).to_numpy()

tickers = tickers.flatten()

print(tickers)

for i in tickers:
    try:
        df = pd.read_csv('Tickers.csv')
        if i in df['Tickers'].values:
            pass
        else:
            new_df = pd.DataFrame([i], columns=['Tickers'])
            new_df.to_csv('Tickers.csv', mode='a', index=False, header=False)
        pm.execute_notebook(
        'main.ipynb',
        'main.ipynb',
        parameters={'stockName': i}
        )
        time.sleep(10)
    except Exception as e:
        print(e)
        pass
