from typing import Tuple

import numpy as np
from sklearn.metrics import pairwise_distances_argmin_min

# Given a [centroid] vector (dim: n_features), a [matrix] (dim: n_samples X n_features),
# a [labels] vector (dim: n_samples) that marks which cluster index a given sample is closest to, and
# a [cluster_idx] which indicates the cluster that the centroid belongs to,
# return the row of the [matrix] which contains the sample closest to the indicated centroid
def get_closest_sample_to_centroid(centroid: np.ndarray, matrix: np.ndarray, labels: np.ndarray, cluster_idx: int) -> int:
    sample_idxs_near_cluter = np.argwhere(labels == cluster_idx).flatten()
    samples_near_cluster = matrix[sample_idxs_near_cluter,:]
    dists_from_centroid = np.linalg.norm(np.subtract(samples_near_cluster, centroid), axis=1)
    closest_sample_idx = np.argmin(dists_from_centroid)
    matrix_sample_idx = sample_idxs_near_cluter[closest_sample_idx]
    return matrix_sample_idx

# Returns a vector (dim: n_centroids) of the indices of the [samples] matrix (dim: n_samples X n_features)
# that are the closest to that centroid index.
def get_closest_samples_to_centroids(centroids: np.ndarray, samples: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    argmin, distances = pairwise_distances_argmin_min(X = centroids, Y = samples)
    return argmin, distances
