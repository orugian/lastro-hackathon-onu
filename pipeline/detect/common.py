from pathlib import Path
import numpy as np
import rasterio
BANDS = ['pre_'+b for b in ['B2','B3','B4','B8','B11','B12']]+['pos_'+b for b in ['B2','B3','B4','B8','B11','B12']]+['dNDVI','dNBR','dNDMI','valid_mask']
FEATURES = BANDS[:12]+['pre_NDVI','pre_NBR','pre_NDMI','pos_NDVI','pos_NBR','pos_NDMI']+BANDS[12:15]
def features(a):
    a=np.asarray(a,dtype=np.float32)
    indices=[]
    for offset in (0,6):
        nir=a[...,offset+3]
        for j in (2,5,4):
            b=a[...,offset+j]; indices.append((nir-b)/np.maximum(nir+b,1e-6))
    return np.concatenate([a[...,:12],np.stack(indices,axis=-1),a[...,12:15]],axis=-1)
def read_stack(path):
    with rasterio.open(path) as src:
        if src.count != 16: raise ValueError('Stack deve ter 16 bandas: '+','.join(BANDS))
        if any(src.descriptions) and list(src.descriptions)!=BANDS:
            raise ValueError('Descricoes das bandas nao correspondem a ordem do contrato')
        a=src.read().transpose(1,2,0); profile=src.profile.copy()
        valid=(a[...,15]>0)&np.all(src.read_masks()[:15]>0,axis=0)&np.isfinite(a[...,:15]).all(axis=-1)
    return a,valid,profile
