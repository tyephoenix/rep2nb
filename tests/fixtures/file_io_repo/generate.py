import json

DATA = [
    {"name": "Alice", "score": 95},
    {"name": "Bob", "score": 87},
    {"name": "Charlie", "score": 92},
]

if __name__ == "__main__":
    with open("output.json", "w") as f:
        json.dump(DATA, f, indent=2)
    print(f"Wrote {len(DATA)} records to output.json")
