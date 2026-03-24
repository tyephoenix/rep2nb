import json

if __name__ == "__main__":
    with open("output.json") as f:
        data = json.load(f)

    avg = sum(d["score"] for d in data) / len(data)
    top = max(data, key=lambda d: d["score"])
    print(f"Average score: {avg:.1f}")
    print(f"Top scorer: {top['name']} ({top['score']})")
