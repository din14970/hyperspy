# -*- coding: utf-8 -*-
# Copyright 2007-2020 The HyperSpy developers
#
# This file is part of  HyperSpy.
#
#  HyperSpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
#  HyperSpy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with  HyperSpy.  If not, see <http://www.gnu.org/licenses/>.

import pytest
import numpy as np
import numpy.testing as nt

from hyperspy._signals.signal1d import Signal1D
from hyperspy._signals.signal2d import Signal2D
from hyperspy.misc.machine_learning.import_sklearn import sklearn_installed
from hyperspy.datasets import artificial_data
from hyperspy.decorators import lazifyTestClass


def are_bss_components_equivalent(c1_list, c2_list, atol=1e-4):
    """Check if two list of components are equivalent.

    To be equivalent they must differ by a max of `atol` except
    for an arbitraty -1 factor.

    Parameters
    ----------
    c1_list, c2_list: list of Signal instances.
        The components to check.
    atol: float
        Absolute tolerance for the amount that they can differ.

    Returns
    -------
    bool

    """
    matches = 0
    for c1 in c1_list:
        for c2 in c2_list:
            if (np.allclose(c2.data, c1.data, atol=atol) or
                    np.allclose(c2.data, -c1.data, atol=atol)):
                matches += 1
    return matches == len(c1_list)


@lazifyTestClass
class TestReverseBSS:

    def setup_method(self, method):
        s = artificial_data.get_core_loss_eels_line_scan_signal()
        s.decomposition()
        s.blind_source_separation(2)
        self.s = s

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_autoreverse_default(self):
        self.s.learning_results.bss_factors[:, 0] *= -1
        self.s._auto_reverse_bss_component('loadings')
        nt.assert_array_less(self.s.learning_results.bss_factors[:, 0], 0)
        nt.assert_array_less(0, self.s.learning_results.bss_factors[:, 1])
        self.s._auto_reverse_bss_component('factors')
        nt.assert_array_less(0, self.s.learning_results.bss_factors)

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_autoreverse_on_loading(self):
        self.s._auto_reverse_bss_component('loadings')
        nt.assert_array_less(0, self.s.learning_results.bss_factors)

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_reverse_wrong_parameter(self):
        with pytest.raises(ValueError):
            self.s.blind_source_separation(2,
                                           reverse_component_criterion='toto')


@lazifyTestClass
class TestBSS1D:

    def setup_method(self, method):
        ics = np.random.laplace(size=(3, 1000))
        np.random.seed(1)
        mixing_matrix = np.random.random((100, 3))
        s = Signal1D(np.dot(mixing_matrix, ics))
        s.decomposition()

        mask_sig = s._get_signal_signal(dtype="bool")
        mask_sig.isig[5] = True

        mask_nav = s._get_navigation_signal(dtype="bool")
        mask_nav.isig[5] = True

        self.s = s
        self.mask_nav = mask_nav
        self.mask_sig = mask_sig


    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_on_loadings(self):
        self.s.blind_source_separation(
            3, diff_order=0, fun="exp", on_loadings=False)
        s2 = self.s.as_signal1D(0)
        s2.decomposition()
        s2.blind_source_separation(
            3, diff_order=0, fun="exp", on_loadings=True)
        assert are_bss_components_equivalent(
            self.s.get_bss_factors(), s2.get_bss_loadings())

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_mask_diff_order_0(self):
        # This test, unlike most other tests, either passes or raises an error.
        # It is designed to test if the mask is correctly dilated inside the
        # `blind_source_separation_method`. If the mask is not correctely
        # dilated the nan in the loadings should raise an error.
        self.s.learning_results.factors[5, :] = np.nan
        self.s.blind_source_separation(3, diff_order=0, mask=self.mask_sig)

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_mask_diff_order_1(self):
        # This test, unlike most other tests, either passes or raises an error.
        # It is designed to test if the mask is correctly dilated inside the
        # `blind_source_separation_method`. If the mask is not correctely
        # dilated the nan in the loadings should raise an error.
        self.s.learning_results.factors[5, :] = np.nan
        self.s.blind_source_separation(3, diff_order=1, mask=self.mask_sig)

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_mask_diff_order_0_on_loadings(self):
        # This test, unlike most other tests, either passes or raises an error.
        # It is designed to test if the mask is correctly dilated inside the
        # `blind_source_separation_method`. If the mask is not correctely
        # dilated the nan in the loadings should raise an error.
        self.s.learning_results.loadings[5, :] = np.nan
        self.s.blind_source_separation(3, diff_order=0, mask=self.mask_nav,
                                       on_loadings=True)

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_mask_diff_order_1_on_loadings(self):
        # This test, unlike most other tests, either passes or raises an error.
        # It is designed to test if the mask is correctly dilated inside the
        # `blind_source_separation_method`. If the mask is not correctly
        # dilated the nan in the loadings should raise an error.
        self.s.learning_results.loadings[5, :] = np.nan
        self.s.blind_source_separation(2, diff_order=1, mask=self.mask_nav,
                                       on_loadings=True)


