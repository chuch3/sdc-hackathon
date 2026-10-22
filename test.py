import numpy as np

actual = np.array([1, 0, 1, 0])
predicted = np.array([0.9, 0.2, 0.8, 0.1])

abs_errors = np.abs(actual - predicted)
sq = np.abs(actual - predicted) ** 2

bias_errors = np.mean(actual - predicted)

y_pred = np.clip(predicted, 1e-10, 1 - 1e-10)
cross_entropy = -np.mean(actual * np.log(predicted) + (1 - actual) * np.log(1 - predicted))

mse = np.mean(sq)
mbe = np.mean(bias_errors)

print(mse)
