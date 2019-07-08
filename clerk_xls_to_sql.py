import pandas as pd
import sqlite3

df0 = pd.read_excel("Cast Vote Records_18GEDANE.xlsx")
df1 = pd.read_excel("Cast Vote Records_18GEDANE - 1.xlsx")
df2 = pd.read_excel("Cast Vote Records_18GEDANE - 2.xlsx")

df = pd.concat([df0, df1, df2], ignore_index=True)

conn = sqlite3.connect("records.db")
df.to_sql("results", conn, if_exists='replace', index=False)

