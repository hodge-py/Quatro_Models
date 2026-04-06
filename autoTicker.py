import papermill as pm
import time
import pandas as pd

tickers = [
    "HLF.TO", "CAS.TO", "DBM.TO", "CCSI", "TBLA", 
    "LIF", "TRVG", "GT", "FA", "CCC", 
    "STLA", "BTE", "ASIX", "SCR.TO", "CVE.TO", 
    "IMO.TO", "BP", "SU.TO", "APOG"
]


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
