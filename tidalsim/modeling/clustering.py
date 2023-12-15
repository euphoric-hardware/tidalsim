from typing import Tuple
import logging

import numpy as np
from sklearn.metrics import pairwise_distances_argmin_min, silhouette_score
from sklearn.cluster import KMeans

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

# Given a [matrix] (dim: n_samples X n_features), select the optimal number of K-means clusters
# within a given range according to silhouette score.
def pick_num_clusters(matrix: np.ndarray, max_clusters: int, random_state: int) -> int:
    # make sure max_clusters isn't greater than the number of data points
    max_clusters = min(max_clusters, matrix.shape[0])
    range_n_clusters = range(2, max_clusters+1)
    best_score: float = -1
    best_n_clusters: int = 1
    for n_clusters in range_n_clusters:
        # Initialize the clusterer with n_clusters value
        clusterer: KMeans = KMeans(n_clusters=n_clusters, n_init="auto", random_state=random_state)
        cluster_labels: np.ndarray = clusterer.fit_predict(matrix)

        # The silhouette_score gives the average value for all the samples.
        # This gives a perspective into the density and separation of the formed
        # clusters
        silhouette_avg: float = silhouette_score(matrix, cluster_labels)
        if silhouette_avg > best_score:
            best_score = silhouette_avg
            best_n_clusters = n_clusters
        logging.debug(f"For n_clusters = {n_clusters}, the average silhouette_score is {silhouette_avg}")
    logging.info(f"K-means best n_clusters {best_n_clusters} with silhouette score {round(best_score, 3)}")
    return best_n_clusters
