"""Architecture parameters (specs/arch.yaml) and the quantities derived from them."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
import yaml

from . import REPO_ROOT

ARCH_YAML = REPO_ROOT / "specs" / "arch.yaml"

K_BOLTZMANN = 1.380649e-23


@dataclass(frozen=True)
class Arch:
    raw: dict

    @classmethod
    def load(cls, path: Path | str = ARCH_YAML) -> "Arch":
        with open(path, encoding="utf-8") as f:
            return cls(yaml.safe_load(f))

    # --- basic parameters -------------------------------------------------
    @property
    def fs(self) -> float:
        return float(self.raw["timing"]["fs"])

    @property
    def vref(self) -> float:
        return float(self.raw["reference"]["vref"])

    @property
    def cu(self) -> float:
        return float(self.raw["cdac"]["cu"])

    @cached_property
    def w(self) -> np.ndarray:
        """CDAC weights in decision order (cap index 12 .. 0)."""
        return np.asarray(self.raw["cdac"]["cap_weights"], dtype=float)

    @cached_property
    def sampled(self) -> np.ndarray:
        return np.asarray(self.raw["cdac"]["cap_sampled"], dtype=bool)

    @cached_property
    def out_weights(self) -> np.ndarray:
        return np.asarray(self.raw["conversion"]["out_weights"], dtype=float)

    @property
    def n_dec(self) -> int:
        return int(self.raw["conversion"]["n_decisions"])

    # --- derived ----------------------------------------------------------
    @property
    def c_dac(self) -> float:
        """Total switched DAC capacitance per side."""
        return float(self.w.sum() * self.cu)

    @property
    def c_s(self) -> float:
        """Sampling capacitance per side (caps whose bottom plate tracks VIN)."""
        return float(self.w[self.sampled].sum() * self.cu)

    @property
    def c_p(self) -> float:
        return float(self.raw["cdac"]["cp_top_ratio"]) * self.c_dac

    @property
    def c_tot(self) -> float:
        return self.c_dac + self.c_p

    @property
    def lsb(self) -> float:
        """Input-referred differential LSB = weight-1 step of the code."""
        return self.vref * self.cu / self.c_s

    @property
    def n_codes(self) -> int:
        return int(self.out_weights.sum()) + 1

    @property
    def fs_peak(self) -> float:
        """Differential full-scale peak (V): +/- (sum(w) + 1/2) LSB."""
        return (self.w.sum() + 0.5) * self.lsb

    @property
    def code_offset(self) -> float:
        """code - code_offset = signed DAC level in LSB."""
        return float(self.w.sum() + 0.5)

    @property
    def gain_top(self) -> float:
        """Input-to-top-plate attenuation C_S / C_tot."""
        return self.c_s / self.c_tot

    def redundancy(self) -> np.ndarray:
        """Decision-error tolerance (LSB, input referred) of decisions 1..13."""
        w = self.w
        tail = np.concatenate([np.cumsum(w[::-1])[::-1][1:], [0.0]])
        return tail + 1.0 - w

    def ktc_noise(self, temp_c: float = 27.0) -> float:
        """Input-referred differential sampled kT/C noise (V rms).

        Bottom-plate sampling: the top node freezes kT*C_tot of charge noise;
        referred to the input through C_S per side, doubled for the two sides.
        """
        kt = K_BOLTZMANN * (temp_c + 273.15)
        return float(np.sqrt(2.0 * kt * self.c_tot / self.c_s**2))

    def summary(self) -> dict:
        return {
            "C_S_per_side_pF": self.c_s * 1e12,
            "C_DAC_per_side_pF": self.c_dac * 1e12,
            "C_tot_per_side_pF": self.c_tot * 1e12,
            "LSB_uV": self.lsb * 1e6,
            "FS_peak_diff_V": self.fs_peak,
            "levels": self.n_codes,
            "bits_equiv": float(np.log2(self.n_codes)),
            "top_gain": self.gain_top,
            "redundancy_LSB": self.redundancy().tolist(),
            "kTC_noise_27C_uV": self.ktc_noise(27) * 1e6,
            "kTC_noise_125C_uV": self.ktc_noise(125) * 1e6,
        }


def decode(bits: np.ndarray, arch: Arch | None = None, weights=None) -> np.ndarray:
    """Raw bits (N x 14, MSB first) -> unsigned code using output weights."""
    if weights is None:
        weights = (arch or Arch.load()).out_weights
    bits = np.asarray(bits, dtype=float)
    return bits @ np.asarray(weights, dtype=float)


def code_to_volts(code: np.ndarray, arch: Arch) -> np.ndarray:
    """Unsigned code -> differential input voltage estimate."""
    return (np.asarray(code, dtype=float) - arch.code_offset) * arch.lsb
