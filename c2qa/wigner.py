from copy import copy
from pathlib import Path


from c2qa.circuit import CVCircuit
from c2qa.util import trace_out_qubits, simulate


import matplotlib.pyplot as plt
import numpy as np
from numpy import array, zeros, real, meshgrid, exp, pi, conj, sqrt
from qiskit.quantum_info import DensityMatrix, Statevector
from qiskit.result import Result
import scipy.stats
import matplotlib.ticker as tick


def simulate_wigner(
    circuit: CVCircuit,
    xvec: np.ndarray,
    shots: int,
    noise_passes=None,
    conditional: bool = True,
    trace: bool = False,
):
    """Simulate the circuit, optionally partial trace the results, and calculate the Wigner function."""
    states, _, _ = simulate(
        circuit,
        shots=shots,
        noise_passes=noise_passes,
        conditional_state_vector=conditional,
    )

    if states:
        if conditional:
            state = states["0x0"]  # even state
            # state = states["0x1"]  # odd state
        else:
            state = states

        if trace:
            density_matrix = trace_out_qubits(circuit, state)
        else:
            density_matrix = state

        wigner_result = _wigner(density_matrix, xvec)
    else:
        print(
            "WARN: No state vector returned by simulation -- unable to calculate Wigner function!"
        )
        wigner_result = None
        state = None

    return wigner_result, state


def simulate_wigner_multiple_statevectors(
    circuit: CVCircuit,
    xvec: np.ndarray,
    shots: int,
    statevector_label: str,
    num_statevectors:int,
    noise_passes=None,
    trace: bool = False,
):
    """Simulate the circuit, optionally partial trace the results, and calculate the Wigner function on each statevector starting with the given label."""
    state, result, _ = simulate(
        circuit,
        shots=shots,
        noise_passes=noise_passes
    )

    if len(result.results):
        wigner_results = []
        for num in range(num_statevectors):
            state = result.data()[f"{statevector_label}{num}"]
            if trace:
                density_matrix = trace_out_qubits(circuit, state)
            else:
                density_matrix = state

            wigner_results.append(_wigner(density_matrix, xvec))
    else:
        print(
            "WARN: No state vector returned by simulation -- unable to calculate Wigner function!"
        )
        wigner_results = None

    return wigner_results

def wigner(
    state,
    axes_min: int = -6,
    axes_max: int = 6,
    axes_steps: int = 200,
):
    """
    Calculate the Wigner function on the given state vector.

    Args:
        state (array-like): state vector to calculate Wigner function
        cutoff (int): cutoff used during simulation
        axes_min (int, optional): Minimum axes plot value. Defaults to -6.
        axes_max (int, optional): Maximum axes plot value. Defaults to 6.
        axes_steps (int, optional): Steps between axes ticks. Defaults to 200.
        hbar (int, optional): hbar value to use in Wigner function calculation. Defaults to 2.

    Returns:
        array-like: Results of Wigner function calculation
    """
    xvec = np.linspace(axes_min, axes_max, axes_steps)
    return _wigner(state, xvec)


def wigner_mle(
    states,
    axes_min: int = -6,
    axes_max: int = 6,
    axes_steps: int = 200,
):
    """
    Find the maximum likelihood estimation for the given state vectors and calculate the Wigner function on the result.

    Args:
        states (array-like of array-like): state vectors to calculate MLE and Wigner function
        cutoff (int): cutoff used during simulation
        axes_min (int, optional): Minimum axes plot value. Defaults to -6.
        axes_max (int, optional): Maximum axes plot value. Defaults to 6.
        axes_steps (int, optional): Steps between axes ticks. Defaults to 200.
        hbar (int, optional): hbar value to use in Wigner function calculation. Defaults to 2.

    Returns:
        array-like: Results of Wigner function calculation
    """
    mle_state = []

    # Prevent DeprecationWarning from Qiskit returning Statevector instead of array
    states_data = [state.data for state in states]

    for qubit_states in zip(*states_data):
        # TODO what distribution are the qubit states? (using normal)
        # scipy.stats normal distribution defaults to MLE fit, returns tuple[0] mean, tuple[1] std dev
        mle = scipy.stats.norm.fit(qubit_states)
        mle_state.append(mle[0])

    mle_normalized = mle_state / np.linalg.norm(mle_state)

    return wigner(mle_normalized, axes_min, axes_max, axes_steps)


def _wigner(state, xvec, yvec = None):
    if isinstance(state, DensityMatrix):
        rho = state.data
    else:
        rho = DensityMatrix(state).data

    if not yvec:
        yvec = xvec

    return _wigner_clenshaw(rho, xvec, yvec)
    # return _wigner_iterative(rho, xvec, yvec)


