"""Generate fake PII test data as CSV."""
import csv
from faker import Faker

fake = Faker()
Faker.seed(42)

rows = []
for _ in range(50):
    rows.append({
        "name": fake.name(),
        "email": fake.email(),
        "phone": fake.phone_number(),
        "address": fake.address().replace("\n", ", "),
        "ssn": fake.ssn(),
        "credit_card": fake.credit_card_number(),
        "date_of_birth": fake.date_of_birth(minimum_age=18, maximum_age=90).isoformat(),
        "company": fake.company(),
        "job": fake.job(),
    })

with open("tests/test_pii_data.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

print(f"Generated {len(rows)} rows to tests/test_pii_data.csv")
