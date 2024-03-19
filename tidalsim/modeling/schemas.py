import pandera as pa
from pandera.typing import Series
from pandera.engines.numpy_engine import Object


class EmbeddingSchema(pa.DataFrameModel):
    # Instructions retired in this interval
    instret: Series[int]
    # Total number of instructions retired *after* the completion of this interval
    inst_count: Series[int]
    # Total number of instructions retired so far *before* this interval begins
    inst_start: Series[int]
    # An embedding vector for this interval
    embedding: Series[Object]


class ClusteringSchema(EmbeddingSchema, pa.DataFrameModel):
    # The label for the cluster this interval has been placed into
    cluster_id: Series[int]
    # The L2 norm of the difference between this interval's embedding and the centroid for its cluster
    dist_to_centroid: Series[float]
    # Whether this interval is chosen for RTL simulation
    chosen_for_rtl_sim: Series[bool]


class EstimatedPerfSchema(ClusteringSchema, pa.DataFrameModel):
    ## Cold (no warmup) estimates
    # Estimated number of cycles executed in this interval (from extrapolation)
    est_cycles_cold: Series[int]
    # Estimated IPC based on [est_cycles_cold] and [instret]
    est_ipc_cold: Series[float]
    ## Warm (functional L1 cache warmup) estimates
    est_cycles_warm: Series[int]
    est_ipc_warm: Series[float]


# This dataframe schema is for the golden perf metrics from full RTL simulation
class GoldenPerfSchema(pa.DataFrameModel):
    # Cycles consumed by this interval
    cycles: Series[int]
    # Instructions retired in this interval
    instret: Series[int]
    # Total number of instructions retired right *after* the completion of this interval
    inst_count: Series[int]
    # The golden IPC for this interval
    ipc: Series[float]
