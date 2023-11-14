import pytest

from tidalsim.modeling.clustering import *

class TestClustering:
    def test_get_closest_samples_to_centroids(self) -> None:
        centroids = np.array([
            [1, 10, 50],
            [0, 0, 1],
            [10, 100, 40]
        ])
        samples = np.array([
            [0.1, 0.5, 1], # closest to centroid 1
            [10, 90, 30], # closest to centroid 2
            [0, 10, 45],
            [1, 10, 47]  # closest to centroid 0
        ])
        argmin = get_closest_samples_to_centroids(centroids, samples)
        assert argmin[0] == 3
        assert argmin[1] == 0
        assert argmin[2] == 1
