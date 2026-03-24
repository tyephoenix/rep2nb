from data_processor import fetch_data, process
from helpers import log

if __name__ == "__main__":
    log("Starting pipeline")
    raw = fetch_data("/users")
    result = process(raw)
    print(f"Result: {result}")
    log("Pipeline complete")