def _wigner_iterative(rho, xvec, yvec, g=sqrt(2)):
    r"""
    Wigner function as implemented in QuTiP (i.e., copy/paste). QuTiP is released under the BSD 3-clause license: https://github.com/qutip/qutip/blob/master/LICENSE.txt

    See https://github.com/qutip/qutip/blob/master/qutip/wigner.py#L257-L300

    Using an iterative method to evaluate the wigner functions for the Fock
    state :math:`|m><n|`.
    The Wigner function is calculated as
    :math:`W = \sum_{mn} \rho_{mn} W_{mn}` where :math:`W_{mn}` is the Wigner
    function for the density matrix :math:`|m><n|`.
    In this implementation, for each row m, Wlist contains the Wigner functions
    Wlist = [0, ..., W_mm, ..., W_mN]. As soon as one W_mn Wigner function is
    calculated, the corresponding contribution is added to the total Wigner
    function, weighted by the corresponding element in the density matrix
    :math:`rho_{mn}`.
    """

    M = np.prod(rho.shape[0])
    X, Y = meshgrid(xvec, yvec)
    A = 0.5 * g * (X + 1.0j * Y)

    Wlist = array([zeros(np.shape(A), dtype=complex) for k in range(M)])
    Wlist[0] = exp(-2.0 * abs(A) ** 2) / pi

    W = real(rho[0, 0]) * real(Wlist[0])
    for n in range(1, M):
        Wlist[n] = (2.0 * A * Wlist[n - 1]) / sqrt(n)
        W += 2 * real(rho[0, n] * Wlist[n])

    for m in range(1, M):
        temp = copy(Wlist[m])
        Wlist[m] = (2 * conj(A) * temp - sqrt(m) * Wlist[m - 1]) / sqrt(m)

        # Wlist[m] = Wigner function for |m><m|
        W += real(rho[m, m] * Wlist[m])

        for n in range(m + 1, M):
            temp2 = (2 * A * Wlist[n - 1] - sqrt(m) * temp) / sqrt(n)
            temp = copy(Wlist[n])
            Wlist[n] = temp2

            # Wlist[n] = Wigner function for |m><n|
            W += 2 * real(rho[m, n] * Wlist[n])

    return 0.5 * W * g ** 2


def _wigner_clenshaw(rho, xvec, yvec, g=sqrt(2), sparse=True):
    r"""
    Wigner Cleanshaw function as implemented in QuTiP.
    It's a copy; however, rho.data was transformed to scipy sparce matrix
        and further rho accessing lines were changed for compatibility rho.data -> rho
    QuTiP is released under the BSD 3-clause license: https://github.com/qutip/qutip/blob/master/LICENSE.txt

    See https://github.com/qutip/qutip/blob/master/qutip/wigner.py#L447-L486

    Using Clenshaw summation - numerically stable and efficient
    iterative algorithm to evaluate polynomial series.

    The Wigner function is calculated as
    :math:`W = e^(-0.5*x^2)/pi * \sum_{L} c_L (2x)^L / sqrt(L!)` where
    :math:`c_L = \sum_n \\rho_{n,L+n} LL_n^L` where
    :math:`LL_n^L = (-1)^n sqrt(L!n!/(L+n)!) LaguerreL[n,L,x]`

    """
    from scipy import sparse
    from qutip.cy.sparse_utils import _csr_get_diag

    # assuming rho.data is numpy array
    rho = sparse.csr_matrix(rho.data)

    # w0 = (2*rho_data_sparse[0,-1])*np.ones_like(A2)

    M = np.prod(rho.shape[0])
    X,Y = np.meshgrid(xvec, yvec)
    #A = 0.5 * g * (X + 1.0j * Y)
    A2 = g * (X + 1.0j * Y) #this is A2 = 2*A

    B = np.abs(A2)
    B *= B
    w0 = (2*rho[0,-1])*np.ones_like(A2)
    # w0 = (2*rho.data[0,-1])*np.ones_like(A2)
    L = M-1
    #calculation of \sum_{L} c_L (2x)^L / sqrt(L!)
    #using Horner's method
    if not sparse:
        rho = rho.full() * (2*np.ones((M,M)) - np.diag(np.ones(M)))
        while L > 0:
            L -= 1
            #here c_L = _wig_laguerre_val(L, B, np.diag(rho, L))
            w0 = _wig_laguerre_val(L, B, np.diag(rho, L)) + w0 * A2 * (L+1)**-0.5
    else:
        while L > 0:
            L -= 1
            diag = _csr_get_diag(rho.data,rho.indices,
                                rho.indptr,L)
            if L != 0:
                diag *= 2
            #here c_L = _wig_laguerre_val(L, B, np.diag(rho, L))
            w0 = _wig_laguerre_val(L, B, diag) + w0 * A2 * (L+1)**-0.5

    return w0.real * np.exp(-B*0.5) * (g*g*0.5 / pi)