@lazifyTestClass
class TestBSS2D:

    def setup_method(self, method):
        ics = np.random.laplace(size=(3, 1024))
        np.random.seed(1)
        mixing_matrix = np.random.random((100, 3))
        s = Signal2D(np.dot(mixing_matrix, ics).reshape((100, 32, 32)))
        for (axis, name) in zip(s.axes_manager._axes, ("z", "y", "x")):
            axis.name = name
        s.decomposition()

        mask_sig = s._get_signal_signal(dtype="bool")
        mask_sig.unfold()
        mask_sig.isig[5] = True
        mask_sig.fold()

        mask_nav = s._get_navigation_signal(dtype="bool")
        mask_nav.unfold()
        mask_nav.isig[5] = True
        mask_nav.fold()

        self.s = s
        self.mask_nav = mask_nav
        self.mask_sig = mask_sig

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_diff_axes_string_with_mask(self):
        self.s.learning_results.factors[5, :] = np.nan
        factors = self.s.get_decomposition_factors().inav[:3]
        if self.mask_sig._lazy:
            self.mask_sig.compute()
        self.s.blind_source_separation(
            3, diff_order=0, fun="exp", on_loadings=False,
            factors=factors.diff(axis="x", order=1),
            mask=self.mask_sig.diff(axis="x", order=1))
        matrix = self.s.learning_results.unmixing_matrix.copy()
        self.s.blind_source_separation(
            3, diff_order=1, fun="exp", on_loadings=False,
            diff_axes=["x"], mask=self.mask_sig
        )
        assert np.allclose(matrix, self.s.learning_results.unmixing_matrix,
                            atol=1e-6)

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_diff_axes_string_without_mask(self):
        factors = self.s.get_decomposition_factors().inav[:3].diff(
            axis="x", order=1)
        self.s.blind_source_separation(
            3, diff_order=0, fun="exp", on_loadings=False, factors=factors)
        matrix = self.s.learning_results.unmixing_matrix.copy()
        self.s.blind_source_separation(
            3, diff_order=1, fun="exp", on_loadings=False,
            diff_axes=["x"],
        )
        assert np.allclose(matrix, self.s.learning_results.unmixing_matrix,
                            atol=1e-3)

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_diff_axes_without_mask(self):
        factors = self.s.get_decomposition_factors().inav[:3].diff(
            axis="y", order=1)
        self.s.blind_source_separation(
            3, diff_order=0, fun="exp", on_loadings=False, factors=factors)
        matrix = self.s.learning_results.unmixing_matrix.copy()
        self.s.blind_source_separation(
            3, diff_order=1, fun="exp", on_loadings=False, diff_axes=[2],)
        assert np.allclose(matrix, self.s.learning_results.unmixing_matrix,
                            atol=1e-3)

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_on_loadings(self):
        self.s.blind_source_separation(
            3, diff_order=0, fun="exp", on_loadings=False)
        s2 = self.s.as_signal1D(0)
        s2.decomposition()
        s2.blind_source_separation(
            3, diff_order=0, fun="exp", on_loadings=True)
        assert are_bss_components_equivalent(
            self.s.get_bss_factors(), s2.get_bss_loadings())

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_mask_diff_order_0(self):
        # This test, unlike most other tests, either passes or raises an error.
        # It is designed to test if the mask is correctly dilated inside the
        # `blind_source_separation_method`. If the mask is not correctely
        # dilated the nan in the loadings should raise an error.
        self.s.learning_results.factors[5, :] = np.nan
        self.s.blind_source_separation(3, diff_order=0, mask=self.mask_sig)

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_mask_diff_order_1(self):
        # This test, unlike most other tests, either passes or raises an error.
        # It is designed to test if the mask is correctly dilated inside the
        # `blind_source_separation_method`. If the mask is not correctely
        # dilated the nan in the loadings should raise an error.
        self.s.learning_results.factors[5, :] = np.nan
        self.s.blind_source_separation(3, diff_order=1, mask=self.mask_sig)

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_mask_diff_order_1_diff_axes(self):
        # This test, unlike most other tests, either passes or raises an error.
        # It is designed to test if the mask is correctly dilated inside the
        # `blind_source_separation_method`. If the mask is not correctely
        # dilated the nan in the loadings should raise an error.
        self.s.learning_results.factors[5, :] = np.nan
        self.s.blind_source_separation(3, diff_order=1, mask=self.mask_sig,
                                        diff_axes=["x", ])

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_mask_diff_order_0_on_loadings(self):
        # This test, unlike most other tests, either passes or raises an error.
        # It is designed to test if the mask is correctly dilated inside the
        # `blind_source_separation_method`. If the mask is not correctely
        # dilated the nan in the loadings should raise an error.
        self.s.learning_results.loadings[5, :] = np.nan
        self.s.blind_source_separation(3, diff_order=0, mask=self.mask_nav,
                                        on_loadings=True)

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_mask_diff_order_1_on_loadings(self):
        # This test, unlike most other tests, either passes or raises an error.
        # It is designed to test if the mask is correctly dilated inside the
        # `blind_source_separation_method`. If the mask is not correctely
        # dilated the nan in the loadings should raise an error.
        s = self.s.to_signal1D()
        s.decomposition()
        if hasattr(s.learning_results.loadings, 'compute'):
            s.learning_results.loadings = s.learning_results.loadings.compute()
        s.learning_results.loadings[5, :] = np.nan
        s.blind_source_separation(3, diff_order=1, mask=self.mask_sig,
                                  on_loadings=True)

    @pytest.mark.skipif(not sklearn_installed, reason="sklearn not installed")
    def test_mask_diff_order_1_on_loadings_diff_axes(self):
        # This test, unlike most other tests, either passes or raises an error.
        # It is designed to test if the mask is correctly dilated inside the
        # `blind_source_separation_method`. If the mask is not correctely
        # dilated the nan in the loadings should raise an error.
        s = self.s.to_signal1D()
        s.decomposition()
        if hasattr(s.learning_results.loadings, 'compute'):
            s.learning_results.loadings = s.learning_results.loadings.compute()
        s.learning_results.loadings[5, :] = np.nan
        s.blind_source_separation(3, diff_order=1, mask=self.mask_sig,
                                  on_loadings=True, diff_axes=["x"])
