import csv
import io


def parse_csv(csv_content: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_content))
    return list(reader)