def _wig_laguerre_val(L, x, c):
    r"""
    Wigner Cleanshaw function helper as implemented in QuTiP.
    It's a copy; however, rho.data was transformed to scipy sparce matrix
        and further rho accessing lines were changed for compatibility rho.data -> rho
    QuTiP is released under the BSD 3-clause license: https://github.com/qutip/qutip/blob/master/LICENSE.txt

    See https://github.com/qutip/qutip/blob/master/qutip/wigner.py#L489-L520

    this is evaluation of polynomial series inspired by hermval from numpy.
    Returns polynomial series
    \sum_n b_n LL_n^L,
    where
    LL_n^L = (-1)^n sqrt(L!n!/(L+n)!) LaguerreL[n,L,x]
    The evaluation uses Clenshaw recursion
    """

    if len(c) == 1:
        y0 = c[0]
        y1 = 0
    elif len(c) == 2:
        y0 = c[0]
        y1 = c[1]
    else:
        k = len(c)
        y0 = c[-2]
        y1 = c[-1]
        for i in range(3, len(c) + 1):
            k -= 1
            y0,    y1 = c[-i] - y1 * (float((k - 1)*(L + k - 1))/((L+k)*k))**0.5, \
            y0 - y1 * ((L + 2*k -1) - x) * ((L+k)*k)**-0.5

    return y0 - y1 * ((L + 1) - x) * (L + 1)**-0.5


def plot_wigner(
    circuit: CVCircuit,
    state_vector: Statevector,
    trace: bool = True,
    file: str = None,
    axes_min: int = -6,
    axes_max: int = 6,
    axes_steps: int = 200,
    num_colors: int = 100,
    draw_grid: bool = False,
    dpi: int = 100
):
    """Produce a Matplotlib figure for the Wigner function on the given state vector.

    Optionally perform partial trace.

    Args:
        circuit (CVCircuit): circuit with results to trace (to find Qubit index)
        state_vector (Statevector): simulation results to trace over and plot
        trace (bool, optional): True if qubits should be traced. Defaults to True.
        file (str, optional): File path to save plot. If none, return plot. Defaults to None.
        axes_min (int, optional): Minimum axes plot value. Defaults to -6.
        axes_max (int, optional): Maximum axes plot value. Defaults to 6.
        axes_steps (int, optional): Steps between axes ticks. Defaults to 200.
        num_colors (int, optional): Number of color gradients in legend. Defaults to 100.
        draw_grid (bool, optional): True if grid lines should be drawn on plot. Defaults to False.
    """
    if trace:
        state = trace_out_qubits(circuit, state_vector)
    else:
        state = state_vector

    w_fock = wigner(state, axes_min, axes_max, axes_steps)

    plot(
        data=w_fock,
        axes_min=axes_min,
        axes_max=axes_max,
        axes_steps=axes_steps,
        file=file,
        num_colors=num_colors,
        draw_grid=draw_grid,
        dpi = dpi
    )


def plot(
    data,
    axes_min: int = -6,
    axes_max: int = 6,
    axes_steps: int = 200,
    file: str = None,
    num_colors: int = 100,
    draw_grid: bool = False,
    dpi = 100
):
    """Contour plot the given data array"""
    xvec = np.linspace(axes_min, axes_max, axes_steps)

    amax = np.amax(data)
    amin = np.amin(data)
    if amax == 0 and amin == 0:
        amax = 1
        amin = -1
    abs_max = max(amax, abs(amin))
    color_levels = np.linspace(-abs_max, abs_max, num_colors)

    fig, ax = plt.subplots(constrained_layout=True)
    cont = ax.contourf(xvec, xvec, data, color_levels, cmap="RdBu")

    xvec_int = [int(x) for x in xvec]
    xvec_int = sorted(set(xvec_int))
    ax.set_xlabel(r"$x$")
    # ax.set_xticks(xvec_int)
    ax.set_ylabel(r"$p$")
    # ax.set_yticks(xvec_int)
    ax.set_aspect('equal', 'box')
    if draw_grid:
        ax.grid()


    cb = fig.colorbar(cont, ax=ax, format=tick.FormatStrFormatter('%.2f'))
    cb.set_label(r"$W(x,p)$",rotation=270,labelpad=25)

    if file:
        plt.savefig(file, dpi=dpi)
    else:
        plt.show()


