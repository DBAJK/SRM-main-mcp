import numpy as np
from sklearn.preprocessing import MinMaxScaler

# Create and fit a scaler
scaler = MinMaxScaler()
scaler.fit(np.random.random((100, 11)))

# Save all necessary attributes
np.save('models/lstm_single/X_scaler.npy', np.array([
    scaler.data_min_,
    scaler.data_max_,
    scaler.scale_,
    scaler.min_
], dtype=object)) 