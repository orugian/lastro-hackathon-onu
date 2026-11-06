"""Baseline sem treino; deltas usam pos - pre."""
import numpy as np
from skimage.filters import threshold_otsu
from scipy.ndimage import binary_opening
from .common import read_stack

def score(a):
    return np.clip(-(a[...,12]+a[...,13])/2,0,1)
def otsu_mask(values, valid=None, opening=True):
    valid=np.isfinite(values) if valid is None else valid & np.isfinite(values)
    out=np.zeros(values.shape,dtype=bool)
    v=values[valid]
    if v.size and np.ptp(v)>1e-8: out[valid]=v>threshold_otsu(v)
    if opening and out.ndim==2: out=binary_opening(out,structure=np.ones((3,3)))
    return out & valid

def prever_baseline(stack_path):
    a,valid,_=read_stack(stack_path); prob=score(a); mask=otsu_mask(prob,valid)
    prob[~valid]=np.nan
    return prob,mask
