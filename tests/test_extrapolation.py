from pathlib import Path
from pandera.typing import DataFrame

from tidalsim.modeling.extrapolation import parse_perf_file, get_checkpoint_insts
from tidalsim.modeling.schemas import ClusteringSchema


class TestExtrapolation:
    def test_parse_perf_file(self, tmp_path: Path) -> None:
        perf_file_csv = """cycles,instret
180,100
140,100
130,100
135,100"""
        with (tmp_path / "perf.csv").open("w") as f:
            f.write(perf_file_csv)
        perf = parse_perf_file(tmp_path / "perf.csv", 0)
        expected_ipc = 400 / (180 + 140 + 130 + 135)
        assert perf.ipc == expected_ipc

    def test_get_checkpoint_insts(self) -> None:
        clustering_df = DataFrame[ClusteringSchema]({
            "instret": [100, 100, 100, 100],
            "inst_count": [100, 200, 300, 400],
            "inst_start": [0, 100, 200, 300],
            "embedding": [[0, 1], [0, 1], [1, 2], [3, 4]],
            "cluster_id": [2, 2, 1, 0],
            "dist_to_centroid": [0.0, 0.0, 0.0, 0.0],
            "chosen_for_rtl_sim": [False, True, True, True],
        })
        insts = get_checkpoint_insts(clustering_df)
        assert insts == [300, 200, 100]
