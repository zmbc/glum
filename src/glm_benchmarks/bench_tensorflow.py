import warnings
from typing import Any, Dict, Union

import numpy as np
import tensorflow as tf
import tensorflow_probability as tfp
from scipy import sparse as sps

from glm_benchmarks.util import runtime


def map_distribution_to_tf_dist(distribution: str):
    if distribution.lower() == "poisson":
        return tfp.glm.Poisson()
    elif distribution.lower() == "gaussian":
        return tfp.glm.Normal()
    else:
        raise NotImplementedError


def sps_to_tf_sparse(x: sps.spmatrix) -> tf.SparseTensor:
    """
    From https://stackoverflow.com/questions/40896157/scipy-sparse-csr-matrix-to-tensorflow-sparsetensor-mini-batch-gradient-descent
    """
    coo = x.tocoo()
    indices = np.mat([coo.row, coo.col]).T
    return tf.SparseTensor(indices, coo.data, coo.shape)


def format_design_mat(x):
    """
    Adds constant and returns dense tensor if input is dense, sparse tensor if input is
    sparse.
    """
    # Add intercept
    to_stack = (np.ones((x.shape[0], 1)), x)
    if isinstance(x, sps.spmatrix):
        x = sps_to_tf_sparse(sps.hstack(to_stack))
        return x
    x = tf.convert_to_tensor(np.hstack(to_stack))
    return x


def tensorflow_bench(
    dat: Dict[str, Union[np.ndarray, sps.spmatrix]],
    distribution: str,
    alpha: float,
    l1_ratio: float,
) -> Dict[str, Any]:

    result: Dict[str, Any] = dict()
    if "weights" in dat.keys():
        warnings.warn("Tensorflow doesn't support weights.")
        return result

    n_minimum_rows_sparse = 156
    n_minimum_rows_dense = 38
    if len(dat["y"]) < n_minimum_rows_sparse and sps.isspmatrix(dat["X"]):
        warnings.warn(
            f"""Tensorflow doesn't work with fewer than {n_minimum_rows_sparse} rows when
            sparse."""
        )
        return result
    if len(dat["y"]) < n_minimum_rows_dense:
        warnings.warn(
            f"""Tensorflow doesn't work with {n_minimum_rows_dense} or fewer rows when
            dense."""
        )
        return result

    x = format_design_mat(dat["X"])
    y = tf.convert_to_tensor(dat["y"])

    t, fit = runtime(
        tfp.glm.fit_sparse,
        model_matrix=x,
        response=y,
        model=map_distribution_to_tf_dist(distribution),
        model_coefficients_start=tf.zeros(x.shape[1], dtype=tf.float64),
        tolerance=1e-2,
        l1_regularizer=alpha * l1_ratio,
        l2_regularizer=alpha * (1 - l1_ratio),
        # Starts to return infinite coefficients with more than 2
        maximum_iterations=2,
    )
    model_coefficients, is_converged, iter_ = fit
    assert np.isfinite(model_coefficients.numpy()).all()
    result["runtime"] = t
    result["model_obj"] = fit
    result["intercept"] = model_coefficients.numpy()[0]
    result["coef"] = model_coefficients.numpy()[1:]
    result["n_iter"] = iter_.numpy()
    return result