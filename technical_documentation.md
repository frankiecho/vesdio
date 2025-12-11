# Technical Documentation: Mixed Input-Output Model

This document outlines the mathematical formulation of the mixed input-output model used in the `run_physical_risk` function to simulate supply-side shocks.

## 1. Standard Leontief Input-Output Model

The foundation of the model is the standard Leontief equation:

`$x = Ax + y$`

Where:
- **$x$**: Gross Output vector (total production of each sector)
- **$A$**: Technical Coefficients matrix (inputs required per unit of output)
- **$y$**: Final Demand vector (consumption by households, government, etc.)

This can be rearranged to solve for the gross output required to meet a given final demand:

`$x = (I - A)^{-1}y = Ly$`

Where **$L$** is the Leontief Inverse matrix, which captures all direct and indirect effects in the economy.

## 2. Mixed Input-Output Model for Supply Shocks

When a supply shock occurs, the output of one or more sectors (`$x_m$`) is exogenously fixed at a new, lower level. We need to find the new equilibrium output for all other, endogenous sectors (`$x_n$`).

The economy is partitioned as follows:
- **Endogenous sectors (n)**: Sectors whose output is determined by the model.
- **Exogenous sectors (m)**: Sectors whose output is fixed by the shock.

The core equation for the endogenous sectors is:

`$x_n = A_{nn}x_n + A_{nm}x_m + y_n$`

Where:
- **$A_{nn}$**: Sub-matrix of `$A$` for endogenous-to-endogenous flows.
- **$A_{nm}$**: Sub-matrix of `$A$` for endogenous-to-exogenous flows.
- **$y_n$**: Final demand for goods from endogenous sectors.

## 3. Incorporating Endogenous Final Demand

To create a more realistic model with stronger multiplier effects, we assume that the final demand for endogenous goods (`$y_n$`) is not fixed. Instead, it changes in proportion to the total output of the economy.

First, we define a propensity to consume vector, `cₙ`:

`$c_n = y_n / \sum x$`

The new final demand for endogenous goods becomes a function of the new total output:

`$y_{n_{new}} = c_n * (\sum x_n + \sum x_m)$`

Substituting this back into the core equation gives:

`$x_n = A_{nn}x_n + A_{nm}x_m + c_n(\sum x_n + \sum x_m)$`

Rearranging to solve for `xₙ` yields:

`$x_n = (I - A_{nn} - c_n1^T)^{-1} * (A_{nm}x_m + c_n\sum x_m)$`

Where `$1^T$` is a row vector of ones. Let `$B = (I - A_{nn} - c_n1^T)$`. The direct inversion of `$B$` is computationally very slow.

## 4. High-Performance Calculation

To avoid the slow runtime inversion of `B`, we use two established methods for high-performance computation:

**a) Deriving the Endogenous Leontief Inverse (`$L_{nn}^{-1}$`)**

Instead of inverting `$(I - A_{nn})$` at runtime, we derive it from the pre-calculated full Leontief inverse `$L$` using the formula from Miller and Blair:

`$L_{nn}^{-1} = (I - A_{nn})^{-1} = L_{nn} - L_{nm}(L_{mm})^{-1}L_{mn}$`

This is extremely fast because the matrix to be inverted, `$L_{mm}$`, is very small (its size is the number of shocked sectors).

**b) Sherman-Morrison-Woodbury Formula**

To calculate `$B^{-1}$` efficiently, we use the Sherman- Morrison-Woodbury formula, which calculates the inverse of a matrix plus a rank-1 update (`$-c_n1^T$`):

`$B^{-1} = L_{nn}^{-1} + \frac{(L_{nn}^{-1}c_n)(1^T L_{nn}^{-1})}{1 - 1^T L_{nn}^{-1}c_n}$`

This calculation uses the `$L_{nn}^{-1}$` we derived above and involves only matrix-vector multiplications, which are much faster than a full matrix inversion. This allows the model to retain the powerful economic effects of endogenous demand while executing very quickly.