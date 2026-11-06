import json
import numpy as np
import rasterio
from rasterio.transform import from_origin
from pipeline.detect.baseline import otsu_mask,prever_baseline
from pipeline.detect.common import BANDS,FEATURES,features
from pipeline.detect.train import folds,model
from pipeline.detect.predict import prever

def test_otsu():
    a=np.zeros((20,20)); a[5:15,5:15]=.8
    mask=otsu_mask(a)
    assert mask.sum()==100
    assert not otsu_mask(np.zeros((8,8))).any()
    assert not otsu_mask(np.full((8,8),np.nan)).any()

def test_spatial_folds():
    groups=np.repeat(np.arange(15),20); tested=[]
    for tr,te in folds(groups):
        assert not set(groups[tr]) & set(groups[te])
        tested.extend(te)
    assert sorted(tested)==list(range(len(groups)))

def test_predict_shape_and_nodata(tmp_path):
    rng=np.random.default_rng(42); a=rng.uniform(.05,.6,(20,20,16)).astype('float32'); a[...,15]=1; a[0,:,15]=0
    x=features(a.reshape(-1,16)); y=(a[...,3]>a[...,2]).ravel().astype(int)
    trained=model().fit(x,y,feature_name=FEATURES); trained.booster_.save_model(str(tmp_path/'lgbm_detector.txt'))
    (tmp_path/'threshold.json').write_text(json.dumps({'features':FEATURES,'threshold':.5}))
    stack=tmp_path/'stack.tif'
    with rasterio.open(stack,'w',driver='GTiff',width=20,height=20,count=16,dtype='float32',crs='EPSG:31980',transform=from_origin(500000,9000000,10,10)) as dst: dst.write(a.transpose(2,0,1))
    result=prever(stack,tmp_path/'out',tmp_path)
    with rasterio.open(result['prob_tif']) as src:
        assert src.shape==(20,20); assert (src.read(1)[0]==-9999).all()
    with rasterio.open(result['mask_tif']) as src:
        assert set(np.unique(src.read(1)))<={0,1,255}; assert (src.read(1)[0]==255).all()
    for f in json.loads((tmp_path/'out/poligonos.geojson').read_text())['features']:
        assert f['properties']['area_ha']>=.1
        assert 0<=f['properties']['prob']<=1
    prob,mask=prever_baseline(stack); assert np.isnan(prob[0]).all(); assert not mask[0].any()

def test_features_indices_and_order():
    a=np.ones((2,16),dtype=float); a[:,3]=3; a[:,9]=2
    result=features(a)
    assert result.shape==(2,len(FEATURES))
    np.testing.assert_allclose(result[:,12:15],.5)
    np.testing.assert_allclose(result[:,15:18],1/3)

def test_demo_exclusion_removes_entire_intersecting_block(monkeypatch):
    import pandas as pd
    from shapely.geometry import box
    from pipeline.detect import dataset
    monkeypatch.setattr(dataset,'demo_exclusion',lambda:(box(5010,5010,5020,5020),'teste'))
    df=pd.DataFrame({'bloco':['1_1','1_1','3_3'],'label':[0,1,0]})
    filtered,note=dataset.exclude_demo_rows(df)
    assert filtered.bloco.tolist()==['3_3']
    assert '1 blocos removidos' in note