def plot_wigner_projection(circuit: CVCircuit, qubit, file: str = None, draw_grid: bool = False):
    """Plot the projection onto 0, 1, +, - for the given circuit.

    This is limited to CVCircuit with only one qubit, also provided as a parameter.

    Args:
        circuit (CVCircuit): circuit to simulate and plot
        qubit (Qubit): qubit to measure
        file (str, optional): File path to save file, if None return plot. Defaults to None.
        draw_grid (bool, optional): True if gridlines should be drawn on plots. Defaults to False.
    """
    # Get unaltered state vector and partial trace
    x, _, _ = simulate(circuit)
    xT = x.data.conjugate().transpose()

    # Project onto 0 and 1 using Pauli Z
    circuit.z(qubit)
    y, _, _ = simulate(circuit)
    yT = y.data.conjugate().transpose()

    x_xT = x.data * xT
    x_yT = x.data * yT
    y_xT = y.data * xT
    y_yT = y.data * yT

    trace_x_xT = trace_out_qubits(circuit, x_xT)
    trace_x_yT = trace_out_qubits(circuit, x_yT)
    trace_y_xT = trace_out_qubits(circuit, y_xT)
    trace_y_yT = trace_out_qubits(circuit, y_yT)

    projection_zero = (trace_x_xT + trace_x_yT + trace_y_xT + trace_y_yT) / 4
    projection_one = (trace_x_xT - trace_x_yT - trace_y_xT + trace_y_yT) / 4

    # Clean up by popping off the Pauli Z
    circuit.data.pop()

    # Project onto + and - using Pauli X
    circuit.x(qubit)
    y, _, _ = simulate(circuit)
    yT = y.data.conjugate().transpose()

    x_xT = x.data * xT
    x_yT = x.data * yT
    y_xT = y.data * xT
    y_yT = y.data * yT

    trace_x_xT = trace_out_qubits(circuit, x_xT)
    trace_x_yT = trace_out_qubits(circuit, x_yT)
    trace_y_xT = trace_out_qubits(circuit, y_xT)
    trace_y_yT = trace_out_qubits(circuit, y_yT)

    projection_plus = (trace_x_xT + trace_x_yT + trace_y_xT + trace_y_yT) / 4
    projection_minus = (trace_x_xT - trace_x_yT - trace_y_xT + trace_y_yT) / 4

    # Clean up by popping of the Pauli X
    circuit.data.pop()

    # Calculate Wigner functions
    xvec = np.linspace(-6, 6, 200)
    wigner_zero = _wigner(projection_zero, xvec)
    wigner_one = _wigner(projection_one, xvec)
    wigner_plus = _wigner(projection_plus, xvec)
    wigner_minus = _wigner(projection_minus, xvec)

    # Plot using matplotlib on four subplots, at double the default width & height
    fig, ((ax0, ax1), (ax2, ax3)) = plt.subplots(2, 2, figsize=(12.8, 12.8))

    _add_contourf(ax0, fig, "Projection onto zero", xvec, xvec, wigner_zero, draw_grid)
    _add_contourf(ax1, fig, "Projection onto one", xvec, xvec, wigner_one, draw_grid)
    _add_contourf(ax2, fig, "Projection onto plus", xvec, xvec, wigner_plus, draw_grid)
    _add_contourf(ax3, fig, "Projection onto minus", xvec, xvec, wigner_minus, draw_grid)

    # Save to file or display
    if file:
        plt.savefig(file)
    else:
        plt.show()


def plot_wigner_snapshot(
    circuit: CVCircuit,
    result: Result,
    folder: Path = None,
    trace: bool = True,
    axes_min: int = -6,
    axes_max: int = 6,
    axes_steps: int = 200,
    num_colors: int = 100,
):
    snapshots = result.data()['snapshots']['statevector']

    for cv_snapshot_id in range(circuit.cv_snapshot_id):
        label = f"cv_snapshot_{cv_snapshot_id}"

        if folder:
            file = Path(folder, f"{label}.png")
        else:
            file = f"{label}.png"

        snapshot = snapshots[label]
        index = 0
        if len(snapshot) > 1:
            print(f"Simulation had {len(snapshot)} shots, plotting last one")
            index = len(snapshot) - 1

        plot_wigner(circuit, snapshot[index], trace, file, axes_min, axes_max, axes_steps, num_colors)


def _add_contourf(ax, fig, title, x, y, z, draw_grid: bool = False):
    """Add a matplotlib contourf plot with color levels based on min/max values in z."""
    amax = np.amax(z)
    amin = abs(np.amin(z))
    max_value = max(amax, amin, 0.0001)  # Force a range if amin/amax are equal
    color_levels = np.linspace(-max_value, max_value, 100)

    cont = ax.contourf(x, y, z, color_levels, cmap="RdBu")

    xvec_int = [int(value) for value in x]
    xvec_int = sorted(set(xvec_int))
    ax.set_xlabel("x")
    ax.set_xticks(xvec_int)

    yvec_int = [int(value) for value in y]
    yvec_int = sorted(set(yvec_int))
    ax.set_ylabel("p")
    ax.set_yticks(yvec_int)

    if draw_grid:
        ax.grid()

    ax.set_title(title)
    fig.colorbar(cont, ax=ax)
