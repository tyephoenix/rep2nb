import numpy as np
from sklearn.linear_model import LinearRegression


def train(X, y):
    model = LinearRegression()
    model.fit(X, y)
    return model


def predict(model, X):
    return model.predict(X)
