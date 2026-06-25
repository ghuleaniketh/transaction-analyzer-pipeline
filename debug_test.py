from app.pipeline.parser import parse_csv
from app.pipeline.cleaning import remove_exact_duplicates, strip_currency_symbol, normalize_currency
from app.pipeline.anomaly import detect_statistical_outliers, detect_currency_mismatch

with open('tests/fixtures/transactions.csv') as f:
    rows = parse_csv(f.read())

rows = remove_exact_duplicates(rows)

for row in rows:
    row['amount'] = strip_currency_symbol(row['amount'])
    row['currency'] = normalize_currency(row['currency'])
    row['is_anomaly'] = False
    row['anomaly_reason'] = None

rows = detect_statistical_outliers(rows)
rows = detect_currency_mismatch(rows)

print("SUCCESS")
flagged = [r for r in rows if r['is_anomaly']]
print('Total flagged:', len(flagged))
for r in flagged:
    print(r['txn_id'], r['merchant'], r['currency'], r['amount'], r['anomaly_reason'])
