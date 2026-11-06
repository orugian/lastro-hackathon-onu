import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box, Point
from pipeline.ingest.if100 import normaliza_coordenadas, localiza_arvores
from pipeline.ingest.poa import normalize
from pipeline.ingest.regras_doc import calcula
from pipeline.grid.celulas import grade_celulas, agrega_arvores

def test_unsigned_coordinates_and_invalid():
    lat,lon = normaliza_coordenadas(pd.Series([',437689','-8,1','bad','91']),pd.Series(['60,412819','-63,2','64','181']))
    assert lat.iloc[0] == pytest.approx(-.437689)
    assert lon.iloc[0] == pytest.approx(-60.412819)
    assert lat.iloc[1] == -8.1
    assert lat.iloc[2:].isna().all()
    assert lon.iloc[3:].isna().all()

def test_utm_tolerance_and_sign_test():
    polygon = box(500000,9100000,500100,9100100)
    auth = gpd.GeoDataFrame({'autex':['x']},geometry=[polygon],crs=31980).to_crs(4326).set_index('autex')
    trees = gpd.GeoDataFrame({'autex':['x']*3},geometry=[Point(500050,9100050),Point(500119,9100050),Point(500121,9100050)],crs=31980).to_crs(4326)
    trees['lat']=trees.geometry.y; trees['lon']=trees.geometry.x
    out=localiza_arvores(trees,auth)
    assert out.dentro_upa.tolist() == [True,True,False]
    assert out.dist_upa_m.tolist() == pytest.approx([0,19,21],abs=.001)
    north = gpd.GeoDataFrame({'autex':['x']},geometry=[box(-63.01,8,-63,8.01)],crs=4326).set_index('autex')
    wrong=gpd.GeoDataFrame({'autex':['x'],'lat':[-8.005],'lon':[-63.005]},geometry=[Point(-63.005,-8.005)],crs=4326)
    corrected=localiza_arvores(wrong,north)
    assert corrected.sinal_positivo_testado.iloc[0]
    assert corrected.sinal_lat_corrigido.iloc[0]
    assert corrected.dentro_upa.iloc[0]

def test_deduplicate_authorized_species_products():
    raw=pd.DataFrame({'autex':['x']*4,'especie':['a']*4,'produto':['Tora']*3+['Tora especial'],'volume_autorizado_m3':['10','10','20','5'],'nome_popular':['a']*4})
    assert normalize(raw,'test').volume_autorizado_m3.iloc[0] == 35

def test_rules_inclusive_dates_missing_and_thresholds():
    auth=pd.DataFrame({'autex':['x','y'],'tipo':['POA','ASV'],'validade_ini':['2022-01-01']*2,'validade_fim':['2022-12-31']*2,'area_ha':[1.,100.]})
    trees=pd.DataFrame({'autex':['x']*3,'vol_explorado':[11.,10.,12.],'vol_autorizado':[10.]*3,'dist_upa_m':[20.,20.001,0.],'data_exploracao':['2022-01-01','2022-12-31','2023-01-01']})
    sp=pd.DataFrame({'autex':['x'],'volume_autorizado_m3':[30.]})
    rules=calcula(auth,trees,sp).set_index('autex')
    assert rules.loc['x','c_n_fora'] == 1
    assert rules.loc['x','d_n_arvores_excesso'] == 1
    assert rules.loc['x','e_n_fora_validade'] == 1
    assert rules.loc['x','intensidade_m3_ha'] == 33
    assert rules.loc['y','status_C'] == 'nao_avaliado'
    assert pd.isna(rules.loc['y','volume_explorado_m3'])

def test_grid_area_and_no_boundary_double_count():
    geom=gpd.GeoSeries([box(500000,9100000,500200,9100200)],crs=31980).to_crs(4326).iloc[0]
    cells=grade_celulas(geom)
    assert cells.area_ha.sum() == pytest.approx(4,abs=.001)
    trees=gpd.GeoDataFrame({'vol_explorado':[7.,3.]},geometry=[Point(500100,9100100),Point(500050,9100050)],crs=31980).to_crs(4326)
    result=agrega_arvores(cells,trees)
    assert result.n_arvores.sum()==2
    assert result.vol_declarado.sum()==10
    with pytest.raises(ValueError): grade_celulas(geom,0)

def test_nullable_volumes_do_not_become_false_evidence():
    auth=pd.DataFrame({'autex':['x'],'tipo':['POA'],'validade_ini':['2022-01-01'],'validade_fim':['2022-12-31'],'area_ha':[100.]})
    trees=pd.DataFrame({'autex':['x'],'vol_explorado':pd.Series([pd.NA],dtype='Float64'),'vol_autorizado':pd.Series([pd.NA],dtype='Float64'),'dist_upa_m':[0.],'data_exploracao':[None]})
    sp=pd.DataFrame({'autex':['x'],'volume_autorizado_m3':[10.]})
    out=calcula(auth,trees,sp)
    assert not out.flag_D.iloc[0]
    assert pd.isna(out.volume_explorado_m3.iloc[0])
