import numpy as np
from model import train, predict

if __name__ == "__main__":
    X = np.array([[1], [2], [3], [4], [5]])
    y = np.array([2, 4, 6, 8, 10])

    m = train(X, y)
    preds = predict(m, np.array([[6], [7]]))
    print(f"Predictions: {preds}")
