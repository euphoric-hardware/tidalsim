import pandera as pa
from pandera.typing import DataFrame, Series
from pandera.engines.numpy_engine import Object
from typing import List

class EmbeddingSchema(pa.DataFrameModel):
    instret: Series[int]
    inst_count: Series[int]
    embedding: Series[Object]

class ClusteringSchema(EmbeddingSchema, pa.DataFrameModel):
    cluster_id: Series[int]
    dist_to_centroid: Series[float]
    chosen_for_rtl_sim: Series[bool]

class EstimatedPerfSchema(ClusteringSchema, pa.DataFrameModel):
    est_cycles: Series[int]
    est_ipc: Series[int]
